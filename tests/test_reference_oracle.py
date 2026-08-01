"""Tests for MEGB-03C's oracle construction (comparison profiles, canonical-solution
execution, and the three physically separated oracle artifacts)."""

import dataclasses
import json
import sys
from typing import Any

import pytest

import src.reference.oracle as oracle_module
from src.dataset import PrivilegedTaskView, load_privileged_view, load_provenance, load_public_view
from src.reference.augmentation import (
    PROVENANCE_ORIGINAL,
    PROVENANCE_SUPPLEMENTARY,
    build_canonical_callable,
)
from src.reference.oracle import (
    COMPARISON_KIND_DEFAULT,
    COMPARISON_KIND_FIND_ZERO,
    DEVELOPMENT_ORACLE_ARTIFACT_ID,
    ORACLE_STATUS_GENERATION_FAILED,
    ORACLE_STATUS_SUCCESS,
    POOL_DEVELOPMENT,
    POOL_REFERENCE_ONLY,
    POOL_REFERENCE_VALIDATION_ONLY,
    AmbiguousSupplementaryOracleError,
    ComparisonProfile,
    OracleBuildResult,
    build_oracle_artifacts,
    comparison_profile_for_task,
    compare_outputs,
    generate_oracle_record,
    unbounded_int_str_digits,
)
from src.reference.partition import (
    EXCLUDED_TASK_ID,
    CaseWithProvenance,
    PrimaryExperimentManifest,
    ReferenceValidationManifest,
    build_primary_experiment_manifest,
    build_reference_validation_manifest,
    gather_eligible_cases_and_args,
)
from src.reference.case_serialization import stable_case_id


def _task(
    task_id: str,
    entry_point: str,
    canonical_solution: str,
    atol: float = 0.0,
    base_input: tuple[tuple[Any, ...], ...] = (),
) -> PrivilegedTaskView:
    """Build a minimal synthetic PrivilegedTaskView for a test-only task."""
    return PrivilegedTaskView(
        task_id=task_id,
        entry_point=entry_point,
        canonical_solution=canonical_solution,
        original_test="",
        contract="",
        atol=atol,
        base_input=base_input,
        plus_input=(),
    )


def _synthetic_double_task(task_id: str, count: int = 100) -> PrivilegedTaskView:
    """A task whose canonical solution just doubles its integer input.

    The matching prompt (needed separately as ``public_by_id[task_id]``) is
    ``f"def {entry_point}(n):\\n"`` at every call site.
    """
    solution = "    return n * 2\n"
    return _task(
        task_id,
        entry_point=task_id.replace("/", "_"),
        canonical_solution=solution,
        base_input=tuple((n,) for n in range(count)),
    )


def _cases_and_args(
    task: PrivilegedTaskView,
) -> tuple[list[CaseWithProvenance], dict[str, tuple[Any, ...]]]:
    cases = []
    args_by_id: dict[str, tuple[Any, ...]] = {}
    for args in task.base_input:
        cid = stable_case_id(task.task_id, args)
        cases.append(CaseWithProvenance(case_id=cid, provenance=PROVENANCE_ORIGINAL))
        args_by_id[cid] = args
    return cases, args_by_id


def _build_synthetic_corpus(
    experimental_task_ids: list[str], validation_only_count: int = 12
) -> tuple[
    dict[str, PrivilegedTaskView],
    dict[str, str],
    dict[str, list[CaseWithProvenance]],
    dict[str, dict[str, tuple[Any, ...]]],
]:
    """Two (or more) experimental tasks with >=70 cases each, plus a
    HumanEval/39-style validation-only task with a small exhaustive domain."""
    privileged_by_id: dict[str, PrivilegedTaskView] = {}
    public_by_id: dict[str, str] = {}
    cases_by_task: dict[str, list[CaseWithProvenance]] = {}
    args_by_task: dict[str, dict[str, tuple[Any, ...]]] = {}

    for task_id in experimental_task_ids:
        task = _synthetic_double_task(task_id)
        privileged_by_id[task_id] = task
        public_by_id[task_id] = f"def {task.entry_point}(n):\n"
        cases, args_by_id = _cases_and_args(task)
        cases_by_task[task_id] = cases
        args_by_task[task_id] = args_by_id

    validation_task = _synthetic_double_task(EXCLUDED_TASK_ID, count=validation_only_count)
    privileged_by_id[EXCLUDED_TASK_ID] = validation_task
    public_by_id[EXCLUDED_TASK_ID] = f"def {validation_task.entry_point}(n):\n"
    val_cases, val_args = _cases_and_args(validation_task)
    cases_by_task[EXCLUDED_TASK_ID] = val_cases
    args_by_task[EXCLUDED_TASK_ID] = val_args

    return privileged_by_id, public_by_id, cases_by_task, args_by_task


