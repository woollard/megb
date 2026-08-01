"""MEGB-03C: construct the privileged expected-output oracle.

For every case admitted by MEGB-03B's frozen partition (163-task
development/reference-only split, plus ``HumanEval/39``'s 12-case
validation-only domain), executes the corrected, pinned EvalPlus canonical
solution against that case's (deep-copied) input and records the result as
an :class:`OracleRecord` — the trusted expected output later measurement
systems compare candidate output against.

Three physically separated artifacts are produced, matching the access
boundaries different consumers are authorized to cross:

* ``development_oracle`` — the 40 development cases per experimental task;
  intended only for the trusted side of MEGB-04.
* ``reference_only_oracle`` — every reference-only case per experimental
  task; intended only for S\\*.
* ``reference_validation_only_oracle`` — ``HumanEval/39``'s complete
  12-case domain; intended only for the 164-task validation workflow
  (MEGB-03D).

A committed composite manifest (:class:`ReferenceValidationCompositeManifest`)
indexes all three without duplicating expected-output bytes, and — matching
the boundary MEGB-03B already established (only development-pool case IDs
are ever optimizer/committed-visible) — never lists reference-only or
``HumanEval/39`` case IDs itself, only their counts.

Comparison semantics are never reimplemented from scratch: EvalPlus's own
``is_floats``/``_poly`` (from the pinned ``evalplus==0.3.1``) are reused
directly for the tolerance and HumanEval/32 (``find_zero``) special-oracle
checks (see :func:`compare_outputs`), and canonical-solution execution
mirrors ``evalplus.gen.util.trusted_exec`` (deep-copy each input before the
call; no sandboxing, since this is trusted reference code, matching
upstream's own precedent — not candidate code, which this subtask never
executes).
"""

import contextlib
import copy
import dataclasses
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterator, Mapping, Sequence

import numpy as np
from evalplus.eval import is_floats
from evalplus.eval._special_oracle import _poly
from evalplus.eval.utils import TimeoutException, time_limit

from src.dataset import DatasetProvenance, PrivilegedTaskView
from src.execution.wire import encode_value
from src.reference.augmentation import PROVENANCE_SUPPLEMENTARY, build_canonical_callable
from src.reference.partition import (
    EXCLUDED_TASK_ID,
    CaseWithProvenance,
    PrimaryExperimentManifest,
    ReferenceValidationManifest,
)

ORACLE_ALGORITHM_VERSION = "oracle-v1"
COMPARISON_PROFILE_VERSION = "comparison-profile-v1"
ORACLE_CASE_TIME_LIMIT_SECONDS = 10.0

@contextlib.contextmanager
def unbounded_int_str_digits() -> Iterator[None]:
    """Temporarily disable CPython's integer-string-conversion-length guard.

    Some canonical solutions produce legitimate, very large integers on
    their largest ``plus_input`` cases (e.g. HumanEval/83 on n=1_000_000
    returns a ~1,000,002-digit int; HumanEval/139 similarly for its larger
    inputs). Python 3.11+ refuses to ``str()``/JSON-serialize *or* parse an
    int past 4300 digits by default (a DoS hardening measure) — since these
    are genuine pinned-benchmark values, not attacker-supplied input, this
    disables that limit for the duration of the wrapped call only.

    Confined to trusted oracle serialization/deserialization: callers wrap
    only the specific operation that may touch a huge int (building/writing/
    verifying an oracle artifact), never left enabled process-wide, so it
    never weakens the guard for unrelated code sharing this process (e.g.
    untrusted candidate execution elsewhere). The prior value is restored on
    exit even if the wrapped code raises.
    """
    previous = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(0)
    try:
        yield
    finally:
        sys.set_int_max_str_digits(previous)


