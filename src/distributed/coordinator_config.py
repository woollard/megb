"""MEGB-03H.2C.3B.2B.2: typed, immutable coordinator configuration.

**MEGB-03H.2C.3B.2B.2 correction:** this type previously capped
``max_admitted_workers`` at construction time by
:data:`~src.distributed.personal_policy.PERSONAL_BOOTSTRAP_MAX_WORKERS` --
but that hardcodes the *personal*-environment ceiling into the
provider-neutral scheduling engine itself, which is wrong: the engine's own
bounded-concurrency mechanism (this config plus
:class:`~src.distributed.coordinator.Coordinator`'s own
``threading.Semaphore``) must support any explicitly bounded positive
concurrency, not just two, so a future, separately-gated non-personal
environment is never structurally prevented from running more workers by
this config type alone. ``max_admitted_workers`` here is now only required
to be a positive int -- no upper bound.

The personal-environment ceiling is enforced independently and unchanged,
in two places that were already correct before this correction and remain
untouched: (1) :class:`~src.distributed.personal_policy.PersonalEnvironmentPolicy`
itself refuses to construct with ``max_admitted_workers`` above
:data:`~src.distributed.personal_policy.PERSONAL_BOOTSTRAP_MAX_WORKERS`
when ``environment_class == PERSONAL_BOOTSTRAP``; (2)
:func:`~src.distributed.personal_policy.evaluate_admission` refuses any
work item whose ``requested_worker_count`` exceeds the policy's own
``max_admitted_workers``. What this correction adds is a **third**,
structural check, at :class:`~src.distributed.coordinator.Coordinator`
construction time (see that module): the coordinator's own
``config.max_admitted_workers`` must not exceed the *injected policy's*
``max_admitted_workers`` -- so a coordinator wired to a personal-bootstrap
policy can never be configured to run more than two concurrent workers,
rejected before any admission ever occurs, while a coordinator wired to a
policy with a higher ceiling (a synthetic test fixture only, never a real
company-authorization policy -- that remains a separately-gated, not-yet-
authorized concern) may run at a genuinely higher bounded concurrency."""

from dataclasses import dataclass

from src.distributed._checksums import (
    require_positive_int as _require_positive_int,
)


@dataclass(frozen=True)
class CoordinatorConfig:  # pylint: disable=too-many-instance-attributes
    """Bounded-scheduler configuration for one coordinator run.
    ``max_admitted_workers`` must be a positive int -- provider-neutral,
    with no upper bound of its own; see this module's own docstring for
    where the personal-environment ceiling is actually enforced."""

    max_admitted_workers: int
    max_in_flight_work: int
    lease_duration_ticks: int
    visibility_timeout_ticks: int
    heartbeat_interval_ticks: int
    audit_outbox_max_pending: int

    def __post_init__(self) -> None:
        _require_positive_int(self, "max_admitted_workers")
        _require_positive_int(self, "max_in_flight_work")
        _require_positive_int(self, "lease_duration_ticks")
        _require_positive_int(self, "visibility_timeout_ticks")
        _require_positive_int(self, "heartbeat_interval_ticks")
        _require_positive_int(self, "audit_outbox_max_pending")


__all__ = ["CoordinatorConfig"]