def _build(
    experimental_task_ids: list[str] | None = None,
) -> tuple[OracleBuildResult, PrimaryExperimentManifest, ReferenceValidationManifest]:
    experimental_task_ids = experimental_task_ids or ["T/A", "T/B"]
    privileged_by_id, public_by_id, cases_by_task, args_by_task = _build_synthetic_corpus(
        experimental_task_ids
    )
    provenance = load_provenance()
    experiment_manifest = build_primary_experiment_manifest(cases_by_task, provenance)
    validation_manifest = build_reference_validation_manifest(cases_by_task, provenance)
    result = build_oracle_artifacts(
        experiment_manifest,
        validation_manifest,
        cases_by_task,
        args_by_task,
        privileged_by_id,
        public_by_id,
        provenance,
    )
    return result, experiment_manifest, validation_manifest


# --- comparison profile / compare_outputs -----------------------------------


def test_comparison_profile_for_find_zero_entry_point() -> None:
    """HumanEval/32's entry_point (find_zero) gets the special-oracle profile."""
    profile = comparison_profile_for_task("find_zero", atol=1e-4)
    assert profile.kind == COMPARISON_KIND_FIND_ZERO
    assert profile.atol == 1e-4


def test_comparison_profile_for_ordinary_entry_point() -> None:
    """Every other entry_point gets the default exact-or-tolerance profile."""
    profile = comparison_profile_for_task("has_close_elements", atol=1e-6)
    assert profile.kind == COMPARISON_KIND_DEFAULT


def test_compare_outputs_exact_match() -> None:
    """Identical values compare equal regardless of atol."""
    profile = ComparisonProfile(kind=COMPARISON_KIND_DEFAULT, atol=0.0)
    assert compare_outputs(profile, args=(), actual=[1, 2, 3], expected=[1, 2, 3])


def test_compare_outputs_float_tolerance_accepts_within_atol() -> None:
    """A float within the enforced tolerance (atol=0 -> 1e-6 default) still passes."""
    profile = ComparisonProfile(kind=COMPARISON_KIND_DEFAULT, atol=0.0)
    assert compare_outputs(profile, args=(), actual=1.0000001, expected=1.0)


def test_compare_outputs_float_tolerance_rejects_beyond_atol() -> None:
    """A float outside the enforced tolerance is rejected."""
    profile = ComparisonProfile(kind=COMPARISON_KIND_DEFAULT, atol=0.0)
    assert not compare_outputs(profile, args=(), actual=1.1, expected=1.0)


def test_compare_outputs_respects_explicit_task_atol() -> None:
    """A task-specific atol wider than the default is honored."""
    profile = ComparisonProfile(kind=COMPARISON_KIND_DEFAULT, atol=0.5)
    assert compare_outputs(profile, args=(), actual=1.3, expected=1.0)


def test_compare_outputs_type_mismatch_rejected() -> None:
    """A differently-typed actual value is rejected even if it "looks" equal."""
    profile = ComparisonProfile(kind=COMPARISON_KIND_DEFAULT, atol=1e-6)
    assert not compare_outputs(profile, args=(), actual="1", expected=1)