COMPARISON_KIND_DEFAULT = "default_exact_or_tolerance"
COMPARISON_KIND_FIND_ZERO = "special_oracle_find_zero"
# HumanEval/32; EvalPlus's only HumanEval-specific special oracle (see
# evalplus.eval.unsafe_execute's `if dataset == "humaneval":` branch). MBPP's
# special oracles never apply — MEGB only evaluates HumanEval.
_FIND_ZERO_ENTRY_POINT = "find_zero"

ORACLE_STATUS_SUCCESS = "success"
ORACLE_STATUS_GENERATION_FAILED = "generation_failed"

POOL_DEVELOPMENT = "development"
POOL_REFERENCE_ONLY = "reference_only"
POOL_REFERENCE_VALIDATION_ONLY = "reference_validation_only"

DEVELOPMENT_ORACLE_ARTIFACT_ID = "development_oracle"
REFERENCE_ONLY_ORACLE_ARTIFACT_ID = "reference_only_oracle"
REFERENCE_VALIDATION_ONLY_ORACLE_ARTIFACT_ID = "reference_validation_only_oracle"
COMPOSITE_MANIFEST_KIND = "reference_validation_composite_manifest"


class AmbiguousSupplementaryOracleError(ValueError):
    """A MEGB-03A.1 supplementary case could not produce an unambiguous oracle.

    Per the MEGB-03C execution amendment, supplementary evidence gets
    stricter treatment than upstream EvalPlus cases: a generation failure
    here aborts the whole oracle build rather than being recorded as a
    per-case failure (as an original-provenance case's failure would be),
    since these inputs are novel — not vetted at scale upstream — and must
    never be silently dropped or silently accepted.
    """


@dataclass(frozen=True)
class ComparisonProfile:
    """How to compare an actual output to an oracle record's expected output.

    Mirrors EvalPlus's own comparison exactly (``evalplus.eval.unsafe_execute``
    in the pinned ``evalplus==0.3.1``), not a reimplementation from scratch:
    ``kind=COMPARISON_KIND_DEFAULT`` is exact-match-or-tolerance (enforcing
    ``atol=1e-6`` for float-valued outputs when the task's own ``atol`` is
    0, then ``numpy.allclose(rtol=1e-7, atol=atol)``); the one HumanEval
    task whose ``entry_point`` is ``find_zero`` (HumanEval/32) uses
    EvalPlus's polynomial postcondition oracle instead of a fixed expected
    value.
    """

    kind: str
    atol: float
    profile_version: str = COMPARISON_PROFILE_VERSION


def comparison_profile_for_task(entry_point: str, atol: float) -> ComparisonProfile:
    """The comparison profile EvalPlus uses for a task with this entry_point/atol."""
    if entry_point == _FIND_ZERO_ENTRY_POINT:
        return ComparisonProfile(kind=COMPARISON_KIND_FIND_ZERO, atol=atol)
    return ComparisonProfile(kind=COMPARISON_KIND_DEFAULT, atol=atol)


def compare_outputs(  # pylint: disable=too-many-return-statements
    profile: ComparisonProfile, args: tuple[Any, ...], actual: Any, expected: Any
) -> bool:
    """Compare a candidate's actual output to this case's oracle expected output.

    Never a universal ``==``: reimplements the exact EvalPlus
    ``unsafe_execute`` comparison procedure for the HumanEval dataset —
    ``find_zero``'s polynomial postcondition (independent of ``expected``),
    otherwise exact-match falling through to atol-tolerant
    ``numpy.allclose`` for non-exact numeric/sequence outputs.
    """
    if profile.kind == COMPARISON_KIND_FIND_ZERO:
        (coefficients,) = args
        return bool(abs(_poly(coefficients, actual)) <= profile.atol)

    if actual == expected:
        return True

    atol = profile.atol
    if atol == 0 and is_floats(expected):
        atol = 1e-6  # enforce a tolerance for float comparison, matching EvalPlus
    if atol == 0:
        return False
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, (list, tuple)) and len(actual) != len(expected):
        return False
    try:
        return bool(np.allclose(actual, expected, rtol=1e-07, atol=atol))
    except (TypeError, ValueError):
        return False


