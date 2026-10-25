import json
import sqlite3
import sys
from types import ModuleType

import pytest

from runner.durable_dispatch import (
    _EXECUTION_JOURNAL_SCHEMA,
    _attempt_digest,
    _result_payload,
    _sha256_text,
    _verification_digest,
)
from runner.backends import BackendResult
from runner.work_units import WorkUnitStatus
from runner.blotter_export import journal_events, export_to_blotter
from runner.cli import main


def _journal(path):
    conn = sqlite3.connect(path)
    conn.executescript(_EXECUTION_JOURNAL_SCHEMA)
    fingerprint = "f" * 64
    for fence in (1, 2):
        conn.execute(
            "INSERT INTO execution_attempts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                "lineage", fingerprint, fence, "worker", float(fence),
                1, fence, _attempt_digest(
                    lineage_id="lineage", work_fingerprint_value=fingerprint,
                    fencing_token=fence, holder="worker", admitted_at=float(fence),
                    budget_generation=1, work_generation=fence,
                ), None, None, None,
            ),
        )
    result = _result_payload(BackendResult(
        work_fingerprint=fingerprint, succeeded=True, outputs=("value",),
        evidence=("readback",), classification="SUCCEEDED",
    ))
    conn.execute(
        "UPDATE execution_attempts SET result_json=?, result_sha256=?, result_recorded_at=? "
        "WHERE fencing_token=2", (result, _sha256_text(result), 3.0),
    )
    conn.execute(
        "INSERT INTO execution_verifications VALUES (?,?,?,?,?,?,?,?)",
        ("lineage", fingerprint, 2, 1, "COMPLETE", "provider readback succeeded",
         4.0, _verification_digest(
             status=WorkUnitStatus.COMPLETE, reason="provider readback succeeded", verified_at=4.0,
         )),
    )
    conn.commit()
    conn.close()


def test_journal_events_are_stable_distinct_across_retries_and_not_effect_attestations(tmp_path):
    db = tmp_path / "journal.db"
    _journal(db)
    first = journal_events(db)
    assert first == journal_events(db)
    assert [e["payload"]["phase"] for e in first] == [
        "ADMITTED", "ADMITTED", "RESULT_RECORDED", "VERIFICATION_RECORDED",
    ]
    assert len({e["event_id"] for e in first}) == 4
    assert len({e["correlation_id"] for e in first}) == 1
    assert all(e["effect"] == "REPORTED" for e in first)
    assert first[-1]["payload"]["status"] == "COMPLETE"
    assert "provider readback succeeded" not in json.dumps(first)
    assert "worker" not in json.dumps(first)