def test_compare_outputs_find_zero_special_oracle() -> None:
    """find_zero: postcondition check on the polynomial, independent of any
    fixed expected value — 1.0 and -1.0 are both valid roots of x^2 - 1."""
    profile = ComparisonProfile(kind=COMPARISON_KIND_FIND_ZERO, atol=1e-4)
    coefficients = [-1.0, 0.0, 1.0]  # -1 + 0x + 1x^2 = x^2 - 1
    assert compare_outputs(profile, args=(coefficients,), actual=1.0, expected=None)
    assert compare_outputs(profile, args=(coefficients,), actual=-1.0, expected=None)
    assert not compare_outputs(profile, args=(coefficients,), actual=2.0, expected=None)


# --- generate_oracle_record: success / failure / mutation -------------------


def test_generate_oracle_record_success() -> None:
    """A well-behaved canonical solution produces a success record with the
    tagged-JSON encoding of its actual return value."""
    task = _synthetic_double_task("T/X", count=1)
    canonical_fn = build_canonical_callable(
        f"def {task.entry_point}(n):\n", task.canonical_solution, task.entry_point
    )
    profile = comparison_profile_for_task(task.entry_point, task.atol)
    record = generate_oracle_record(
        "T/X", "case-1", (21,), PROVENANCE_ORIGINAL, POOL_DEVELOPMENT, canonical_fn, profile
    )
    assert record.status == ORACLE_STATUS_SUCCESS
    assert record.expected_output == {"type": "int", "value": 42}
    assert record.failure_reason is None


def test_generate_oracle_record_classifies_exception_as_generation_failed() -> None:
    """A canonical solution that raises produces an explicit failure record,
    never a candidate-failure-shaped result and never a crash."""
    canonical_fn = build_canonical_callable(
        "def broken(n):\n", "    return 1 / 0\n", "broken"
    )
    profile = comparison_profile_for_task("broken", 0.0)
    record = generate_oracle_record(
        "T/BROKEN", "case-1", (1,), PROVENANCE_ORIGINAL, POOL_DEVELOPMENT, canonical_fn, profile
    )
    assert record.status == ORACLE_STATUS_GENERATION_FAILED
    assert record.expected_output is None
    assert record.failure_reason is not None
    assert "ZeroDivisionError" in record.failure_reason


def test_generate_oracle_record_classifies_timeout_as_generation_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A canonical solution that never returns is classified as a generation
    failure (timeout), never left hanging or silently misclassified."""
    monkeypatch.setattr(oracle_module, "ORACLE_CASE_TIME_LIMIT_SECONDS", 0.2)
    canonical_fn = build_canonical_callable(
        "def spins(n):\n", "    while True:\n        pass\n", "spins"
    )
    profile = comparison_profile_for_task("spins", 0.0)
    record = oracle_module.generate_oracle_record(
        "T/SPINS", "case-1", (1,), PROVENANCE_ORIGINAL, POOL_DEVELOPMENT, canonical_fn, profile
    )
    assert record.status == ORACLE_STATUS_GENERATION_FAILED
    assert record.failure_reason is not None
    assert "timed out" in record.failure_reason


def test_generate_oracle_record_deep_copies_mutable_args() -> None:
    """A canonical solution that mutates a mutable argument in place must
    never corrupt the caller's original args tuple."""
    canonical_fn = build_canonical_callable(
        "def mutates(lst):\n", "    lst.append(99)\n    return len(lst)\n", "mutates"
    )
    profile = comparison_profile_for_task("mutates", 0.0)
    original_list = [1, 2, 3]
    args = (original_list,)
    record = generate_oracle_record(
        "T/MUT", "case-1", args, PROVENANCE_ORIGINAL, POOL_DEVELOPMENT, canonical_fn, profile
    )
    assert record.status == ORACLE_STATUS_SUCCESS
    assert record.expected_output == {"type": "int", "value": 4}
    assert original_list == [1, 2, 3]  # untouched — canonical_fn only saw a deep copy


# --- build_oracle_artifacts: coverage, separation, supplementary handling ---


