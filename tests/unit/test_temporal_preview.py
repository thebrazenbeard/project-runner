"""Contract tests for the explicit, read-only Project Runner timeline preview."""

import json
import sqlite3
from datetime import datetime

import pytest

from runner.backends import BackendResult
from runner.blotter_export import journal_events
from runner.cli import main
from runner.durable_dispatch import (
    _EXECUTION_JOURNAL_SCHEMA,
    _attempt_digest,
    _result_payload,
    _reconciliation_digest,
    _sha256_text,
    _verification_digest,
)
from runner.temporal_preview import _utc_timestamp, journal_temporal_events
from runner.work_units import WorkUnitStatus


def _journal(path):
    with sqlite3.connect(path) as conn:
        conn.executescript(_EXECUTION_JOURNAL_SCHEMA)
        fingerprint = "f" * 64
        conn.execute(
            "INSERT INTO execution_attempts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                "lineage", fingerprint, 1, "private-worker", 1.0, 1, 1,
                _attempt_digest(
                    lineage_id="lineage", work_fingerprint_value=fingerprint,
                    fencing_token=1, holder="private-worker", admitted_at=1.0,
                    budget_generation=1, work_generation=1,
                ), None, None, None,
            ),
        )
        result = _result_payload(BackendResult(
            work_fingerprint=fingerprint, succeeded=True, outputs=("private-output",),
            evidence=("private-evidence",), classification="SUCCEEDED",
        ))
        conn.execute(
            "UPDATE execution_attempts SET result_json=?, result_sha256=?, result_recorded_at=?",
            (result, _sha256_text(result), 3.0),
        )
        conn.execute(
            "INSERT INTO execution_verifications VALUES (?,?,?,?,?,?,?,?)",
            ("lineage", fingerprint, 1, 1, "COMPLETE", "private-reason", 4.0,
             _verification_digest(status=WorkUnitStatus.COMPLETE,
                                  reason="private-reason", verified_at=4.0)),
        )
        conn.execute(
            "INSERT INTO execution_reconciliations VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("lineage", fingerprint, 1, 1, "RECONCILED", "private-reconciliation-reason",
             '["private-reconciliation-evidence"]', "private-reconciler", 5.0,
             _reconciliation_digest(
                 outcome="RECONCILED", reason="private-reconciliation-reason",
                 evidence=("private-reconciliation-evidence",),
                 reconciler="private-reconciler", observed_at=5.0)),
        )


def test_temporal_preview_preserves_distinct_time_bases_and_sanitized_source_refs(tmp_path):
    db = tmp_path / "journal.db"
    _journal(db)
    native = journal_events(db)
    first = journal_temporal_events(db)
    assert first == journal_temporal_events(db)
    assert [e["id"] for e in first] == [e["event_id"] for e in native]
    assert [e["metadata"]["time_basis"] for e in first] == [
        "admitted_at", "result_recorded_at", "verified_at", "observed_at",
    ]
    # Temporal's canonical UTC representation elides an all-zero fraction,
    # unlike Project Runner's always-microsecond native source convention.
    assert [e["timestamp"] for e in first] == [
        e["occurred_at"].replace(".000000Z", "Z") for e in native
    ]
    for event, original in zip(first, native, strict=True):
        assert set(event) == {"id", "timestamp", "source", "event", "refs", "metadata"}
        assert event["source"] == "project-runner"
        assert event["refs"] == [
            "project-runner:journal-sha256:" + original["payload"]["journal_record_sha256"]
        ]
        assert event["metadata"]["correlation_id"] == original["correlation_id"]
        assert event["metadata"]["phase"] == original["payload"]["phase"]
        assert datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")).utcoffset().total_seconds() == 0
    assert "private-" not in json.dumps(first)
    assert all(event["metadata"]["claim_limit"] == "source_report_not_effect_attestation"
               for event in first)


def test_cli_temporal_preview_is_read_only_and_does_not_use_network(tmp_path, monkeypatch, capsys):
    db = tmp_path / "journal.db"
    _journal(db)
    before = db.read_bytes()
    monkeypatch.delenv("PROJECT_RUNNER_BLOTTER_TOKEN", raising=False)
    assert main(["temporal-preview", "--state-db", str(db)]) == 0
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert records == list(journal_temporal_events(db))
    assert db.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["journal.db"]


def test_corrupt_journal_rejected_before_any_cli_output(tmp_path, capsys):
    db = tmp_path / "journal.db"
    _journal(db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE execution_attempts SET holder='tampered'")
    with pytest.raises(ValueError, match="digest mismatch"):
        main(["temporal-preview", "--state-db", str(db)])
    assert capsys.readouterr().out == ""


def test_unknown_phase_fails_closed(tmp_path, monkeypatch):
    db = tmp_path / "journal.db"
    _journal(db)
    import runner.temporal_preview as preview
    native = journal_events(db)[0]
    monkeypatch.setattr(preview, "journal_events", lambda _: (
        {**native, "payload": {**native["payload"], "phase": "UNKNOWN"}},
    ))
    with pytest.raises(ValueError, match="unknown journal phase"):
        preview.journal_temporal_events(db)


@pytest.mark.parametrize(("source", "expected"), [
    ("2026-10-27T12:00:00.000000Z", "2026-10-27T12:00:00Z"),
    ("2026-10-27T12:00:00.123456Z", "2026-10-27T12:00:00.123456Z"),
])
def test_timestamp_matches_temporal_precision_contract(source, expected):
    assert _utc_timestamp(source) == expected


@pytest.mark.parametrize("source", [
    "2026-10-27T12:00:00+01:00",
    "2026-10-27T12:00:00",
    "2026-10-27T12:00:00.1234567Z",
])
def test_noncanonical_source_timestamp_rejected(source):
    with pytest.raises(ValueError, match="timestamp|canonical"):
        _utc_timestamp(source)


def test_tied_timestamps_order_by_temporal_timestamp_then_stable_id(tmp_path, monkeypatch):
    db = tmp_path / "journal.db"
    _journal(db)
    import runner.temporal_preview as preview
    native = journal_events(db)
    zero = {**native[0], "event_id": "pr.event.z", "occurred_at": "2026-10-27T12:00:00.000000Z"}
    later = {**native[0], "event_id": "pr.event.a", "occurred_at": "2026-10-27T12:00:00.123456Z"}
    same = {**native[0], "event_id": "pr.event.a0", "occurred_at": "2026-10-27T12:00:00.000000Z"}
    monkeypatch.setattr(preview, "journal_events", lambda _: (later, zero, same))
    assert [event["id"] for event in journal_temporal_events(db)] == [
        "pr.event.a0", "pr.event.z", "pr.event.a",
    ]
