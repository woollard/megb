"""MEGB-03H.2C.3B.2B.2: typed, immutable coordinator configuration.

``max_admitted_workers`` is capped at construction time by
:data:`~src.distributed.personal_policy.PERSONAL_BOOTSTRAP_MAX_WORKERS` --
a technical, not merely documented, refusal, exactly mirroring
:class:`~src.distributed.personal_policy.PersonalEnvironmentPolicy`'s own
established discipline for the same ceiling."""

from dataclasses import dataclass

from src.distributed._checksums import (
    InvalidDistributedProvenanceError,
    require_positive_int as _require_positive_int,
)
from src.distributed.personal_policy import PERSONAL_BOOTSTRAP_MAX_WORKERS


@dataclass(frozen=True)
class CoordinatorConfig:  # pylint: disable=too-many-instance-attributes
    """Bounded-scheduler configuration for one coordinator run."""

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
        if self.max_admitted_workers > PERSONAL_BOOTSTRAP_MAX_WORKERS:
            raise InvalidDistributedProvenanceError(
                f"personal-environment coordinator may not admit more than "
                f"{PERSONAL_BOOTSTRAP_MAX_WORKERS} concurrent workers, got "
                f"{self.max_admitted_workers}"
            )


__all__ = ["CoordinatorConfig"]