def test_build_oracle_artifacts_has_complete_coverage_no_duplicates() -> None:
    """Every eligible case gets exactly one oracle record; none are missing
    or duplicated in either the development or reference-only artifact."""
    result, experiment_manifest, validation_manifest = _build()

    dev_ids_by_task: dict[str, set[str]] = {}
    for record in result.development_oracle.records:
        dev_ids_by_task.setdefault(record.task_id, set()).add(record.case_id)
    ref_ids_by_task: dict[str, set[str]] = {}
    for record in result.reference_only_oracle.records:
        ref_ids_by_task.setdefault(record.task_id, set()).add(record.case_id)

    assert len(result.development_oracle.records) == len(
        {(r.task_id, r.case_id) for r in result.development_oracle.records}
    )
    assert len(result.reference_only_oracle.records) == len(
        {(r.task_id, r.case_id) for r in result.reference_only_oracle.records}
    )

    for partition in experiment_manifest.task_partitions:
        assert dev_ids_by_task[partition.task_id] == set(partition.development_case_ids)
        assert ref_ids_by_task[partition.task_id] == set(partition.reference_only_case_ids)

    validation_only_entry = next(
        t for t in validation_manifest.tasks if t.task_id == EXCLUDED_TASK_ID
    )
    assert {r.case_id for r in result.reference_validation_only_oracle.records} == set(
        validation_only_entry.case_ids
    )


def test_build_oracle_artifacts_pools_are_disjoint() -> None:
    """No case ever appears in more than one of the three physically
    separated artifacts."""
    result, _, _ = _build()
    dev = {(r.task_id, r.case_id) for r in result.development_oracle.records}
    ref = {(r.task_id, r.case_id) for r in result.reference_only_oracle.records}
    val = {(r.task_id, r.case_id) for r in result.reference_validation_only_oracle.records}
    assert not dev & ref
    assert not dev & val
    assert not ref & val


def test_build_oracle_artifacts_records_correct_pool_labels() -> None:
    """Every record in each artifact is tagged with that artifact's own pool."""
    result, _, _ = _build()
    assert all(r.pool == POOL_DEVELOPMENT for r in result.development_oracle.records)
    assert all(r.pool == POOL_REFERENCE_ONLY for r in result.reference_only_oracle.records)
    assert all(
        r.pool == POOL_REFERENCE_VALIDATION_ONLY
        for r in result.reference_validation_only_oracle.records
    )


def test_build_oracle_artifacts_all_records_succeed_for_well_behaved_canonical_solutions() -> None:
    """The happy path: no generation failures when every canonical solution behaves."""
    result, _, _ = _build()
    assert all(r.status == ORACLE_STATUS_SUCCESS for r in result.development_oracle.records)
    assert all(r.status == ORACLE_STATUS_SUCCESS for r in result.reference_only_oracle.records)


def test_build_oracle_artifacts_tolerates_original_provenance_generation_failure() -> None:
    """An original-provenance case that fails oracle generation is recorded
    explicitly, without aborting the whole build (unlike supplementary cases)."""
    task_id = "T/A"
    privileged_by_id, public_by_id, cases_by_task, args_by_task = _build_synthetic_corpus(
        [task_id, "T/B"]
    )
    # Swap in a canonical solution that raises on exactly one input; every
    # case here has PROVENANCE_ORIGINAL (see _cases_and_args), so this
    # exercises the "tolerated, recorded explicitly" path, not the
    # supplementary-case "abort the whole build" path.
    privileged_by_id[task_id] = _task(
        task_id,
        entry_point="t_a_flaky",
        canonical_solution="    if n == 3:\n        raise ValueError('boom')\n    return n * 2\n",
        base_input=tuple((n,) for n in range(100)),
    )
    public_by_id[task_id] = "def t_a_flaky(n):\n"

    provenance = load_provenance()
    experiment_manifest = build_primary_experiment_manifest(cases_by_task, provenance)
    validation_manifest = build_reference_validation_manifest(cases_by_task, provenance)
    result = build_oracle_artifacts(
        experiment_manifest,
        validation_manifest,
        cases_by_task,
        args_by_task,
        privileged_by_id,
        public_by_id,
        provenance,
    )
    all_records = list(result.development_oracle.records) + list(
        result.reference_only_oracle.records
    )
    failed = [r for r in all_records if r.status == ORACLE_STATUS_GENERATION_FAILED]
    assert len(failed) == 1
    assert failed[0].task_id == task_id
    assert failed[0].failure_reason is not None
    assert "ValueError" in failed[0].failure_reason