@dataclass(frozen=True)
class OracleRecord:
    """One case's trusted expected-output record.

    ``expected_output`` is the tagged-JSON representation (see
    ``src.execution.wire.encode_value``) of the canonical solution's actual
    return value — present only when ``status == ORACLE_STATUS_SUCCESS``.
    For the find_zero/HumanEval/32 task this value is still the canonical
    solution's own literal return value, not a postcondition result;
    comparison-time consumers must dispatch on ``comparison_profile_kind``
    (see :func:`compare_outputs`) rather than assume direct equality
    against it.
    """

    task_id: str
    case_id: str
    pool: str
    provenance: str
    comparison_profile_kind: str
    status: str
    expected_output: Mapping[str, Any] | None
    failure_reason: str | None


def _canonical_callable(privileged: PrivilegedTaskView, prompt: str) -> Callable[..., Any]:
    return build_canonical_callable(prompt, privileged.canonical_solution, privileged.entry_point)


def generate_oracle_record(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    task_id: str,
    case_id: str,
    args: tuple[Any, ...],
    provenance: str,
    pool: str,
    canonical_fn: Callable[..., Any],
    profile: ComparisonProfile,
) -> OracleRecord:
    """Execute the pinned canonical solution against one (deep-copied) case.

    Deep-copies ``args`` before the call — mirroring EvalPlus's own
    ``evalplus.gen.util.trusted_exec`` — so a canonical solution that
    mutates a mutable argument (list/dict) can never corrupt the shared,
    frozen case-input data reused elsewhere in this project. A per-case
    time limit and a broad exception catch (matching EvalPlus's own
    ``unsafe_execute``, which must tolerate arbitrary failures from
    executed code) both map to an explicit ``ORACLE_STATUS_GENERATION_FAILED``
    record — a generation failure is never silently coerced into a
    placeholder expected output or conflated with a candidate failure.
    """
    # pylint: disable=no-else-return
    # The else-branch is deliberate: it scopes the success path so that a
    # failure raised while constructing the *success* OracleRecord itself
    # is never mis-caught by the except clauses above (which are only for
    # canonical_fn/encode_value failures).
    try:
        with time_limit(ORACLE_CASE_TIME_LIMIT_SECONDS):
            actual = canonical_fn(*copy.deepcopy(args))
        encoded = encode_value(actual)
    except TimeoutException:
        return OracleRecord(
            task_id=task_id,
            case_id=case_id,
            pool=pool,
            provenance=provenance,
            comparison_profile_kind=profile.kind,
            status=ORACLE_STATUS_GENERATION_FAILED,
            expected_output=None,
            failure_reason=f"timed out after {ORACLE_CASE_TIME_LIMIT_SECONDS}s",
        )
    except BaseException as exc:  # pylint: disable=broad-exception-caught
        return OracleRecord(
            task_id=task_id,
            case_id=case_id,
            pool=pool,
            provenance=provenance,
            comparison_profile_kind=profile.kind,
            status=ORACLE_STATUS_GENERATION_FAILED,
            expected_output=None,
            failure_reason=f"{type(exc).__name__}: {exc}",
        )
    else:
        return OracleRecord(
            task_id=task_id,
            case_id=case_id,
            pool=pool,
            provenance=provenance,
            comparison_profile_kind=profile.kind,
            status=ORACLE_STATUS_SUCCESS,
            expected_output=encoded,
            failure_reason=None,
        )


@dataclass(frozen=True)
class OracleArtifact:
    """One physically separated privileged oracle file."""

    artifact_kind: str
    dataset_provenance: DatasetProvenance
    partition_checksum: str
    comparison_profile_version: str
    records: tuple[OracleRecord, ...]
    generated_at: str
    artifact_checksum: str = ""


