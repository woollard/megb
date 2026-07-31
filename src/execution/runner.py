"""In-container runner harness for one candidate invocation (MEGB-02).

Runs only inside the isolated candidate worker container. Reads a single
tagged-JSON request from stdin, executes the candidate's entry point exactly
once, and writes a single tagged-JSON response line to stdout. Must never be
imported or executed in the trusted controller process, and must never
raise out of ``main()``: every failure mode is captured and reported as a
structured ``RunnerResponse`` (see CLAUDE.md: "Do not swallow execution
exceptions. Convert them into structured diagnostic results").
"""

import contextlib
import os
import sys
import time
from typing import Any, Iterator

from src.execution.protocol import ExecutionStatus
from src.execution.wire import (
    ProtocolError,
    RunnerResponse,
    parse_request_message,
    serialize_response,
)

# Sanity ceiling for the pre-parse size check only. The actual configured
# max_request_bytes policy is already enforced by the trusted controller
# before this payload was ever sent (see wire.serialize_request); this is
# defense in depth, not the source of truth for that limit.
_ABSOLUTE_MAX_REQUEST_BYTES = 8 * 1024 * 1024


class _OutputLimitExceeded(Exception):
    """Raised internally once a bounded stdout/stderr buffer is exceeded."""


class _BoundedTextBuffer:
    """A write-only text buffer that raises once a byte budget is exceeded.

    Aborting on overflow (rather than truncating and continuing) lets an
    excessive-output invocation be classified as ``OUTPUT_LIMIT``
    immediately, instead of only being caught later by the wall-clock
    timeout, and keeps memory bounded regardless of how long the candidate
    keeps writing.
    """

    def __init__(self, max_bytes: int) -> None:
        self._max_bytes = max_bytes
        self._parts: list[str] = []
        self._size = 0
        self.truncated = False

    def write(self, text: str) -> int:
        """Append text, raising once the cumulative byte budget is exceeded."""
        encoded_len = len(text.encode("utf-8", errors="replace"))
        if self._size + encoded_len > self._max_bytes:
            self.truncated = True
            raise _OutputLimitExceeded(f"output exceeded {self._max_bytes} bytes")
        self._parts.append(text)
        self._size += encoded_len
        return len(text)

    def flush(self) -> None:
        """No-op: required by the text-stream protocol used by redirect_stdout."""

    def getvalue(self) -> str:
        """Return everything written so far."""
        return "".join(self._parts)


@contextlib.contextmanager
def _os_stdio_isolated() -> Iterator[None]:
    """Redirect the OS-level stdout/stderr file descriptors (1, 2) to /dev/null.

    ``contextlib.redirect_stdout``/``redirect_stderr`` only swap Python's
    ``sys.stdout``/``sys.stderr`` objects; they do nothing to stop candidate
    code that writes directly to file descriptor 1 (e.g. ``os.write(1,
    ...)``), which would otherwise land on the same real pipe this runner
    uses for its own final protocol response line and could corrupt it (the
    "malformed protocol output" adversarial scenario). This additionally
    redirects at the OS fd level so such writes are discarded instead of
    ever reaching the real channel, and restores the original fds
    afterward regardless of how the candidate call exits.
    """
    saved_stdout_fd = os.dup(1)
    saved_stderr_fd = os.dup(2)
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull_fd, 1)
        os.dup2(devnull_fd, 2)
        yield
    finally:
        os.dup2(saved_stdout_fd, 1)
        os.dup2(saved_stderr_fd, 2)
        os.close(saved_stdout_fd)
        os.close(saved_stderr_fd)
        os.close(devnull_fd)


def _is_process_limit_error(exc: BaseException) -> bool:
    """Best-effort classification of OS-level process/thread-spawn exhaustion."""
    if isinstance(exc, (BlockingIOError, ChildProcessError)):
        return True
    if isinstance(exc, OSError) and exc.errno in (11, 12):  # EAGAIN, ENOMEM
        return True
    return isinstance(exc, RuntimeError) and "can't start new thread" in str(exc)


def run_invocation(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    candidate_code: str,
    entry_point: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    max_stdout_bytes: int,
    max_stderr_bytes: int,
) -> RunnerResponse:
    """Execute one candidate invocation and produce a structured response.

    Never raises: all failure modes are captured and reported as a
    ``RunnerResponse`` with an appropriate ``ExecutionStatus``.
    """
    stdout_buf = _BoundedTextBuffer(max_stdout_bytes)
    stderr_buf = _BoundedTextBuffer(max_stderr_bytes)

    status = ExecutionStatus.COMPLETED
    return_value: Any = None
    exception_type: str | None = None
    exception_message: str | None = None

    candidate_start = time.monotonic()
    try:
        try:
            compiled = compile(candidate_code, "<candidate>", "exec")
        except SyntaxError as exc:
            status = ExecutionStatus.SYNTAX_ERROR
            exception_type = type(exc).__name__
            exception_message = str(exc)
        else:
            with (
                _os_stdio_isolated(),
                contextlib.redirect_stdout(stdout_buf),
                contextlib.redirect_stderr(stderr_buf),
            ):
                namespace: dict[str, Any] = {}
                exec(compiled, namespace)  # pylint: disable=exec-used
                if entry_point not in namespace or not callable(namespace[entry_point]):
                    raise NameError(f"entry_point '{entry_point}' not defined by candidate code")
                return_value = namespace[entry_point](*args, **kwargs)
    except _OutputLimitExceeded:
        status = ExecutionStatus.OUTPUT_LIMIT
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Candidate code is untrusted and may raise anything.
        status = (
            ExecutionStatus.PROCESS_LIMIT
            if _is_process_limit_error(exc)
            else ExecutionStatus.CANDIDATE_EXCEPTION
        )
        exception_type = type(exc).__name__
        exception_message = str(exc)

    return RunnerResponse(
        status=status,
        return_value=return_value if status is ExecutionStatus.COMPLETED else None,
        exception_type=exception_type,
        exception_message=exception_message,
        stdout=stdout_buf.getvalue(),
        stderr=stderr_buf.getvalue(),
        stdout_truncated=stdout_buf.truncated,
        stderr_truncated=stderr_buf.truncated,
        candidate_wall_time_sec=time.monotonic() - candidate_start,
    )


def _protocol_error_response(exc: ProtocolError) -> RunnerResponse:
    return RunnerResponse(
        status=ExecutionStatus.PROTOCOL_ERROR,
        return_value=None,
        exception_type=type(exc).__name__,
        exception_message=str(exc),
        stdout="",
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
        candidate_wall_time_sec=0.0,  # candidate code never ran
    )


def main() -> None:
    """Read one request from stdin, execute it, and write one response line."""
    raw_request = sys.stdin.buffer.read()

    try:
        invocation = parse_request_message(raw_request, _ABSOLUTE_MAX_REQUEST_BYTES)
    except ProtocolError as exc:
        response = _protocol_error_response(exc)
        max_response_bytes = 1_048_576
    else:
        response = run_invocation(
            candidate_code=invocation.candidate_code,
            entry_point=invocation.entry_point,
            args=invocation.args,
            kwargs=dict(invocation.kwargs),
            max_stdout_bytes=invocation.max_stdout_bytes,
            max_stderr_bytes=invocation.max_stderr_bytes,
        )
        max_response_bytes = invocation.max_response_bytes

    try:
        payload = serialize_response(response, max_response_bytes)
    except ProtocolError as exc:
        # The real result was too large to send back; report a protocol
        # error instead of a truncated/corrupt result.
        payload = serialize_response(_protocol_error_response(exc), max_response_bytes)

    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.write(b"\n")
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