def test_build_oracle_artifacts_aborts_on_ambiguous_supplementary_case() -> None:
    """A supplementary-provenance case that fails oracle generation must abort
    the whole build, never be silently dropped or silently accepted."""
    task_id = "T/A"
    privileged_by_id, public_by_id, cases_by_task, args_by_task = _build_synthetic_corpus(
        [task_id, "T/B"]
    )
    flaky = _task(
        task_id,
        entry_point="t_a_flaky2",
        canonical_solution=(
            "    if n == 5:\n"
            "        raise ValueError('bad supplementary case')\n"
            "    return n * 2\n"
        ),
        base_input=tuple((n,) for n in range(100)),
    )
    privileged_by_id[task_id] = flaky
    public_by_id[task_id] = "def t_a_flaky2(n):\n"

    cases, args = _cases_and_args(flaky)
    # Mark case n=5 as supplementary provenance (as MEGB-03A.1 evidence would be).
    supplementary_case_id = stable_case_id(task_id, (5,))
    cases_by_task[task_id] = [
        CaseWithProvenance(
            case_id=c.case_id,
            provenance=(
                PROVENANCE_SUPPLEMENTARY if c.case_id == supplementary_case_id else c.provenance
            ),
        )
        for c in cases
    ]
    args_by_task[task_id] = args

    provenance = load_provenance()
    experiment_manifest = build_primary_experiment_manifest(cases_by_task, provenance)
    validation_manifest = build_reference_validation_manifest(cases_by_task, provenance)

    with pytest.raises(AmbiguousSupplementaryOracleError):
        build_oracle_artifacts(
            experiment_manifest,
            validation_manifest,
            cases_by_task,
            args_by_task,
            privileged_by_id,
            public_by_id,
            provenance,
        )


def test_build_oracle_artifacts_composite_manifest_never_leaks_privileged_case_ids() -> None:
    """The committed composite manifest must never carry reference-only or
    validation-only case IDs — only development-pool case IDs are ever
    committed/optimizer-visible, matching MEGB-03B's own boundary."""
    result, _, _ = _build()
    for task_entry in result.composite_manifest.tasks:
        for source in task_entry.sources:
            if source.oracle_artifact_id == DEVELOPMENT_ORACLE_ARTIFACT_ID:
                assert len(source.case_ids) == source.case_count
            else:
                assert source.case_ids == ()


def test_build_oracle_artifacts_composite_manifest_never_contains_expected_outputs() -> None:
    """No expected-output bytes anywhere in the composite manifest structure."""
    result, _, _ = _build()
    serialized = json.dumps(dataclasses.asdict(result.composite_manifest), default=str)
    assert "expected_output" not in serialized
    assert "status" not in serialized  # no oracle-record fields at all, just structure


