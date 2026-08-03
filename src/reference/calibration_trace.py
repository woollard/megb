"""MEGB-03H.2A: durable, single-process, append-only JSONL trace storage
for calibration records.

Implements the design doc's chosen trace-storage strategy
(``docs/reference/megb-03h1-calibration-design.md`` §10, and the ticket's
"Approved MEGB-03H Planning Amendment" §3's durability requirement): design
(b), append-only JSONL with ``flush()``+``fsync()`` after every append, plus
startup repair that verifies each record's checksum and truncates the file
to the last verified newline before any further append. An in-process
lock (mirroring ``ReferenceOrchestrator``'s own ``_io_lock``) serializes
concurrent-execution writes into one file; multi-process/multi-host writers
remain out of scope, per the Amendment.

One file mixes both :class:`~src.reference.calibration_schema.CalibrationInvocationRecord`
and :class:`~src.reference.calibration_schema.CalibrationTaskEvaluationRecord`
entries (one per stage, per the design doc), each wrapped in a small typed
envelope so a reader can tell the two apart and verify each line
independently before ever touching the payload it wraps.

**Corruption handling is deliberately asymmetric**: a non-trailing
(interior) line that fails to parse or fails its checksum is never
silently repaired -- :meth:`CalibrationTraceStore.repair` raises
:class:`CalibrationTraceCorruptionError` instead, since interior corruption
can only mean something wrote to (or damaged) the middle of an
append-only file, an integrity violation no automatic recovery should
paper over. Only a genuinely trailing, incomplete/corrupt line (the shape
a crash mid-``write()`` produces) is ever truncated away automatically.
:meth:`CalibrationTraceStore.read_all` never repairs -- it raises on *any*
invalid line, whether interior or trailing, so a caller cannot accidentally
read past unrepaired trailing corruption without calling :meth:`repair`
first.
"""

import json
import os
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from src.reference.calibration_schema import (
    CalibrationInvocationRecord,
    CalibrationTaskEvaluationRecord,
    calibration_invocation_record_from_dict,
    calibration_invocation_record_to_dict,
    calibration_task_evaluation_record_from_dict,
    calibration_task_evaluation_record_to_dict,
    checksum_of,
)

TRACE_ENVELOPE_SCHEMA_VERSION = "megb-03h-calibration-trace-envelope-v1"

DEFAULT_CALIBRATION_TRACE_DIR = Path("artifacts/privileged/reference/calibration")

_TraceReadResult = tuple[
    tuple[CalibrationInvocationRecord, ...], tuple[CalibrationTaskEvaluationRecord, ...]
]


class CalibrationTraceError(Exception):
    """Base class for all calibration trace store errors."""


class CalibrationTraceCorruptionError(CalibrationTraceError):
    """Raised when interior (non-trailing) corruption is detected in a
    trace file. Never silently repaired -- see the module docstring."""


class CalibrationTraceWriteError(CalibrationTraceError):
    """Raised when a durable append (write/flush/fsync) fails."""


class _EnvelopeKind(str, Enum):
    INVOCATION = "INVOCATION"
    TASK_EVALUATION = "TASK_EVALUATION"


@dataclass(frozen=True)
class RepairReport:
    """Outcome of one :meth:`CalibrationTraceStore.repair` call."""

    total_lines_seen: int
    valid_records_recovered: int
    trailing_bytes_truncated: int
    trailing_line_repaired: bool


def _envelope_payload(kind: _EnvelopeKind, payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "envelope_schema_version": TRACE_ENVELOPE_SCHEMA_VERSION,
        "kind": kind.value,
        "payload": payload,
    }


def _build_envelope(kind: _EnvelopeKind, payload: Mapping[str, Any]) -> dict[str, Any]:
    body = _envelope_payload(kind, payload)
    checksum = checksum_of(body)
    return {**body, "line_checksum": checksum}