@dataclass(frozen=True)
class CompositeSourceRef:
    """One artifact's contribution to a composite task entry.

    ``case_ids`` is populated only for the development-pool source — the
    only case IDs MEGB-03B ever made committed/optimizer-visible.
    Reference-only and reference-validation-only sources leave it empty and
    rely on ``case_count``, preserving that same boundary here.
    """

    oracle_artifact_id: str
    case_count: int
    case_ids: tuple[str, ...]


@dataclass(frozen=True)
class CompositeTaskEntry:
    """One task's entry in the composite manifest: where its cases live."""

    task_id: str
    pool_kind: str
    sources: tuple[CompositeSourceRef, ...]


@dataclass(frozen=True)
class ReferenceValidationCompositeManifest:
    """Committed, 164-task index over the three privileged oracle artifacts.

    References case counts (and, for the development pool only, case IDs)
    without duplicating any expected-output bytes.
    """

    manifest_kind: str
    dataset_provenance: DatasetProvenance
    experiment_partition_checksum: str
    validation_partition_checksum: str
    tasks: tuple[CompositeTaskEntry, ...]
    generated_at: str
    manifest_checksum: str = ""


@dataclass(frozen=True)
class OracleBuildResult:
    """The complete output of one oracle-construction run."""

    development_oracle: OracleArtifact
    reference_only_oracle: OracleArtifact
    reference_validation_only_oracle: OracleArtifact
    composite_manifest: ReferenceValidationCompositeManifest


class UnresolvedGenerationFailureError(ValueError):
    """A build has one or more unresolved oracle-generation failures.

    Raised by the release step (``oracle_lock.write_privileged_oracle_artifacts``
    / ``oracle_lock.verify_oracle_against_lock``), never by
    :func:`build_oracle_artifacts` itself: constructing the in-memory/
    diagnostic ``OracleBuildResult`` may complete even with an
    original-provenance generation failure recorded explicitly (see
    ``build_oracle_artifacts``'s docstring), but that result must never be
    frozen into a privileged release or treated as verified — this is the
    gate that enforces it.
    """


def find_generation_failures(build_result: OracleBuildResult) -> tuple[OracleRecord, ...]:
    """Every record across all three artifacts whose oracle generation failed.

    Empty means the build is release-ready. Supplementary-provenance
    failures can never appear here in practice — they already abort
    :func:`build_oracle_artifacts` before it returns — but every record is
    still checked regardless of provenance, so this stays correct even if
    that upstream invariant ever changed.
    """
    all_records = (
        build_result.development_oracle.records
        + build_result.reference_only_oracle.records
        + build_result.reference_validation_only_oracle.records
    )
    return tuple(r for r in all_records if r.status != ORACLE_STATUS_SUCCESS)


def require_release_ready(build_result: OracleBuildResult) -> None:
    """Raise ``UnresolvedGenerationFailureError`` if any record failed generation.

    Reports only identity fields (task_id, case_id, pool, failure_reason) —
    there is no expected-output content to leak for a failed record in the
    first place, but this is still explicit about never doing so.
    """
    failures = find_generation_failures(build_result)
    if failures:
        details = ", ".join(
            f"{r.task_id}/{r.case_id} ({r.pool}): {r.failure_reason}" for r in failures
        )
        raise UnresolvedGenerationFailureError(
            f"{len(failures)} case(s) have an unresolved oracle-generation "
            f"failure; refusing to release or verify as valid: {details}"
        )


