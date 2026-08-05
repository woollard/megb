"""MEGB-03H.2C.3B.2A: construction/validation/round-trip and
admission-decision tests for :mod:`src.distributed.personal_policy`,
including the personal-bootstrap two-worker and $50 ceilings and the
privileged/real/production workload-refusal requirement."""

import dataclasses

import pytest

from src.distributed._checksums import (
    InvalidDistributedProvenanceError,
    UnsupportedDistributedOrchestrationSchemaVersionError,
)
from src.distributed.personal_policy import (
    PERSONAL_BOOTSTRAP_MAX_WORKERS,
    PERSONAL_BOOTSTRAP_SPENDING_CEILING_CENTS,
    AdmissionDecision,
    AdmissionRefusalReason,
    DataClassification,
    PersonalEnvironmentPolicy,
    WorkloadClass,
    evaluate_admission,
    personal_environment_policy_to_dict,
)
from src.distributed.provenance import EnvironmentClass
from tests._distributed_orchestration_fixtures import make_personal_environment_policy


def test_personal_environment_policy_constructs_and_computes_checksum() -> None:
    """Test personal environment policy constructs and computes checksum."""
    policy = make_personal_environment_policy()
    assert len(policy.policy_checksum) == 64


def test_personal_environment_policy_is_immutable() -> None:
    """Test personal environment policy is immutable."""
    policy = make_personal_environment_policy()
    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.max_admitted_workers = 99  # type: ignore[misc]


def test_personal_environment_policy_round_trips() -> None:
    """Test personal environment policy round trips."""
    policy = make_personal_environment_policy()
    data = personal_environment_policy_to_dict(policy)
    rebuilt = PersonalEnvironmentPolicy(
        distributed_orchestration_schema_version=data["distributed_orchestration_schema_version"],
        checksum_algorithm_version=data["checksum_algorithm_version"],
        environment_class=EnvironmentClass(data["environment_class"]),
        allowed_workload_classes=tuple(
            WorkloadClass(item) for item in data["allowed_workload_classes"]
        ),
        max_admitted_workers=data["max_admitted_workers"],
        spending_ceiling_cents=data["spending_ceiling_cents"],
        policy_checksum=data["policy_checksum"],
    )
    assert rebuilt == policy


# ---------------------------------------------------------------------------
# Personal-bootstrap ceilings -- technical, not merely documented, refusal
# ---------------------------------------------------------------------------


def test_personal_environment_policy_rejects_unsupported_schema_version() -> None:
    """Test personal environment policy rejects unsupported schema
    version."""
    with pytest.raises(UnsupportedDistributedOrchestrationSchemaVersionError):
        make_personal_environment_policy(
            distributed_orchestration_schema_version="stale-version"
        )


def test_personal_bootstrap_ceiling_constants_match_accepted_amendment() -> None:
    """Test personal bootstrap ceiling constants match accepted
    amendment (max 2 workers, $50 spending ceiling)."""
    assert PERSONAL_BOOTSTRAP_MAX_WORKERS == 2
    assert PERSONAL_BOOTSTRAP_SPENDING_CEILING_CENTS == 5000


def test_personal_bootstrap_policy_accepts_exactly_two_workers() -> None:
    """Test personal bootstrap policy accepts exactly two workers (the
    ceiling itself is an allowed value, not merely values below it)."""
    policy = make_personal_environment_policy(max_admitted_workers=2)
    assert policy.max_admitted_workers == 2


def test_personal_bootstrap_policy_rejects_more_than_two_workers() -> None:
    """Test personal bootstrap policy construction itself refuses more
    than 2 admitted workers -- a technical, not merely documented,
    refusal."""
    with pytest.raises(InvalidDistributedProvenanceError):
        make_personal_environment_policy(max_admitted_workers=3)


def test_personal_bootstrap_policy_accepts_exactly_fifty_dollar_ceiling() -> None:
    """Test personal bootstrap policy accepts exactly fifty dollar
    ceiling."""
    policy = make_personal_environment_policy(spending_ceiling_cents=5000)
    assert policy.spending_ceiling_cents == 5000


def test_personal_bootstrap_policy_rejects_ceiling_above_fifty_dollars() -> None:
    """Test personal bootstrap policy construction itself refuses a
    spending ceiling above $50 -- represented as a hard construction-time
    rejection, not a runtime check that could be skipped."""
    with pytest.raises(InvalidDistributedProvenanceError):
        make_personal_environment_policy(spending_ceiling_cents=5001)


