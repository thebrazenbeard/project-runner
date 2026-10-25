"""Explicit, read-only export of hashed execution-journal facts to Blotter.

This does not execute work, grant authority, or claim independent verification.
No network request occurs unless an operator explicitly calls export_to_blotter.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3

from .durable_dispatch import (
    _attempt_digest,
    _reconciliation_digest,
    _sha256_text,
    _verification_digest,
)
from .work_units import WorkUnitStatus


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _occurred_at(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def _check_digest(actual: str, expected: str, phase: str) -> None:
    if not hmac.compare_digest(actual, expected):
        raise ValueError(f"{phase} digest mismatch; refusing journal export")


def journal_events(state_db: str | Path) -> tuple[dict, ...]:
    """Snapshot all attempted and verified transitions; no token or network use.

    Only journal structure, hashes, statuses, and generation numbers leave the
    machine. Arbitrary reasons, outputs, holder names, and evidence are omitted.
    """
    db = Path(state_db).resolve(strict=True)
    conn = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
    records: list[tuple[float, int, str, dict]] = []
    try:
        conn.execute("BEGIN")
        # SQLite can hold orphan child rows from writers that disabled FK
        # enforcement. Exporting only joined attempts would silently omit
        # those records while claiming a complete journal snapshot.
        if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("journal foreign-key integrity violation; refusing export")
        attempts = conn.execute(
            "SELECT lineage_id, work_fingerprint, fencing_token, holder, "
            "admitted_at, budget_generation, work_generation, attempt_sha256, "
            "result_json, result_sha256, result_recorded_at "
            "FROM execution_attempts ORDER BY admitted_at, lineage_id, "
            "work_fingerprint, fencing_token"
        ).fetchall()
        for row in attempts:
            (lineage, fingerprint, fence, holder, admitted, budget_generation,
             work_generation, attempt_sha, result_json, result_sha,
             result_recorded_at) = row
            fence = int(fence)
            correlation = "pr.corr." + _digest(f"{lineage}\n{fingerprint}")[:48]
            attempt_hash = _attempt_digest(
                lineage_id=str(lineage), work_fingerprint_value=str(fingerprint),
                fencing_token=fence, holder=str(holder), admitted_at=float(admitted),
                budget_generation=int(budget_generation), work_generation=int(work_generation),
            )
            _check_digest(str(attempt_sha), attempt_hash, "attempt")

            def add(phase: str, at: float, phase_sha: str, *,
                    status: str | None = None, sequence: int | None = None,
                    reconciliation: str | None = None):
                identity = f"{correlation}\n{fence}\n{phase}\n{sequence}\n{phase_sha}"
                payload = {
                    "phase": phase,
                    # Blotter intentionally redacts payload keys ending in
                    # "_token"; this value is an attempt fence, not a secret.
                    "attempt_fence": fence,
                    "budget_generation": int(budget_generation),
                    "work_generation": int(work_generation),
                    "attempt_sha256": attempt_hash,
                    "journal_record_sha256": phase_sha,
                    "lineage_sha256": _digest(str(lineage)),
                    "work_fingerprint_sha256": _digest(str(fingerprint)),
                }
                if status is not None:
                    payload["status"] = status
                if sequence is not None:
                    payload["sequence"] = sequence
                if reconciliation is not None:
                    payload["reconciliation_outcome"] = reconciliation
                event = {
                    "kind": "PROJECT_RUNNER_EXECUTION_JOURNAL",
                    "message": f"Project Runner {phase} (local journal report)",
                    "payload": payload,
                    "level": "INFO",
                    "evidence": "SOURCE",
                    # A local claim/readback record is not independent attestation.
                    "effect": "REPORTED",
                    # Blotter source_ids are foreign event references, not
                    # arbitrary source digests. No fabricated remote event ID.
                    "source_ids": [],
                    "event_id": "pr.event." + _digest(identity)[:48],
                    "correlation_id": correlation,
                    "occurred_at": _occurred_at(float(at)),
                }
                records.append((float(at), len(records), event["event_id"], event))

            add("ADMITTED", float(admitted), attempt_hash)
            if result_json is None and result_sha is None and result_recorded_at is None:
                pass
            elif result_json is None or result_sha is None or result_recorded_at is None:
                raise ValueError("execution result journal is incomplete")
            else:
                _check_digest(str(result_sha), _sha256_text(str(result_json)), "result")
                add("RESULT_RECORDED", float(result_recorded_at), str(result_sha))

            verifications = conn.execute(
                "SELECT sequence, status, reason, verified_at, verification_sha256 "
                "FROM execution_verifications WHERE lineage_id=? AND work_fingerprint=? "
                "AND fencing_token=? ORDER BY sequence",
                (lineage, fingerprint, fence),
            ).fetchall()
            for seq, status, reason, at, sha in verifications:
                if result_json is None:
                    raise ValueError("verification has no execution result")
                verified_status = WorkUnitStatus(str(status))
                _check_digest(str(sha), _verification_digest(
                    status=verified_status, reason=str(reason), verified_at=float(at),
                ), "verification")
                add("VERIFICATION_RECORDED", float(at), str(sha),
                    status=verified_status.value, sequence=int(seq))

            reconciliations = conn.execute(
                "SELECT sequence, outcome, reason, evidence_json, reconciler, "
                "observed_at, reconciliation_sha256 FROM execution_reconciliations "
                "WHERE lineage_id=? AND work_fingerprint=? AND fencing_token=? "
                "ORDER BY sequence",
                (lineage, fingerprint, fence),
            ).fetchall()
            for seq, outcome, reason, evidence_json, reconciler, at, sha in reconciliations:
                evidence = json.loads(str(evidence_json))
                if not isinstance(evidence, list) or not all(
                    isinstance(item, str) for item in evidence
                ):
                    raise ValueError("execution reconciliation evidence is invalid")
                _check_digest(str(sha), _reconciliation_digest(
                    outcome=str(outcome), reason=str(reason), evidence=tuple(evidence),
                    reconciler=str(reconciler), observed_at=float(at),
                ), "reconciliation")
                add("RECONCILIATION_RECORDED", float(at), str(sha),
                    reconciliation=str(outcome), sequence=int(seq))
        conn.commit()
    finally:
        conn.close()
    return tuple(item[3] for item in sorted(records))


def export_to_blotter(
    state_db: str | Path, *, url: str, actor: str, session: str, token: str,
) -> tuple[dict, ...]:
    """POST only after explicit invocation; ambiguous writes require reconciliation.

    Uses Blotter's own vetted RemoteBlotter client, including URL and redirect
    restrictions. No automatic retry; stable event IDs make manual replay safe.
    """
    if not isinstance(token, str) or len(token) < 32:
        raise ValueError("missing Blotter token")
    events = journal_events(state_db)  # Validate the complete snapshot before any POST.
    try:
        from agent_blotter.remote import RemoteBlotter
    except ImportError as exc:
        raise ValueError(
            "agent-blotter Python client is required for an explicit export"
        ) from exc
    remote = RemoteBlotter(url, actor=actor, token=token)
    receipts = []
    for event in events:
        event_id = event["event_id"]
        try:
            result = remote.record(session=session, **event)
            if result.get("id") != event_id or type(result.get("seq")) is not int:
                raise ValueError("Blotter receipt is structurally invalid")
            readback = remote.list(
                actor=actor, session=session, after_seq=result["seq"] - 1, limit=1,
            )
            if len(readback) != 1 or readback[0].get("id") != event_id:
                raise ValueError("Blotter persisted event readback mismatched receipt")
        except Exception as exc:
            raise RuntimeError(
                "Blotter write/readback outcome unknown or rejected; reconcile using event_id "
                + event_id + " before retry"
            ) from exc
        receipts.append({
            "event_id": event_id, "seq": result["seq"],
            "event_persisted_readback": True,
        })
    return tuple(receipts)
