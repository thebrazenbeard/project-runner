from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any


REZON_RUN_EVIDENCE_SCHEMA = "rezon.run-evidence.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

_RECEIPT_FIELDS = {
    "task_id",
    "episode_version",
    "accepted_claim_ids",
    "rejected_claim_ids",
    "unresolved",
    "failures",
    "effect_state",
    "source_versions",
    "execution_ids",
    "execution_output_digests",
    "execution_producer_ids",
    "task_envelope_digest",
    "claim_disposition_complete",
}

_EXECUTION_FIELDS = {
    "execution_id",
    "node_id",
    "episode_version",
    "visible_proposition_ids",
    "blinded_proposition_ids",
    "visible_relation_ids",
    "blinded_relation_ids",
    "emitted_proposition_ids",
    "independence_demonstrated",
    "task_envelope_digest",
    "executor_task_specification_digest",
    "executor_episode_version",
    "canonical_producer_execution_id",
    "canonical_episode_snapshot_digest",
    "canonical_output_digest",
    "source_refs",
    "source_versions",
    "reported_source_refs",
    "reported_source_versions",
    "failures",
}


class RezonEvidenceError(ValueError):
    pass


@dataclass(frozen=True)
class RezonPlanEvidenceObservation:
    evidence_digest: str
    task_id: str
    episode_version: str
    execution_count: int
    source_versions: tuple[str, ...]
    unresolved: tuple[str, ...]
    failures: tuple[str, ...]
    structurally_consistent: bool = True
    origin_authenticated: bool = False
    inner_semantics_independently_verified: bool = False
    completion_eligible: bool = False
    authority_eligible: bool = False
    effect_state: str = "plan"


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        missing = sorted(expected - set(value))
        extra = sorted(set(value) - expected)
        raise RezonEvidenceError(
            f"{label} fields mismatch missing={missing} extra={extra}"
        )


def _nonempty(value: Any, label: str) -> str:
    if type(value) is not str or not value:
        raise RezonEvidenceError(f"{label} must be a non-empty exact string")
    return value


def _string_list(value: Any, label: str) -> list[str]:
    if type(value) is not list or any(type(item) is not str or not item for item in value):
        raise RezonEvidenceError(f"{label} must be a list of non-empty exact strings")
    return value