def test_corrupt_local_journal_cannot_be_exported(tmp_path):
    db = tmp_path / "journal.db"
    _journal(db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE execution_attempts SET holder='other' WHERE fencing_token=1")
    with pytest.raises(ValueError, match="digest mismatch"):
        journal_events(db)


def test_remote_export_requires_opt_in_token_and_preserves_event_id(tmp_path, monkeypatch):
    db = tmp_path / "journal.db"
    _journal(db)
    submissions = []

    class FakeRemote:
        def __init__(self, url, *, actor, token):
            assert url == "https://blotter.example.test"
            assert actor == "bt2.test"
            assert token == "x" * 32

        def record(self, **kwargs):
            submissions.append(kwargs)
            return {"id": kwargs["event_id"], "seq": len(submissions)}

        def list(self, **kwargs):
            assert kwargs["actor"] == "bt2.test"
            assert kwargs["session"] == "bt2.tests"
            return [{"id": submissions[kwargs["after_seq"]]["event_id"]}]

    module = ModuleType("agent_blotter")
    remote = ModuleType("agent_blotter.remote")
    remote.RemoteBlotter = FakeRemote
    monkeypatch.setitem(sys.modules, "agent_blotter", module)
    monkeypatch.setitem(sys.modules, "agent_blotter.remote", remote)

    with pytest.raises(ValueError, match="missing Blotter token"):
        export_to_blotter(db, url="https://blotter.example.test", actor="bt2.test",
                          session="bt2.tests", token="")
    assert not submissions
    receipts = export_to_blotter(db, url="https://blotter.example.test",
                                actor="bt2.test", session="bt2.tests", token="x" * 32)
    assert len(receipts) == len(submissions) == 4
    assert [receipt["event_id"] for receipt in receipts] == [
        event["event_id"] for event in journal_events(db)
    ]
    assert all(submission["session"] == "bt2.tests" for submission in submissions)
    assert all(receipt["event_persisted_readback"] for receipt in receipts)


def test_remote_disconnect_reports_ambiguous_write_without_retry(tmp_path, monkeypatch):
    db = tmp_path / "journal.db"
    _journal(db)
    calls = []

    class FakeRemote:
        def __init__(self, url, *, actor, token):
            pass

        def record(self, **kwargs):
            calls.append(kwargs)
            raise ConnectionError("deliberate failure")

    module = ModuleType("agent_blotter")
    remote = ModuleType("agent_blotter.remote")
    remote.RemoteBlotter = FakeRemote
    monkeypatch.setitem(sys.modules, "agent_blotter", module)
    monkeypatch.setitem(sys.modules, "agent_blotter.remote", remote)

    with pytest.raises(RuntimeError, match="unknown.*event_id"):
        export_to_blotter(db, url="https://blotter.example.test", actor="bt2.test",
                          session="bt2.tests", token="x" * 32)
    assert len(calls) == 1


def test_cli_preview_is_read_only_and_does_not_require_credentials(tmp_path, monkeypatch, capsys):
    db = tmp_path / "journal.db"
    _journal(db)
    monkeypatch.delenv("PROJECT_RUNNER_BLOTTER_TOKEN", raising=False)
    assert main(["blotter-export", "--preview", "--state-db", str(db)]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["event_count"] == 4
    assert preview["event_ids"] == [e["event_id"] for e in journal_events(db)]


def test_cli_export_without_token_does_not_post(tmp_path, monkeypatch):
    db = tmp_path / "journal.db"
    _journal(db)
    monkeypatch.delenv("PROJECT_RUNNER_BLOTTER_TOKEN", raising=False)
    with pytest.raises(ValueError, match="missing Blotter token"):
        main(["blotter-export", "--state-db", str(db), "--url",
              "https://blotter.example.test", "--actor", "bt2.test",
              "--session", "bt2.tests"])


def test_stale_or_wrong_remote_readback_stops_export(tmp_path, monkeypatch):
    db = tmp_path / "journal.db"
    _journal(db)
    calls = []

    class FakeRemote:
        def __init__(self, url, *, actor, token):
            pass

        def record(self, **kwargs):
            calls.append(kwargs["event_id"])
            return {"id": kwargs["event_id"], "seq": 1}

        def list(self, **kwargs):
            return [{"id": "unrelated-event"}]

    module = ModuleType("agent_blotter")
    remote = ModuleType("agent_blotter.remote")
    remote.RemoteBlotter = FakeRemote
    monkeypatch.setitem(sys.modules, "agent_blotter", module)
    monkeypatch.setitem(sys.modules, "agent_blotter.remote", remote)
    with pytest.raises(RuntimeError, match="readback.*event_id"):
        export_to_blotter(db, url="https://blotter.example.test", actor="bt2.test",
                          session="bt2.tests", token="x" * 32)
    assert len(calls) == 1


def test_complete_prevalidation_prevents_partial_external_export(tmp_path, monkeypatch):
    db = tmp_path / "journal.db"
    _journal(db)
    # The second attempt is corrupt. No first-attempt event should be POSTed.
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE execution_attempts SET holder='tampered' WHERE fencing_token=2")
    called = []

    class FakeRemote:
        def __init__(self, *args, **kwargs):
            called.append("network-init")

    module = ModuleType("agent_blotter")
    remote = ModuleType("agent_blotter.remote")
    remote.RemoteBlotter = FakeRemote
    monkeypatch.setitem(sys.modules, "agent_blotter", module)
    monkeypatch.setitem(sys.modules, "agent_blotter.remote", remote)
    with pytest.raises(ValueError, match="digest mismatch"):
        export_to_blotter(db, url="https://blotter.example.test", actor="bt2.test",
                          session="bt2.tests", token="x" * 32)
    assert not called


def test_orphan_verification_is_not_silently_omitted(tmp_path):
    db = tmp_path / "journal.db"
    _journal(db)
    # SQLite foreign_keys defaults to OFF for this independent legacy writer.
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO execution_verifications VALUES (?,?,?,?,?,?,?,?)",
            ("orphan-lineage", "e" * 64, 99, 1, "COMPLETE", "orphan",
             7.0, "f" * 64),
        )
    with pytest.raises(ValueError, match="foreign-key integrity"):
        journal_events(db)
