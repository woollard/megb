"""Unit tests for the in-container runner harness's pure execution logic.

These run the runner's ``run_invocation`` directly, in-process, without
Docker. Real containerized adversarial scenarios (network, filesystem,
resource limits enforced by the container runtime) are covered separately
in ``tests/test_execution_sandbox.py`` (requires Docker).
"""

import time

from src.execution.protocol import ExecutionStatus
from src.execution.runner import _is_process_limit_error, run_invocation

_LIMITS = {"max_stdout_bytes": 65_536, "max_stderr_bytes": 65_536}


def test_completed_invocation_returns_value() -> None:
    """A normal candidate function returns its value with COMPLETED status."""
    response = run_invocation(
        candidate_code="def f(x, y):\n    return x + y\n",
        entry_point="f",
        args=(1, 2),
        kwargs={},
        **_LIMITS,
    )

    assert response.status == ExecutionStatus.COMPLETED
    assert response.return_value == 3
    assert response.exception_type is None


def test_completed_invocation_can_return_none() -> None:
    """A candidate that returns None is COMPLETED, not mistaken for a failure."""
    response = run_invocation(
        candidate_code="def f():\n    return None\n",
        entry_point="f",
        args=(),
        kwargs={},
        **_LIMITS,
    )

    assert response.status == ExecutionStatus.COMPLETED
    assert response.return_value is None


def test_syntax_error_is_classified_distinctly() -> None:
    """Invalid candidate source is SYNTAX_ERROR, not CANDIDATE_EXCEPTION."""
    response = run_invocation(
        candidate_code="def f(:\n    pass\n",
        entry_point="f",
        args=(),
        kwargs={},
        **_LIMITS,
    )

    assert response.status == ExecutionStatus.SYNTAX_ERROR
    assert response.exception_type == "SyntaxError"
    assert response.return_value is None


def test_candidate_exception_is_captured_not_raised() -> None:
    """A candidate that raises is captured as CANDIDATE_EXCEPTION, never propagated."""
    response = run_invocation(
        candidate_code="def f():\n    raise ValueError('boom')\n",
        entry_point="f",
        args=(),
        kwargs={},
        **_LIMITS,
    )

    assert response.status == ExecutionStatus.CANDIDATE_EXCEPTION
    assert response.exception_type == "ValueError"
    assert response.exception_message == "boom"


def test_missing_entry_point_is_a_candidate_exception() -> None:
    """A candidate that never defines the expected entry point fails cleanly."""
    response = run_invocation(
        candidate_code="def other():\n    return 1\n",
        entry_point="f",
        args=(),
        kwargs={},
        **_LIMITS,
    )

    assert response.status == ExecutionStatus.CANDIDATE_EXCEPTION
    assert response.exception_type == "NameError"


def test_excessive_stdout_is_output_limit_not_timeout() -> None:
    """A candidate that prints past the bound is stopped immediately as OUTPUT_LIMIT."""
    response = run_invocation(
        candidate_code=(
            "def f():\n"
            "    while True:\n"
            "        print('x' * 1024)\n"
        ),
        entry_point="f",
        args=(),
        kwargs={},
        max_stdout_bytes=4096,
        max_stderr_bytes=65_536,
    )

    assert response.status == ExecutionStatus.OUTPUT_LIMIT
    assert response.stdout_truncated is True


def test_continuous_output_terminates_promptly_with_bounded_memory() -> None:
    """A candidate that never stops printing is stopped quickly, not left to grow unbounded.

    The bound is enforced while output is being produced (the write() call
    itself raises once the budget is crossed), not by buffering everything
    and truncating afterward: this test's candidate would attempt to write
    far more than max_stdout_bytes if unbounded, but both wall-clock time
    and captured size stay small regardless.
    """
    max_bytes = 4096
    start = time.monotonic()
    response = run_invocation(
        candidate_code=(
            "def f():\n"
            "    while True:\n"
            "        print('x' * 1024)\n"
        ),
        entry_point="f",
        args=(),
        kwargs={},
        max_stdout_bytes=max_bytes,
        max_stderr_bytes=max_bytes,
    )
    elapsed = time.monotonic() - start

    assert response.status == ExecutionStatus.OUTPUT_LIMIT
    assert response.stdout_truncated is True
    # Bounded: captured stdout never exceeds the configured budget no matter
    # how long the candidate would otherwise have kept printing.
    assert len(response.stdout.encode("utf-8")) <= max_bytes
    # Prompt: caught by the output bound itself, not left running until some
    # separate wall-clock timeout elsewhere catches it.
    assert elapsed < 1.0


def test_candidate_stdout_does_not_pollute_the_response_channel() -> None:
    """Candidate prints are captured into stdout, not mixed into control fields."""
    response = run_invocation(
        candidate_code="def f():\n    print('hello from candidate')\n    return 1\n",
        entry_point="f",
        args=(),
        kwargs={},
        **_LIMITS,
    )

    assert response.status == ExecutionStatus.COMPLETED
    assert response.return_value == 1
    assert "hello from candidate" in response.stdout


def test_process_limit_heuristic_matches_known_resource_errors() -> None:
    """OS-level fork/thread exhaustion errors are recognized as PROCESS_LIMIT signals."""
    assert _is_process_limit_error(BlockingIOError())
    assert _is_process_limit_error(OSError(11, "Resource temporarily unavailable"))
    assert _is_process_limit_error(OSError(12, "Cannot allocate memory"))
    assert _is_process_limit_error(RuntimeError("can't start new thread"))
    assert not _is_process_limit_error(ValueError("unrelated"))


def test_process_limit_error_is_classified_distinctly_from_candidate_exception() -> None:
    """A candidate hitting a recognized resource-exhaustion error is PROCESS_LIMIT."""
    response = run_invocation(
        candidate_code=(
            "def f():\n"
            "    raise BlockingIOError('Resource temporarily unavailable')\n"
        ),
        entry_point="f",
        args=(),
        kwargs={},
        **_LIMITS,
    )

    assert response.status == ExecutionStatus.PROCESS_LIMIT