def _stable_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Strip volatile fields before hashing (mirrors partition.py's own fix
    for the same class of cross-process determinism bug: a checksum field
    hashing itself, and a wall-clock timestamp embedded unstripped)."""
    # pylint: disable=duplicate-code
    # Deliberately mirrors partition_lock.py's own stripping helper (same
    # class of determinism bug fix); consolidating both isn't authorized in
    # this subtask — see oracle_lock.py's module docstring.
    stripped = dict(payload)
    for checksum_field in ("artifact_checksum", "manifest_checksum"):
        if checksum_field in stripped:
            stripped[checksum_field] = ""
    stripped["generated_at"] = ""
    dataset_provenance_dict = stripped.get("dataset_provenance")
    if isinstance(dataset_provenance_dict, dict):
        dataset_provenance_dict = dict(dataset_provenance_dict)
        dataset_provenance_dict["loaded_at"] = ""
        stripped["dataset_provenance"] = dataset_provenance_dict
    return stripped


def _checksum_payload(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _finalize_artifact(
    artifact_kind: str,
    dataset_provenance: DatasetProvenance,
    partition_checksum: str,
    records: tuple[OracleRecord, ...],
    generated_at: str,
) -> OracleArtifact:
    artifact = OracleArtifact(
        artifact_kind=artifact_kind,
        dataset_provenance=dataset_provenance,
        partition_checksum=partition_checksum,
        comparison_profile_version=COMPARISON_PROFILE_VERSION,
        records=records,
        generated_at=generated_at,
    )
    checksum = _checksum_payload(_stable_payload(dataclasses.asdict(artifact)))
    return dataclasses.replace(artifact, artifact_checksum=checksum)


def _finalize_composite(
    dataset_provenance: DatasetProvenance,
    experiment_partition_checksum: str,
    validation_partition_checksum: str,
    tasks: tuple[CompositeTaskEntry, ...],
    generated_at: str,
) -> ReferenceValidationCompositeManifest:
    manifest = ReferenceValidationCompositeManifest(
        manifest_kind=COMPOSITE_MANIFEST_KIND,
        dataset_provenance=dataset_provenance,
        experiment_partition_checksum=experiment_partition_checksum,
        validation_partition_checksum=validation_partition_checksum,
        tasks=tasks,
        generated_at=generated_at,
    )
    checksum = _checksum_payload(_stable_payload(dataclasses.asdict(manifest)))
    return dataclasses.replace(manifest, manifest_checksum=checksum)


def build_oracle_artifacts(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    experiment_manifest: PrimaryExperimentManifest,
    validation_manifest: ReferenceValidationManifest,
    cases_by_task: Mapping[str, Sequence[CaseWithProvenance]],
    args_by_task: Mapping[str, Mapping[str, tuple[Any, ...]]],
    privileged_by_id: Mapping[str, PrivilegedTaskView],
    public_by_id: Mapping[str, str],
    dataset_provenance: DatasetProvenance,
) -> OracleBuildResult:
    """Construct all three privileged oracle artifacts plus the composite manifest.

    Raises ``AmbiguousSupplementaryOracleError`` immediately (aborting the
    whole build, writing nothing) the first time a supplementary-provenance
    case fails oracle generation. Original-provenance (upstream EvalPlus)
    failures are tolerated as explicit ``ORACLE_STATUS_GENERATION_FAILED``
    records rather than aborting — EvalPlus's own base/plus inputs are
    vetted at benchmark scale, so a failure there is recorded for
    visibility rather than treated as build-fatal.
    """
    provenance_by_case: dict[str, dict[str, str]] = {
        task_id: {c.case_id: c.provenance for c in cases}
        for task_id, cases in cases_by_task.items()
    }

    canonical_fn_cache: dict[str, Callable[..., Any]] = {}
    profile_cache: dict[str, ComparisonProfile] = {}

    def _fn_and_profile(task_id: str) -> tuple[Callable[..., Any], ComparisonProfile]:
        if task_id not in canonical_fn_cache:
            privileged = privileged_by_id[task_id]
            canonical_fn_cache[task_id] = _canonical_callable(privileged, public_by_id[task_id])
            profile_cache[task_id] = comparison_profile_for_task(
                privileged.entry_point, privileged.atol
            )
        return canonical_fn_cache[task_id], profile_cache[task_id]

    def _generate(task_id: str, case_id: str, pool: str) -> OracleRecord:
        canonical_fn, profile = _fn_and_profile(task_id)
        args = args_by_task[task_id][case_id]
        provenance = provenance_by_case[task_id][case_id]
        record = generate_oracle_record(
            task_id, case_id, args, provenance, pool, canonical_fn, profile
        )
        if provenance == PROVENANCE_SUPPLEMENTARY and record.status != ORACLE_STATUS_SUCCESS:
            raise AmbiguousSupplementaryOracleError(
                f"{task_id}/{case_id}: supplementary case failed oracle generation "
                f"({record.failure_reason}) — refusing to silently drop or continue."
            )
        return record

    development_records: list[OracleRecord] = []
    reference_only_records: list[OracleRecord] = []
    composite_tasks: list[CompositeTaskEntry] = []

    for partition in experiment_manifest.task_partitions:
        task_id = partition.task_id
        dev_ids = list(partition.development_case_ids)
        ref_ids = list(partition.reference_only_case_ids)
        development_records.extend(_generate(task_id, cid, POOL_DEVELOPMENT) for cid in dev_ids)
        reference_only_records.extend(
            _generate(task_id, cid, POOL_REFERENCE_ONLY) for cid in ref_ids
        )
        composite_tasks.append(
            CompositeTaskEntry(
                task_id=task_id,
                pool_kind="experimental",
                sources=(
                    CompositeSourceRef(
                        oracle_artifact_id=DEVELOPMENT_ORACLE_ARTIFACT_ID,
                        case_count=len(dev_ids),
                        case_ids=tuple(dev_ids),
                    ),
                    CompositeSourceRef(
                        oracle_artifact_id=REFERENCE_ONLY_ORACLE_ARTIFACT_ID,
                        case_count=len(ref_ids),
                        case_ids=(),
                    ),
                ),
            )
        )

    validation_only_entry = next(
        t for t in validation_manifest.tasks if t.task_id == EXCLUDED_TASK_ID
    )
    validation_only_records = [
        _generate(EXCLUDED_TASK_ID, cid, POOL_REFERENCE_VALIDATION_ONLY)
        for cid in validation_only_entry.case_ids
    ]
    composite_tasks.append(
        CompositeTaskEntry(
            task_id=EXCLUDED_TASK_ID,
            pool_kind="validation_only",
            sources=(
                CompositeSourceRef(
                    oracle_artifact_id=REFERENCE_VALIDATION_ONLY_ORACLE_ARTIFACT_ID,
                    case_count=len(validation_only_records),
                    case_ids=(),
                ),
            ),
        )
    )

    generated_at = datetime.now(timezone.utc).isoformat()

    # Checksumming below serializes each artifact's records to JSON, which
    # may include a huge int (see unbounded_int_str_digits's docstring) —
    # scoped tightly to just this checksum computation, restored on exit.
    with unbounded_int_str_digits():
        development_oracle = _finalize_artifact(
            DEVELOPMENT_ORACLE_ARTIFACT_ID,
            dataset_provenance,
            experiment_manifest.manifest_checksum,
            tuple(development_records),
            generated_at,
        )
        reference_only_oracle = _finalize_artifact(
            REFERENCE_ONLY_ORACLE_ARTIFACT_ID,
            dataset_provenance,
            experiment_manifest.manifest_checksum,
            tuple(reference_only_records),
            generated_at,
        )
        reference_validation_only_oracle = _finalize_artifact(
            REFERENCE_VALIDATION_ONLY_ORACLE_ARTIFACT_ID,
            dataset_provenance,
            validation_manifest.manifest_checksum,
            tuple(validation_only_records),
            generated_at,
        )
        composite_manifest = _finalize_composite(
            dataset_provenance,
            experiment_manifest.manifest_checksum,
            validation_manifest.manifest_checksum,
            tuple(sorted(composite_tasks, key=lambda t: t.task_id)),
            generated_at,
        )

    return OracleBuildResult(
        development_oracle=development_oracle,
        reference_only_oracle=reference_only_oracle,
        reference_validation_only_oracle=reference_validation_only_oracle,
        composite_manifest=composite_manifest,
    )
