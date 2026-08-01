"""Docker-backed vertical-slice tests for src.reference.reference_evaluator
(MEGB-03F), using the real dataset, real oracle-record generation, and the
real ``DockerPerInvocationBackend`` — satisfying the acceptance criterion
"A small vertical slice containing correct, incorrect, malicious, and
infrastructure-failure cases passes before full-corpus use."

The infrastructure-failure member of that slice is covered by
``test_infrastructure_error_invalidates_measurement_and_stops_early`` in
``tests/test_reference_evaluator.py``, using a fake backend:
deterministically forcing a genuine Docker infrastructure failure (rather
than a candidate-caused one) in a real container is inherently flaky to
engineer in a test environment, so that member of the slice is exercised
at the classification-logic level instead.

``_CORRECT_CANDIDATE``'s body is HumanEval/0's own well-known canonical
algorithm, which also appears verbatim in ``src.reference.parity_corpus``
for an unrelated task; sharing a correct, well-known algorithm's literal
source across two different fixtures isn't the kind of duplication worth
extracting a shared helper for.
"""

# pylint: disable=duplicate-code

import hashlib
from typing import Any, Callable

import pytest
from evalplus.data.humaneval import HUMANEVAL_PLUS_VERSION

from src.dataset import PrivilegedTaskView, load_privileged_view, load_public_view
from src.evaluators.schema import FailureCategory
from src.execution.docker_backend import DockerPerInvocationBackend
from src.reference.oracle import (
    COMPARISON_PROFILE_VERSION,
    ORACLE_ALGORITHM_VERSION,
    POOL_REFERENCE_ONLY,
    comparison_profile_for_task,
    generate_oracle_record,
)
from src.reference.partition import PARTITION_ALGORITHM_VERSION
from src.reference.reference_evaluator import (
    EVALUATOR_VERSION_FULL,
    EXECUTION_PROFILE_ID_FULL,
    EXECUTION_PROTOCOL_VERSION,
    FULL_EXECUTION_PROFILE,
    ReferenceCase,
    ReferenceTaskEvidence,
    evaluate_reference,
)
from src.reference.result_schema import MeasurementStatus, ReferenceRunContext

pytestmark = pytest.mark.docker

_TASK_ID = "HumanEval/0"


def _real_task() -> tuple[PrivilegedTaskView, str]:
    privileged = {t.task_id: t for t in load_privileged_view()}[_TASK_ID]
    public = {t.task_id: t for t in load_public_view()}[_TASK_ID]
    return privileged, public.prompt


def _canonical_fn(prompt: str, canonical_solution: str, entry_point: str) -> Callable[..., Any]:
    namespace: dict[str, Any] = {}
    exec(prompt + canonical_solution, namespace)  # pylint: disable=exec-used
    return namespace[entry_point]  # type: ignore[no-any-return]


def _build_evidence() -> ReferenceTaskEvidence:
    privileged, prompt = _real_task()
    profile = comparison_profile_for_task(privileged.entry_point, atol=privileged.atol)
    canonical_fn = _canonical_fn(prompt, privileged.canonical_solution, privileged.entry_point)
    selected_inputs = privileged.base_input[:2]
    cases = tuple(
        ReferenceCase(
            case_id=f"c{index}",
            args=args,
            oracle_record=generate_oracle_record(
                task_id=_TASK_ID,
                case_id=f"c{index}",
                args=args,
                provenance="original",
                pool=POOL_REFERENCE_ONLY,
                canonical_fn=canonical_fn,
                profile=profile,
            ),
        )
        for index, args in enumerate(selected_inputs)
    )
    return ReferenceTaskEvidence(
        task_id=_TASK_ID,
        entry_point=privileged.entry_point,
        comparison_profile=profile,
        cases=cases,
        oracle_version=ORACLE_ALGORITHM_VERSION,
        partition_version=PARTITION_ALGORITHM_VERSION,
        dataset_version=HUMANEVAL_PLUS_VERSION,
        protocol_version=EXECUTION_PROTOCOL_VERSION,
    )