@pytest.mark.integration
def test_build_oracle_artifacts_real_corpus_two_tasks_smoke() -> None:
    """Smoke-test against two real tasks (fast subset), confirming the real
    corpus's canonical solutions execute successfully end-to-end."""
    priv_all = {t.task_id: t for t in load_privileged_view()}
    pub_all = {t.task_id: t.prompt for t in load_public_view()}

    cases_by_task, _augmentation_results, args_by_task = gather_eligible_cases_and_args(
        priv_all, pub_all
    )
    # Restrict to a small, fast subset: two simple tasks plus HumanEval/39.
    subset_ids = ["HumanEval/0", "HumanEval/1", EXCLUDED_TASK_ID]
    cases_by_task = {tid: cases_by_task[tid] for tid in subset_ids}
    args_by_task = {tid: args_by_task[tid] for tid in subset_ids}
    privileged_by_id = {tid: priv_all[tid] for tid in subset_ids}
    public_by_id = {tid: pub_all[tid] for tid in subset_ids}

    provenance = load_provenance()
    experiment_manifest = build_primary_experiment_manifest(
        cases_by_task, provenance, excluded_task_id=EXCLUDED_TASK_ID
    )
    validation_manifest = build_reference_validation_manifest(cases_by_task, provenance)
    result = build_oracle_artifacts(
        experiment_manifest,
        validation_manifest,
        cases_by_task,
        args_by_task,
        privileged_by_id,
        public_by_id,
        provenance,
    )
    assert len(result.development_oracle.records) == 80  # 2 tasks * 40
    assert all(r.status == ORACLE_STATUS_SUCCESS for r in result.development_oracle.records)
    assert all(r.status == ORACLE_STATUS_SUCCESS for r in result.reference_only_oracle.records)
    assert all(
        r.status == ORACLE_STATUS_SUCCESS
        for r in result.reference_validation_only_oracle.records
    )


# --- unbounded_int_str_digits: confined scope, restored afterward -----------


def test_unbounded_int_str_digits_disables_limit_only_inside_the_with_block() -> None:
    """The guard is lifted only for the duration of the with-block, and the
    exact prior process value is restored on normal exit."""
    before = sys.get_int_max_str_digits()
    with unbounded_int_str_digits():
        assert sys.get_int_max_str_digits() == 0
        str(10**5000)  # would raise ValueError outside the with-block
    after = sys.get_int_max_str_digits()
    assert after == before


def test_unbounded_int_str_digits_restores_limit_even_if_the_block_raises() -> None:
    """A confined override is only real if it survives an exception inside
    the with-block — otherwise a failure mid-oracle-build would leak an
    unbounded limit into whatever code runs next in this process."""
    before = sys.get_int_max_str_digits()
    with pytest.raises(RuntimeError):
        with unbounded_int_str_digits():
            assert sys.get_int_max_str_digits() == 0
            raise RuntimeError("simulated failure mid-serialization")
    assert sys.get_int_max_str_digits() == before


def test_str_conversion_of_a_huge_int_fails_outside_the_context_manager() -> None:
    """Sanity check that the default guard is actually active in this test
    environment — otherwise the two tests above would trivially pass."""
    assert sys.get_int_max_str_digits() != 0
    with pytest.raises(ValueError):
        str(10**5000)


def test_build_oracle_artifacts_handles_huge_integer_output_and_restores_limit() -> None:
    """End-to-end: a canonical solution returning an integer far past the
    default digit guard still produces a valid oracle, and the process-wide
    limit is unchanged before vs. after the build."""
    before = sys.get_int_max_str_digits()

    task_id = "T/HUGE"
    privileged_by_id, public_by_id, cases_by_task, args_by_task = _build_synthetic_corpus(
        [task_id, "T/B"]
    )
    huge_int_task = _task(
        task_id,
        entry_point="t_huge",
        canonical_solution="    return 10 ** 5000\n",
        base_input=tuple((n,) for n in range(100)),
    )
    privileged_by_id[task_id] = huge_int_task
    public_by_id[task_id] = "def t_huge(n):\n"

    provenance = load_provenance()
    experiment_manifest = build_primary_experiment_manifest(cases_by_task, provenance)
    validation_manifest = build_reference_validation_manifest(cases_by_task, provenance)
    result = build_oracle_artifacts(
        experiment_manifest,
        validation_manifest,
        cases_by_task,
        args_by_task,
        privileged_by_id,
        public_by_id,
        provenance,
    )

    huge_task_records = [r for r in result.development_oracle.records if r.task_id == task_id]
    assert huge_task_records
    assert all(r.status == ORACLE_STATUS_SUCCESS for r in huge_task_records)
    assert huge_task_records[0].expected_output is not None
    assert huge_task_records[0].expected_output["value"] == 10**5000

    after = sys.get_int_max_str_digits()
    assert after == before