def test_personal_bootstrap_policy_rejects_disallowed_workload_class() -> None:
    """Test personal bootstrap policy construction itself refuses any
    workload class outside the synthetic-smoke/synthetic-qualification-
    candidate allowlist -- e.g. CALIBRATION or PRODUCTION."""
    with pytest.raises(InvalidDistributedProvenanceError):
        make_personal_environment_policy(
            allowed_workload_classes=(WorkloadClass.CALIBRATION,)
        )


def test_company_playground_policy_may_exceed_personal_ceilings() -> None:
    """Test a COMPANY_PLAYGROUND policy is not subject to the personal-
    bootstrap ceilings -- the ceiling enforcement is conditional on
    environment_class, not a blanket limit."""
    policy = make_personal_environment_policy(
        environment_class=EnvironmentClass.COMPANY_PLAYGROUND,
        allowed_workload_classes=(WorkloadClass.CALIBRATION, WorkloadClass.PRODUCTION),
        max_admitted_workers=50,
        spending_ceiling_cents=150000,
    )
    assert policy.max_admitted_workers == 50
    assert policy.spending_ceiling_cents == 150000


def test_allowed_workload_classes_must_be_sorted() -> None:
    """Test allowed workload classes must be sorted for deterministic
    serialization."""
    with pytest.raises(InvalidDistributedProvenanceError):
        make_personal_environment_policy(
            allowed_workload_classes=(
                WorkloadClass.SYNTHETIC_SMOKE,
                WorkloadClass.SYNTHETIC_QUALIFICATION_CANDIDATE,
            )
        )


def test_allowed_workload_classes_rejects_duplicate() -> None:
    """Test allowed workload classes rejects duplicate."""
    with pytest.raises(InvalidDistributedProvenanceError):
        make_personal_environment_policy(
            allowed_workload_classes=(
                WorkloadClass.SYNTHETIC_SMOKE,
                WorkloadClass.SYNTHETIC_SMOKE,
            )
        )


# ---------------------------------------------------------------------------
# evaluate_admission -- refusal occurs before any work is admitted
# ---------------------------------------------------------------------------


def test_evaluate_admission_admits_valid_synthetic_request() -> None:
    """Test evaluate admission admits valid synthetic request."""
    policy = make_personal_environment_policy()
    decision = evaluate_admission(
        policy,
        WorkloadClass.SYNTHETIC_SMOKE,
        DataClassification.SYNTHETIC,
        requested_worker_count=2,
        estimated_cost_cents=1000,
    )
    assert decision.admitted is True
    assert not decision.refusal_reasons


def test_evaluate_admission_refuses_privileged_reference_data() -> None:
    """Test the personal environment refuses privileged reference
    evidence, canonical solutions, real candidate portfolios, and
    production-cache writes -- checked here via
    DataClassification.PRIVILEGED_REFERENCE."""
    policy = make_personal_environment_policy()
    decision = evaluate_admission(
        policy,
        WorkloadClass.SYNTHETIC_SMOKE,
        DataClassification.PRIVILEGED_REFERENCE,
        requested_worker_count=1,
        estimated_cost_cents=100,
    )
    assert decision.admitted is False
    assert AdmissionRefusalReason.DATA_CLASSIFICATION_REFUSED in decision.refusal_reasons


def test_evaluate_admission_refuses_real_candidate_portfolio_data() -> None:
    """Test evaluate admission refuses real candidate portfolio data."""
    policy = make_personal_environment_policy()
    decision = evaluate_admission(
        policy,
        WorkloadClass.SYNTHETIC_SMOKE,
        DataClassification.REAL_CANDIDATE_PORTFOLIO,
        requested_worker_count=1,
        estimated_cost_cents=100,
    )
    assert decision.admitted is False
    assert AdmissionRefusalReason.DATA_CLASSIFICATION_REFUSED in decision.refusal_reasons


def test_evaluate_admission_refuses_production_cache_data() -> None:
    """Test evaluate admission refuses production cache data."""
    policy = make_personal_environment_policy()
    decision = evaluate_admission(
        policy,
        WorkloadClass.SYNTHETIC_SMOKE,
        DataClassification.PRODUCTION_CACHE,
        requested_worker_count=1,
        estimated_cost_cents=100,
    )
    assert decision.admitted is False
    assert AdmissionRefusalReason.DATA_CLASSIFICATION_REFUSED in decision.refusal_reasons


def test_evaluate_admission_refuses_calibration_workload_class() -> None:
    """Test evaluate admission refuses a CALIBRATION workload class on a
    personal-bootstrap policy -- "None — no full calibration or
    experiment run"."""
    policy = make_personal_environment_policy()
    decision = evaluate_admission(
        policy,
        WorkloadClass.CALIBRATION,
        DataClassification.SYNTHETIC,
        requested_worker_count=1,
        estimated_cost_cents=100,
    )
    assert decision.admitted is False
    assert AdmissionRefusalReason.WORKLOAD_CLASS_NOT_ALLOWLISTED in decision.refusal_reasons


