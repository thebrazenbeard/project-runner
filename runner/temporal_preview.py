"""Read-only Temporal NDJSON projection of validated Project Runner journal facts.

This projection neither appends to Temporal nor submits events to Blotter. It
represents source journal reports, never independent effect verification.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re

from .blotter_export import journal_events


# Preserve the meaning of the underlying journal clock, not just its value.
_PHASE_TIME_BASIS = {
    "ADMITTED": "admitted_at",
    "RESULT_RECORDED": "result_recorded_at",
    "VERIFICATION_RECORDED": "verified_at",
    "RECONCILIATION_RECORDED": "observed_at",
}
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _utc_timestamp(value: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("journal timestamp is not canonical UTC")
    try:
        stamp = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("invalid journal timestamp") from exc
    if stamp.utcoffset() != timezone.utc.utcoffset(stamp):
        raise ValueError("journal timestamp is not UTC")
    source_form = stamp.isoformat(timespec="microseconds").replace("+00:00", "Z")
    if source_form != value:
        raise ValueError("journal timestamp is not canonical UTC")
    # Temporal elides an all-zero fraction; otherwise its stored timestamp
    # validator would reject Project Runner's always-six-digit source form.
    precision = "microseconds" if stamp.microsecond else "seconds"
    return stamp.isoformat(timespec=precision).replace("+00:00", "Z")


def journal_temporal_events(state_db: str | Path) -> tuple[dict, ...]:
    """Return validated, sanitized Temporal-shaped events without writing.

    The complete journal snapshot is checked before any projection is exposed.
    The caller remains responsible for any subsequent explicit storage action.
    """
    source = journal_events(state_db)
    result: list[dict] = []
    seen: set[str] = set()
    for native in source:
        event_id = native["event_id"]
        if not isinstance(event_id, str) or not event_id.startswith("pr.event."):
            raise ValueError("invalid journal event id")
        if event_id in seen:
            raise ValueError("duplicate journal event id")
        seen.add(event_id)

        payload = native["payload"]
        phase = payload["phase"]
        if phase not in _PHASE_TIME_BASIS:
            raise ValueError(f"unknown journal phase: {phase}")
        source_digest = payload["journal_record_sha256"]
        if not isinstance(source_digest, str) or not _SHA256.fullmatch(source_digest):
            raise ValueError("invalid journal record digest")
        result.append({
            "id": event_id,
            "timestamp": _utc_timestamp(native["occurred_at"]),
            "source": "project-runner",
            "event": native["message"],
            "refs": [f"project-runner:journal-sha256:{source_digest}"],
            "metadata": {
                "phase": phase,
                "time_basis": _PHASE_TIME_BASIS[phase],
                "correlation_id": native["correlation_id"],
                "claim_limit": "source_report_not_effect_attestation",
            },
        })
    # Project Runner's journal uses admission/insertion tie order. Temporal
    # orders by actual timestamp then stable ID, which is a different contract.
    result.sort(key=lambda event: (
        datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")),
        event["id"],
    ))
    return tuple(result)
