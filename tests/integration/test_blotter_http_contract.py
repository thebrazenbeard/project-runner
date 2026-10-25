"""Optional real HTTP contract test when canonical agent-blotter is installed."""

import threading

import pytest

from runner.blotter_export import export_to_blotter, journal_events

blotter = pytest.importorskip("agent_blotter.store")
server_api = pytest.importorskip("agent_blotter.server")
remote_api = pytest.importorskip("agent_blotter.remote")


def test_real_local_authenticated_blotter_accepts_replay_idempotently(tmp_path):
    # The sample records exercise admission and retry correlation without
    # depending on an external service or any real enrolled actor credential.
    from runner.durable_dispatch import _EXECUTION_JOURNAL_SCHEMA, _attempt_digest
    import sqlite3

    db = tmp_path / "project-runner.db"
    with sqlite3.connect(db) as conn:
        conn.executescript(_EXECUTION_JOURNAL_SCHEMA)
        for fence in (1, 2):
            conn.execute(
                "INSERT INTO execution_attempts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                ("local-test-lineage", "a" * 64, fence, "test-worker", float(fence),
                 1, fence, _attempt_digest(
                     lineage_id="local-test-lineage", work_fingerprint_value="a" * 64,
                     fencing_token=fence, holder="test-worker", admitted_at=float(fence),
                     budget_generation=1, work_generation=fence,
                 ), None, None, None),
            )

    token = "local-temporary-test-token-" + "x" * 32
    ledger = blotter.Blotter(tmp_path / "blotter.db")
    server = server_api.create_server(
        ledger, {token: "project.runner.test"}, host="127.0.0.1", port=0,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}"
        event_count = len(journal_events(db))
        first = export_to_blotter(
            db, url=url, actor="project.runner.test", session="contract-test", token=token,
        )
        second = export_to_blotter(
            db, url=url, actor="project.runner.test", session="contract-test", token=token,
        )
        remote = remote_api.RemoteBlotter(url, actor="project.runner.test", token=token)
        observed = remote.list(session="contract-test", limit=100)
        assert len(first) == len(second) == len(observed) == event_count
        assert [entry["event_id"] for entry in first] == [entry["id"] for entry in observed]
        assert [entry["seq"] for entry in first] == [entry["seq"] for entry in second]
        assert {entry["correlation_id"] for entry in observed} == {
            journal_events(db)[0]["correlation_id"]
        }
        assert all(entry["effect"] == "REPORTED" for entry in observed)
        assert [entry["payload"]["attempt_fence"] for entry in observed] == [1, 2]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