def test_evaluate_admission_refuses_production_workload_class() -> None:
    """Test evaluate admission refuses production workload class."""
    policy = make_personal_environment_policy()
    decision = evaluate_admission(
        policy,
        WorkloadClass.PRODUCTION,
        DataClassification.SYNTHETIC,
        requested_worker_count=1,
        estimated_cost_cents=100,
    )
    assert decision.admitted is False
    assert AdmissionRefusalReason.WORKLOAD_CLASS_NOT_ALLOWLISTED in decision.refusal_reasons


def test_evaluate_admission_refuses_worker_count_above_ceiling() -> None:
    """Test evaluate admission refuses worker count above ceiling."""
    policy = make_personal_environment_policy()
    decision = evaluate_admission(
        policy,
        WorkloadClass.SYNTHETIC_SMOKE,
        DataClassification.SYNTHETIC,
        requested_worker_count=3,
        estimated_cost_cents=100,
    )
    assert decision.admitted is False
    assert AdmissionRefusalReason.WORKER_COUNT_CEILING_EXCEEDED in decision.refusal_reasons


def test_evaluate_admission_refuses_cost_above_ceiling() -> None:
    """Test evaluate admission refuses cost above ceiling."""
    policy = make_personal_environment_policy()
    decision = evaluate_admission(
        policy,
        WorkloadClass.SYNTHETIC_SMOKE,
        DataClassification.SYNTHETIC,
        requested_worker_count=1,
        estimated_cost_cents=5001,
    )
    assert decision.admitted is False
    assert AdmissionRefusalReason.COST_CEILING_EXCEEDED in decision.refusal_reasons


def test_evaluate_admission_enumerates_every_applicable_reason() -> None:
    """Test evaluate_admission surfaces every applicable refusal reason
    in one evaluation, not just the first one found."""
    policy = make_personal_environment_policy()
    decision = evaluate_admission(
        policy,
        WorkloadClass.PRODUCTION,
        DataClassification.PRODUCTION_CACHE,
        requested_worker_count=10,
        estimated_cost_cents=100000,
    )
    assert decision.admitted is False
    assert set(decision.refusal_reasons) == {
        AdmissionRefusalReason.WORKLOAD_CLASS_NOT_ALLOWLISTED,
        AdmissionRefusalReason.DATA_CLASSIFICATION_REFUSED,
        AdmissionRefusalReason.WORKER_COUNT_CEILING_EXCEEDED,
        AdmissionRefusalReason.COST_CEILING_EXCEEDED,
    }


def test_admission_decision_rejects_admitted_true_with_reasons() -> None:
    """Test AdmissionDecision itself refuses to represent admitted=True
    alongside nonempty refusal_reasons -- never a partially-computed
    positive result."""
    with pytest.raises(InvalidDistributedProvenanceError):
        AdmissionDecision(
            admitted=True,
            refusal_reasons=(AdmissionRefusalReason.COST_CEILING_EXCEEDED,),
        )


def test_admission_decision_rejects_admitted_false_without_reasons() -> None:
    """Test admission decision rejects admitted false without reasons."""
    with pytest.raises(InvalidDistributedProvenanceError):
        AdmissionDecision(admitted=False, refusal_reasons=())


def test_evaluate_admission_creates_no_resource_and_authorizes_no_billing() -> None:
    """Test evaluate_admission is a pure function -- calling it twice
    with the same inputs produces an equal, independent result, and it
    has no side-effecting dependency (no queue/store/cloud call) to even
    observe."""
    policy = make_personal_environment_policy()
    first = evaluate_admission(
        policy, WorkloadClass.SYNTHETIC_SMOKE, DataClassification.SYNTHETIC, 1, 100
    )
    second = evaluate_admission(
        policy, WorkloadClass.SYNTHETIC_SMOKE, DataClassification.SYNTHETIC, 1, 100
    )
    assert first == second


# ---------------------------------------------------------------------------
# MEGB-03H.2C.3B.2B.1 correction: canonical integer cents, never a float, on
# the authorization/comparison path -- exact boundary behavior and explicit
# float rejection.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cents", [0, 1, 4999, 5000])
def test_evaluate_admission_accepts_cost_at_and_below_the_ceiling(cents: int) -> None:
    """Test evaluate_admission accepts every exact boundary value at or
    below the 5000-cent ceiling: 0, 1, 4999, and the ceiling itself
    (5000)."""
    policy = make_personal_environment_policy()
    decision = evaluate_admission(
        policy,
        WorkloadClass.SYNTHETIC_SMOKE,
        DataClassification.SYNTHETIC,
        requested_worker_count=1,
        estimated_cost_cents=cents,
    )
    assert decision.admitted is True


