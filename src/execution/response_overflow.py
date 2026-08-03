"""MEGB-03H.2C.1: typed, centralized recognition of the runner's existing
oversized-response protocol-error fallback (``src/execution/runner.py``'s
``main()``: when ``wire.serialize_response`` raises because the real result
exceeds ``max_response_bytes``, the runner substitutes a small
``PROTOCOL_ERROR`` response instead of a truncated/corrupt one).

Uses only information already present on the wire today: no new wire
field, no ``attempted_response_bytes``, no ``EXECUTION_PROTOCOL_VERSION``
bump, and no ``RunnerResponse``/runner-image change. Recognition is
anchored to ``ExecutionStatus.PROTOCOL_ERROR`` — a status the runner
*only* ever assigns to its own protocol handling
(``_protocol_error_response`` in ``runner.py``), never to a candidate
exception (those are always ``CANDIDATE_EXCEPTION``/``PROCESS_LIMIT``) —
so no candidate-controlled ``exception_message`` text can ever reach this
classifier under ``PROTOCOL_ERROR`` status. The message is additionally
matched against the runner's *exact* existing format
(``wire._dumps_and_check_size``'s ``"serialized {label} (...) exceeds
limit (...)"``, with ``label="response"``) rather than a loose substring
check, to avoid conflating it with the other ``ProtocolError`` messages
the same status can carry (e.g. an unsupported return-value type, or a
malformed/oversized *request*).
"""

import re
from enum import Enum

from src.execution.protocol import CandidateExecutionResult, ExecutionStatus

_PROTOCOL_ERROR_EXCEPTION_TYPE = "ProtocolError"

# Exactly the format produced by wire._dumps_and_check_size(..., label="response"):
# f"serialized {label} ({len(payload)} bytes) exceeds limit ({max_bytes} bytes)"
_RESPONSE_OVERFLOW_PATTERN = re.compile(
    r"^serialized response \(\d+ bytes\) exceeds limit \(\d+ bytes\)$"
)


class ResponseOverflowClassification(str, Enum):
    """Whether one invocation's terminal outcome was the runner's own
    oversized-response fallback."""

    NOT_OVERFLOWED = "NOT_OVERFLOWED"
    OVERFLOWED = "OVERFLOWED"


def classify_response_overflow(result: CandidateExecutionResult) -> ResponseOverflowClassification:
    """Classify whether ``result`` is the runner's oversized-response
    fallback, using only ``status``/``exception_type``/``exception_message``
    -- fields already present on the wire, never candidate-controlled
    under ``PROTOCOL_ERROR``."""
    if result.status != ExecutionStatus.PROTOCOL_ERROR:
        return ResponseOverflowClassification.NOT_OVERFLOWED
    if result.exception_type != _PROTOCOL_ERROR_EXCEPTION_TYPE:
        return ResponseOverflowClassification.NOT_OVERFLOWED
    if result.exception_message is None:
        return ResponseOverflowClassification.NOT_OVERFLOWED
    if not _RESPONSE_OVERFLOW_PATTERN.match(result.exception_message):
        return ResponseOverflowClassification.NOT_OVERFLOWED
    return ResponseOverflowClassification.OVERFLOWED
