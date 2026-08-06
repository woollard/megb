"""MEGB-03H.2C.3B.2C: shared accumulator for the offline end-to-end
qualification suite. Not a test module itself -- imported by
``test_offline_e2e_qualification.py``.

Each test function performs its own real, independent coordinator/worker
actions (in its own fresh environment) and contributes its own
measured/observed counts here. The final report-generation test reads
the accumulated totals -- never a hardcoded or asserted-in-advance
figure -- and builds the safe report from them."""

from dataclasses import dataclass, field


@dataclass
class QualificationRunAccumulator:
    """Every count and safe field the final offline E2E qualification
    report needs, accumulated across this suite's own test functions in
    execution order. Plain mutable counters -- no candidate content,
    exception text, or infrastructure identifier is ever accumulated
    here."""

    admitted_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    retried_count: int = 0
    cancelled_count: int = 0
    duplicate_delivery_count: int = 0
    redelivery_count: int = 0
    budget_requested_cents_total: int = 0
    budget_finalized_cents_total: int = 0
    budget_released_cents_total: int = 0
    audit_delivered_count: int = 0
    audit_abandoned_count: int = 0
    audit_still_pending_count: int = 0
    queue_unacknowledged_count: int = 0
    measured_peak_concurrency_personal: int = 0
    measured_peak_concurrency_generic: int = 0
    serial_vs_distributed_equivalent: bool | None = None
    generic_concurrency4_equivalent: bool | None = None
    run_context_checksum: str = ""
    qualification_identity_checksum: str = ""
    distributed_run_intent: str = ""
    qualifying_workload_class: str = ""
    qualification_gate_ready: bool | None = None
    worker_topology_provisioning_class_counts: tuple[tuple[str, int], ...] = field(
        default_factory=tuple
    )
    worker_topology_region_counts: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    worker_topology_machine_type_counts: tuple[tuple[str, int], ...] = field(default_factory=tuple)


ACCUMULATOR = QualificationRunAccumulator()