def _verify_and_unwrap_envelope(
    envelope: Mapping[str, Any]
) -> tuple[_EnvelopeKind, dict[str, Any]]:
    """Validate one decoded JSON line as a trace envelope and return its
    ``(kind, payload)``. Raises :class:`ValueError` on any inconsistency --
    callers decide whether that means interior corruption or a repairable
    trailing line."""
    if envelope.get("envelope_schema_version") != TRACE_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"envelope_schema_version {envelope.get('envelope_schema_version')!r} does not "
            f"match {TRACE_ENVELOPE_SCHEMA_VERSION!r}"
        )
    try:
        kind = _EnvelopeKind(envelope["kind"])
        payload = envelope["payload"]
        stored_checksum = envelope["line_checksum"]
    except KeyError as exc:
        raise ValueError(f"envelope missing required field: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("envelope payload is not a JSON object")
    expected_checksum = checksum_of(_envelope_payload(kind, payload))
    if stored_checksum != expected_checksum:
        raise ValueError("line_checksum mismatch -- tampered or truncated trace line")
    return kind, payload


def _scan_and_classify_lines(content_lines: list[bytes], path: Path) -> tuple[int, int, bool]:
    """Verify every line in ``content_lines``, in order. Returns
    ``(valid_count, good_byte_length, trailing_repaired)``. Raises
    :class:`CalibrationTraceCorruptionError` the moment a non-trailing line
    fails verification; a trailing failure instead stops the scan and
    reports ``trailing_repaired=True`` for the caller to act on."""
    valid_count = 0
    good_byte_length = 0
    trailing_repaired = False
    last_index = len(content_lines) - 1
    for index, raw_line in enumerate(content_lines):
        try:
            envelope = json.loads(raw_line.decode("utf-8"))
            if not isinstance(envelope, dict):
                raise ValueError("trace line is not a JSON object")
            _verify_and_unwrap_envelope(envelope)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            if index == last_index:
                trailing_repaired = True
                break
            raise CalibrationTraceCorruptionError(
                f"interior corruption detected at line {index} of {path} "
                f"(a non-trailing line failed verification -- refusing to silently "
                f"repair): {exc}"
            ) from exc
        valid_count += 1
        good_byte_length += len(raw_line) + 1  # +1 for the stripped newline
    return valid_count, good_byte_length, trailing_repaired


class CalibrationTraceStore:
    """Append-only, single-process, durable JSONL calibration trace, mixing
    invocation and task-evaluation records in one file (one file per
    stage, per the design doc)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        """The JSONL file this store appends to and reads from."""
        return self._path

    def append_invocation_record(self, record: CalibrationInvocationRecord) -> None:
        """Durably append one :class:`CalibrationInvocationRecord`."""
        self._append(_EnvelopeKind.INVOCATION, calibration_invocation_record_to_dict(record))

    def append_task_evaluation_record(self, record: CalibrationTaskEvaluationRecord) -> None:
        """Durably append one :class:`CalibrationTaskEvaluationRecord`."""
        self._append(
            _EnvelopeKind.TASK_EVALUATION, calibration_task_evaluation_record_to_dict(record)
        )

    def _append(self, kind: _EnvelopeKind, payload: Mapping[str, Any]) -> None:
        envelope = _build_envelope(kind, payload)
        line = json.dumps(envelope, sort_keys=True) + "\n"
        with self._lock:
            try:
                with open(self._path, "a", encoding="utf-8") as handle:
                    handle.write(line)
                    handle.flush()
                    os.fsync(handle.fileno())
            except OSError as exc:
                raise CalibrationTraceWriteError(
                    f"failed to durably append trace record to {self._path}: {exc}"
                ) from exc

    def repair(self) -> RepairReport:
        """Startup scan-and-repair: verify every line's checksum in
        deterministic (file) order. A non-trailing invalid line raises
        :class:`CalibrationTraceCorruptionError`. Only a genuinely trailing
        invalid/incomplete line is truncated away, restoring the file to
        its last verified newline so subsequent appends resume cleanly."""
        with self._lock:
            if not self._path.exists():
                return RepairReport(0, 0, 0, False)
            raw = self._path.read_bytes()
            if not raw:
                return RepairReport(0, 0, 0, False)

            content_lines = raw.split(b"\n")
            if raw.endswith(b"\n"):
                content_lines = content_lines[:-1]

            valid_count, good_byte_length, trailing_repaired = _scan_and_classify_lines(
                content_lines, self._path
            )

            if trailing_repaired:
                with open(self._path, "r+b") as handle:
                    handle.truncate(good_byte_length)
                    handle.flush()
                    os.fsync(handle.fileno())
                trailing_bytes_truncated = len(raw) - good_byte_length
            else:
                trailing_bytes_truncated = 0

            return RepairReport(
                total_lines_seen=len(content_lines),
                valid_records_recovered=valid_count,
                trailing_bytes_truncated=trailing_bytes_truncated,
                trailing_line_repaired=trailing_repaired,
            )

    def read_all(self) -> _TraceReadResult:
        """Read every record, in deterministic append order. Raises
        :class:`CalibrationTraceCorruptionError` on *any* invalid line
        (interior or trailing) -- call :meth:`repair` first if the file may
        still contain crash-truncated trailing corruption."""
        if not self._path.exists():
            return (), ()
        invocations: list[CalibrationInvocationRecord] = []
        task_evaluations: list[CalibrationTaskEvaluationRecord] = []
        with self._lock:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if not line.strip():
                continue
            try:
                envelope = json.loads(line)
                if not isinstance(envelope, dict):
                    raise ValueError("trace line is not a JSON object")
                kind, payload = _verify_and_unwrap_envelope(envelope)
            except (json.JSONDecodeError, ValueError) as exc:
                raise CalibrationTraceCorruptionError(
                    f"invalid trace line {index} of {self._path}: {exc}"
                ) from exc
            if kind == _EnvelopeKind.INVOCATION:
                invocations.append(calibration_invocation_record_from_dict(payload))
            else:
                task_evaluations.append(calibration_task_evaluation_record_from_dict(payload))
        return tuple(invocations), tuple(task_evaluations)
