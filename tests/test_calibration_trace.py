"""MEGB-03H.2A tests: durable JSONL calibration trace storage --
concurrency, crash-truncation repair, interior-corruption refusal,
fsync-failure classification, and duplicate-free resumption.

Every test uses ``tmp_path`` exclusively: no test ever constructs a
:class:`~src.reference.calibration_trace.CalibrationTraceStore` against
``DEFAULT_CALIBRATION_TRACE_DIR`` (the real privileged path), and no
canonical/candidate execution or Docker resource is touched anywhere here.
"""

import json
import threading
from pathlib import Path

import pytest

from src.reference.calibration_trace import (
    DEFAULT_CALIBRATION_TRACE_DIR,
    CalibrationTraceCorruptionError,
    CalibrationTraceStore,
    CalibrationTraceWriteError,
)
from src.reference.calibration_schema import CalibrationStage
from src.reference.calibration_summary import build_calibration_summary_report
from src.reference.result_schema import MeasurementStatus
from tests._calibration_fixtures import make_invocation, make_task_evaluation


# ---------------------------------------------------------------------------
# No real privileged path touched
# ---------------------------------------------------------------------------


def test_default_trace_dir_is_under_the_privileged_subtree() -> None:
    """Default trace dir is under the privileged subtree."""
    assert str(DEFAULT_CALIBRATION_TRACE_DIR).startswith("artifacts/privileged/")


def test_referencing_default_trace_dir_constant_creates_no_directory() -> None:
    # Merely importing/referencing the constant must never itself create the
    # real privileged directory -- only constructing a store against a path
    # does (and no test in this module ever does that against the default).
    """Referencing default trace dir constant creates no directory."""
    assert not DEFAULT_CALIBRATION_TRACE_DIR.exists()


# ---------------------------------------------------------------------------
# Append / read round trip
# ---------------------------------------------------------------------------


def test_append_and_read_all_round_trips(tmp_path: Path) -> None:
    """Append and read all round trips."""
    store = CalibrationTraceStore(tmp_path / "trace.jsonl")
    invocation = make_invocation("inv-1")
    task_evaluation = make_task_evaluation(contributing_invocation_ids=("inv-1",))
    store.append_invocation_record(invocation)
    store.append_task_evaluation_record(task_evaluation)

    invocations, task_evaluations = store.read_all()
    assert invocations == (invocation,)
    assert task_evaluations == (task_evaluation,)


def test_read_all_on_missing_file_returns_empty(tmp_path: Path) -> None:
    """Read all on missing file returns empty."""
    store = CalibrationTraceStore(tmp_path / "does-not-exist.jsonl")
    assert store.read_all() == ((), ())


def test_repair_on_missing_or_empty_file_is_a_no_op(tmp_path: Path) -> None:
    """Repair on missing or empty file is a no op."""
    store = CalibrationTraceStore(tmp_path / "trace.jsonl")
    report = store.repair()
    assert report.total_lines_seen == 0
    assert not report.trailing_line_repaired


# ---------------------------------------------------------------------------
# Concurrent thread writes through the intended single-process lock
# ---------------------------------------------------------------------------