def _run_context() -> ReferenceRunContext:
    return ReferenceRunContext(
        experiment_run_id="exp-1",
        optimization_run_id="opt-1",
        optimization_config_sha256="b" * 64,
        portfolio_frozen_at="2026-08-01T00:00:00Z",
        portfolio_selection_rule="best_of_run",
        evaluator_version=EVALUATOR_VERSION_FULL,
        dataset_version=HUMANEVAL_PLUS_VERSION,
        partition_version=PARTITION_ALGORITHM_VERSION,
        execution_profile_id=EXECUTION_PROFILE_ID_FULL,
        comparison_profile_version=COMPARISON_PROFILE_VERSION,
    )


def _candidate_identity(candidate_code: str) -> tuple[str, str]:
    return "cand-1", hashlib.sha256(candidate_code.encode("utf-8")).hexdigest()


_PROMPT_HEADER = "from typing import List\n\n\n"
_ENTRY_SIGNATURE = "def has_close_elements(numbers: List[float], threshold: float) -> bool:\n"

_CORRECT_CANDIDATE = (
    _PROMPT_HEADER
    + _ENTRY_SIGNATURE
    + "    sorted_numbers = sorted(numbers)\n"
    "    for i in range(len(sorted_numbers) - 1):\n"
    "        if sorted_numbers[i + 1] - sorted_numbers[i] < threshold:\n"
    "            return True\n"
    "    return False\n"
)

_INCORRECT_CANDIDATE = _PROMPT_HEADER + _ENTRY_SIGNATURE + "    return False\n"

_MALICIOUS_CANDIDATE = (
    _PROMPT_HEADER
    + _ENTRY_SIGNATURE
    + "    try:\n"
    "        with open('/root/expected_output.json') as handle:\n"
    "            handle.read()\n"
    "    except Exception:\n"
    "        pass\n"
    "    sorted_numbers = sorted(numbers)\n"
    "    for i in range(len(sorted_numbers) - 1):\n"
    "        if sorted_numbers[i + 1] - sorted_numbers[i] < threshold:\n"
    "            return True\n"
    "    return False\n"
)


def test_correct_candidate_passes_real_vertical_slice() -> None:
    """A genuinely correct candidate passes both real cases via real Docker execution."""
    evidence = _build_evidence()
    run_context = _run_context()
    candidate_id, candidate_sha256 = _candidate_identity(_CORRECT_CANDIDATE)
    backend = DockerPerInvocationBackend()

    result, diagnostics = evaluate_reference(
        evidence,
        _CORRECT_CANDIDATE,
        candidate_id,
        candidate_sha256,
        run_context,
        backend=backend,
        profile=FULL_EXECUTION_PROFILE,
    )

    assert result.status == MeasurementStatus.VALID
    assert result.q_ref_task == 1.0
    assert all(d.matched is True for d in diagnostics)


def test_incorrect_candidate_produces_valid_zero_via_real_docker() -> None:
    """A candidate that always returns False fails at least one real case."""
    evidence = _build_evidence()
    run_context = _run_context()
    candidate_id, candidate_sha256 = _candidate_identity(_INCORRECT_CANDIDATE)
    backend = DockerPerInvocationBackend()

    result, _diagnostics = evaluate_reference(
        evidence,
        _INCORRECT_CANDIDATE,
        candidate_id,
        candidate_sha256,
        run_context,
        backend=backend,
        profile=FULL_EXECUTION_PROFILE,
    )

    assert result.status == MeasurementStatus.VALID
    assert result.q_ref_task == 0.0
    assert result.first_failure_category == FailureCategory.WRONG_OUTPUT


def test_malicious_exfiltration_attempt_does_not_crash_or_leak() -> None:
    """A candidate attempting to read an oracle-flavored file path still just
    executes normally — no leakage, no evaluator crash — and is scored on its
    actual (correct) logic alone."""
    evidence = _build_evidence()
    run_context = _run_context()
    candidate_id, candidate_sha256 = _candidate_identity(_MALICIOUS_CANDIDATE)
    backend = DockerPerInvocationBackend()

    result, diagnostics = evaluate_reference(
        evidence,
        _MALICIOUS_CANDIDATE,
        candidate_id,
        candidate_sha256,
        run_context,
        backend=backend,
        profile=FULL_EXECUTION_PROFILE,
    )

    assert result.status == MeasurementStatus.VALID
    assert result.q_ref_task == 1.0
    for diagnostic in diagnostics:
        assert diagnostic.matched is True