def _optional_string(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if type(value) is not str or not value:
        raise RezonEvidenceError(f"{label} must be null or a non-empty exact string")
    return value


def _optional_sha256(value: Any, label: str) -> str | None:
    value = _optional_string(value, label)
    if value is not None and _SHA256.fullmatch(value) is None:
        raise RezonEvidenceError(f"{label} must be null or lowercase SHA-256")
    return value


def _binding_list(value: Any, label: str) -> list[list[str]]:
    if type(value) is not list:
        raise RezonEvidenceError(f"{label} must be a list")
    out: list[list[str]] = []
    seen: set[str] = set()
    for item in value:
        if (
            type(item) is not list
            or len(item) != 2
            or any(type(part) is not str or not part for part in item)
        ):
            raise RezonEvidenceError(f"{label} must contain exact non-empty string pairs")
        if item[0] in seen:
            raise RezonEvidenceError(f"{label} cannot duplicate execution id")
        seen.add(item[0])
        out.append(item)
    return out


def _canonical_body_digest(value: dict[str, Any]) -> str:
    body = {
        "schema_version": value["schema_version"],
        "receipt": value["receipt"],
        "executions": value["executions"],
    }
    encoded = json.dumps(
        body,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_rezon_plan_evidence(
    value: dict[str, Any],
) -> RezonPlanEvidenceObservation:
    """Validate the bounded outer transport contract for Rezon PLAN evidence.

    This validates deterministic envelope/receipt/trace consistency that an
    outer orchestrator can check without importing Rezon's reasoning kernel.

    It intentionally does not authenticate object origin, recompute Rezon's
    canonical producer algorithm, translate authority, or establish completion.
    """
    if type(value) is not dict:
        raise RezonEvidenceError("Rezon evidence must be a JSON object")
    _exact_keys(
        value,
        {"schema_version", "receipt", "executions", "evidence_digest"},
        "Rezon evidence",
    )
    if value["schema_version"] != REZON_RUN_EVIDENCE_SCHEMA:
        raise RezonEvidenceError("unsupported Rezon run-evidence schema")

    supplied_digest = value["evidence_digest"]
    if type(supplied_digest) is not str or _SHA256.fullmatch(supplied_digest) is None:
        raise RezonEvidenceError("evidence_digest must be lowercase SHA-256")
    if _canonical_body_digest(value) != supplied_digest:
        raise RezonEvidenceError("Rezon evidence digest mismatch")

    receipt = value["receipt"]
    if type(receipt) is not dict:
        raise RezonEvidenceError("receipt must be an object")
    _exact_keys(receipt, _RECEIPT_FIELDS, "receipt")

    task_id = _nonempty(receipt["task_id"], "receipt.task_id")
    episode_version = _nonempty(
        receipt["episode_version"],
        "receipt.episode_version",
    )
    if receipt["effect_state"] != "plan":
        raise RezonEvidenceError("outer Rezon evidence may carry PLAN only")
    if receipt["accepted_claim_ids"] != [] or receipt["rejected_claim_ids"] != []:
        raise RezonEvidenceError(
            "generic Rezon run evidence cannot carry claim admission"
        )
    if receipt["claim_disposition_complete"] is not False:
        raise RezonEvidenceError(
            "generic Rezon run evidence cannot assert claim disposition completeness"
        )

    unresolved = _string_list(receipt["unresolved"], "receipt.unresolved")
    receipt_failures = _string_list(receipt["failures"], "receipt.failures")
    receipt_sources = _string_list(
        receipt["source_versions"],
        "receipt.source_versions",
    )
    receipt_execution_ids = _string_list(
        receipt["execution_ids"],
        "receipt.execution_ids",
    )
    receipt_output_bindings = _binding_list(
        receipt["execution_output_digests"],
        "receipt.execution_output_digests",
    )
    receipt_producer_bindings = _binding_list(
        receipt["execution_producer_ids"],
        "receipt.execution_producer_ids",
    )
    task_envelope_digest = _optional_sha256(
        receipt["task_envelope_digest"],
        "receipt.task_envelope_digest",
    )

    executions = value["executions"]
    if type(executions) is not list:
        raise RezonEvidenceError("executions must be a list")

    execution_ids: list[str] = []
    expected_sources: list[str] = []
    expected_failures: list[str] = []
    expected_output_bindings: list[list[str]] = []
    expected_producer_bindings: list[list[str]] = []

    for index, record in enumerate(executions):
        if type(record) is not dict:
            raise RezonEvidenceError(f"execution {index} must be an object")
        _exact_keys(record, _EXECUTION_FIELDS, f"execution {index}")

        execution_id = _nonempty(
            record["execution_id"],
            f"execution {index}.execution_id",
        )
        _nonempty(record["node_id"], f"execution {index}.node_id")
        _nonempty(
            record["episode_version"],
            f"execution {index}.episode_version",
        )
        for field in (
            "visible_proposition_ids",
            "blinded_proposition_ids",
            "visible_relation_ids",
            "blinded_relation_ids",
            "emitted_proposition_ids",
            "source_refs",
            "source_versions",
            "reported_source_refs",
            "reported_source_versions",
            "failures",
        ):
            _string_list(record[field], f"execution {index}.{field}")

        if type(record["independence_demonstrated"]) is not bool:
            raise RezonEvidenceError(
                f"execution {index}.independence_demonstrated must be boolean"
            )
        record_task_digest = _optional_sha256(
            record["task_envelope_digest"],
            f"execution {index}.task_envelope_digest",
        )
        _optional_sha256(
            record["executor_task_specification_digest"],
            f"execution {index}.executor_task_specification_digest",
        )
        _optional_string(
            record["executor_episode_version"],
            f"execution {index}.executor_episode_version",
        )
        producer_id = _optional_string(
            record["canonical_producer_execution_id"],
            f"execution {index}.canonical_producer_execution_id",
        )
        _optional_sha256(
            record["canonical_episode_snapshot_digest"],
            f"execution {index}.canonical_episode_snapshot_digest",
        )
        output_digest = _optional_sha256(
            record["canonical_output_digest"],
            f"execution {index}.canonical_output_digest",
        )

        if execution_id in execution_ids:
            raise RezonEvidenceError("execution IDs must be unique")
        execution_ids.append(execution_id)

        for source_version in record["source_versions"]:
            if source_version not in expected_sources:
                expected_sources.append(source_version)
        for failure in record["failures"]:
            if failure not in expected_failures:
                expected_failures.append(failure)

        if output_digest is not None:
            expected_output_bindings.append([execution_id, output_digest])
        if producer_id is not None:
            expected_producer_bindings.append([execution_id, producer_id])

        if record_task_digest != task_envelope_digest:
            raise RezonEvidenceError(
                "execution task-envelope digest does not match receipt"
            )

    if receipt_execution_ids != execution_ids:
        raise RezonEvidenceError("receipt execution IDs do not match executions")
    if receipt_sources != expected_sources:
        raise RezonEvidenceError("receipt source versions do not match executions")
    if any(failure not in receipt_failures for failure in expected_failures):
        raise RezonEvidenceError(
            "receipt failure summary does not cover execution failures"
        )
    if receipt_output_bindings != expected_output_bindings:
        raise RezonEvidenceError(
            "receipt output bindings do not match executions"
        )
    if receipt_producer_bindings != expected_producer_bindings:
        raise RezonEvidenceError(
            "receipt producer bindings do not match executions"
        )

    return RezonPlanEvidenceObservation(
        evidence_digest=supplied_digest,
        task_id=task_id,
        episode_version=episode_version,
        execution_count=len(executions),
        source_versions=tuple(receipt_sources),
        unresolved=tuple(unresolved),
        failures=tuple(receipt_failures),
    )


__all__ = [
    "REZON_RUN_EVIDENCE_SCHEMA",
    "RezonEvidenceError",
    "RezonPlanEvidenceObservation",
    "validate_rezon_plan_evidence",
]