def test_concurrent_thread_appends_produce_no_interleaving_corruption(tmp_path: Path) -> None:
    """Concurrent thread appends produce no interleaving corruption."""
    store = CalibrationTraceStore(tmp_path / "trace.jsonl")
    thread_count = 16

    def _append(index: int) -> None:
        store.append_invocation_record(make_invocation(f"inv-{index}"))

    threads = [threading.Thread(target=_append, args=(i,)) for i in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    invocations, _ = store.read_all()
    assert len(invocations) == thread_count
    assert {invocation.invocation_id for invocation in invocations} == {
        f"inv-{i}" for i in range(thread_count)
    }


# ---------------------------------------------------------------------------
# Truncated-tail detection, physical truncation, and safe subsequent append
# ---------------------------------------------------------------------------


def test_trailing_truncation_is_repaired_and_append_resumes_cleanly(tmp_path: Path) -> None:
    """Trailing truncation is repaired and append resumes cleanly."""
    path = tmp_path / "trace.jsonl"
    store = CalibrationTraceStore(path)
    store.append_invocation_record(make_invocation("inv-1"))
    store.append_invocation_record(make_invocation("inv-2"))

    good_size = path.stat().st_size
    with open(path, "a", encoding="utf-8") as handle:
        handle.write('{"envelope_schema_version": "megb-03h-calibration-trace-envelope-v1", "kin')

    report = store.repair()
    assert report.trailing_line_repaired is True
    assert report.valid_records_recovered == 2
    assert report.trailing_bytes_truncated > 0
    assert path.stat().st_size == good_size

    invocations, _ = store.read_all()
    assert {invocation.invocation_id for invocation in invocations} == {"inv-1", "inv-2"}

    store.append_invocation_record(make_invocation("inv-3"))
    invocations_after, _ = store.read_all()
    assert {invocation.invocation_id for invocation in invocations_after} == {
        "inv-1",
        "inv-2",
        "inv-3",
    }


def test_trailing_file_without_newline_is_repaired(tmp_path: Path) -> None:
    """Trailing file without newline is repaired."""
    path = tmp_path / "trace.jsonl"
    store = CalibrationTraceStore(path)
    store.append_invocation_record(make_invocation("inv-1"))

    # Append a well-formed-looking but incomplete final line with no
    # trailing newline (as a crash mid-write() would leave it).
    with open(path, "a", encoding="utf-8") as handle:
        handle.write('{"partial": true')

    report = store.repair()
    assert report.trailing_line_repaired is True
    invocations, _ = store.read_all()
    assert len(invocations) == 1


# ---------------------------------------------------------------------------
# Interior corruption rejection
# ---------------------------------------------------------------------------


def test_interior_corruption_is_never_silently_repaired(tmp_path: Path) -> None:
    """Interior corruption is never silently repaired."""
    path = tmp_path / "trace.jsonl"
    store = CalibrationTraceStore(path)
    store.append_invocation_record(make_invocation("inv-1"))
    store.append_invocation_record(make_invocation("inv-2"))
    store.append_invocation_record(make_invocation("inv-3"))

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    middle_envelope = json.loads(lines[1])
    middle_envelope["payload"]["task_id"] = "HumanEval/999"  # break line_checksum
    lines[1] = json.dumps(middle_envelope, sort_keys=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(CalibrationTraceCorruptionError, match="interior corruption"):
        store.repair()

    with pytest.raises(CalibrationTraceCorruptionError):
        store.read_all()


# ---------------------------------------------------------------------------
# fsync/write failure classification
# ---------------------------------------------------------------------------


def test_fsync_failure_is_classified_as_trace_write_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fsync failure is classified as trace write error."""
    store = CalibrationTraceStore(tmp_path / "trace.jsonl")

    def _failing_fsync(_fd: int) -> None:
        raise OSError("simulated fsync failure")

    monkeypatch.setattr("os.fsync", _failing_fsync)
    with pytest.raises(CalibrationTraceWriteError, match="simulated fsync failure"):
        store.append_invocation_record(make_invocation("inv-1"))


def test_write_failure_on_unwritable_directory_is_classified(tmp_path: Path) -> None:
    """Write failure on unwritable directory is classified."""
    unwritable_dir = tmp_path / "unwritable"
    unwritable_dir.mkdir()
    store = CalibrationTraceStore(unwritable_dir / "trace.jsonl")
    unwritable_dir.chmod(0o500)
    try:
        with pytest.raises(CalibrationTraceWriteError):
            store.append_invocation_record(make_invocation("inv-1"))
    finally:
        unwritable_dir.chmod(0o700)


# ---------------------------------------------------------------------------
# Resumption without duplicate scientific records
# ---------------------------------------------------------------------------


def test_resumption_after_repair_produces_no_duplicate_scientific_records(tmp_path: Path) -> None:
    """Resumption after repair produces no duplicate scientific records."""
    path = tmp_path / "trace.jsonl"
    store = CalibrationTraceStore(path)

    # First (interrupted) attempt: one invocation, then a superseded,
    # incomplete task-evaluation record representing the crash.
    store.append_invocation_record(make_invocation("inv-attempt-1"))
    store.append_task_evaluation_record(
        make_task_evaluation(
            measurement_status=MeasurementStatus.INCOMPLETE,
            q_ref_task=None,
            contributing_invocation_ids=("inv-attempt-1",),
            superseded=True,
        )
    )

    # Simulate a crash mid-write of the next line.
    with open(path, "a", encoding="utf-8") as handle:
        handle.write('{"envelope_schema_ver')
    report = store.repair()
    assert report.trailing_line_repaired is True

    # Fresh, complete re-execution of the same replicate under a new
    # invocation id, per the supersession rule (never merged with the
    # superseded partial attempt).
    store.append_invocation_record(make_invocation("inv-attempt-2"))
    store.append_task_evaluation_record(
        make_task_evaluation(contributing_invocation_ids=("inv-attempt-2",))
    )

    invocations, task_evaluations = store.read_all()
    assert {invocation.invocation_id for invocation in invocations} == {
        "inv-attempt-1",
        "inv-attempt-2",
    }

    summary = build_calibration_summary_report(
        stage=CalibrationStage.H3,
        calibration_run_id="run-1",
        generated_at="2026-08-03T00:00:05Z",
        invocation_records=invocations,
        task_evaluation_records=task_evaluations,
    )
    # Exactly one active (non-superseded) task evaluation counted -- the
    # superseded partial contributes nothing to the scientific summary.
    assert summary.total_task_evaluation_records == 1
    assert summary.measurement_status_counts.get(MeasurementStatus.INCOMPLETE.value, 0) == 0