def test_evaluate_admission_rejects_cost_one_cent_above_the_ceiling() -> None:
    """Test evaluate_admission refuses exactly one cent above the
    5000-cent ceiling (5001), the exact opposite boundary from the
    accepted-at-ceiling case above."""
    policy = make_personal_environment_policy()
    decision = evaluate_admission(
        policy,
        WorkloadClass.SYNTHETIC_SMOKE,
        DataClassification.SYNTHETIC,
        requested_worker_count=1,
        estimated_cost_cents=5001,
    )
    assert decision.admitted is False
    assert AdmissionRefusalReason.COST_CEILING_EXCEEDED in decision.refusal_reasons


def test_evaluate_admission_rejects_a_float_estimated_cost() -> None:
    """Test evaluate_admission raises rather than silently accepting a
    binary floating-point ``estimated_cost_cents`` -- the authorization
    path admits only ``int``, never ``float``, even when the float value
    is numerically integral (e.g. ``100.0``)."""
    policy = make_personal_environment_policy()
    with pytest.raises(InvalidDistributedProvenanceError):
        evaluate_admission(
            policy,
            WorkloadClass.SYNTHETIC_SMOKE,
            DataClassification.SYNTHETIC,
            requested_worker_count=1,
            estimated_cost_cents=100.0,  # type: ignore[arg-type]
        )


def test_evaluate_admission_rejects_a_negative_estimated_cost() -> None:
    """Test evaluate_admission rejects a negative cost outright rather
    than silently treating it as always-admitted."""
    policy = make_personal_environment_policy()
    with pytest.raises(InvalidDistributedProvenanceError):
        evaluate_admission(
            policy,
            WorkloadClass.SYNTHETIC_SMOKE,
            DataClassification.SYNTHETIC,
            requested_worker_count=1,
            estimated_cost_cents=-1,
        )


def test_evaluate_admission_rejects_a_boolean_estimated_cost() -> None:
    """Test evaluate_admission rejects ``bool`` (a ``int`` subclass in
    Python) as an ambiguous, disallowed conversion for
    ``estimated_cost_cents``."""
    policy = make_personal_environment_policy()
    with pytest.raises(InvalidDistributedProvenanceError):
        evaluate_admission(
            policy,
            WorkloadClass.SYNTHETIC_SMOKE,
            DataClassification.SYNTHETIC,
            requested_worker_count=1,
            estimated_cost_cents=True,
        )


def test_personal_environment_policy_rejects_a_float_spending_ceiling() -> None:
    """Test PersonalEnvironmentPolicy construction itself refuses a
    binary floating-point ``spending_ceiling_cents`` -- canonical integer
    currency units are required at construction time, not merely at
    comparison time."""
    with pytest.raises(InvalidDistributedProvenanceError):
        make_personal_environment_policy(spending_ceiling_cents=5000.0)


def test_personal_environment_policy_rejects_a_negative_spending_ceiling() -> None:
    """Test personal environment policy rejects a negative spending
    ceiling."""
    with pytest.raises(InvalidDistributedProvenanceError):
        make_personal_environment_policy(spending_ceiling_cents=-1)


def test_personal_environment_policy_rejects_the_stale_v1_schema_version_literal() -> None:
    """Test personal environment policy rejects the stale
    MEGB-03H.2C.3B.2A v1 schema-version literal -- v1's
    ``PersonalEnvironmentPolicy`` had a ``spending_ceiling_usd: float``
    field; a payload still stamped with the exact prior v1 string must
    be rejected under the v2 field shape, never silently
    reinterpreted."""
    with pytest.raises(UnsupportedDistributedOrchestrationSchemaVersionError):
        make_personal_environment_policy(
            distributed_orchestration_schema_version="megb-03h2c3b2a-distributed-orchestration-v1"
        )


def test_personal_environment_policy_has_no_float_typed_field() -> None:
    """Test PersonalEnvironmentPolicy has no ``float``-typed field
    anywhere -- a structural guarantee, not merely a construction-time
    check, that the authorization path never carries binary
    floating-point currency."""
    for field in dataclasses.fields(PersonalEnvironmentPolicy):
        assert field.type is not float, (
            f"field {field.name!r} is typed float -- canonical integer cents required"
        )
