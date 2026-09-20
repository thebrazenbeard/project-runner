from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
from typing import Any


REZON_RUN_EVIDENCE_SCHEMA = "rezon.run-evidence.v1"

_RECEIPT_KEYS = {
    "task_id", "episode_version", "accepted_claim_ids", "rejected_claim_ids",
    "unresolved", "failures", "effect_state", "source_versions",
    "execution_ids", "execution_output_digests", "execution_producer_ids",
    "task_envelope_digest", "claim_disposition_complete",
}
_EXECUTION_KEYS = {
    "execution_id", "node_id", "episode_version", "visible_proposition_ids",
    "blinded_proposition_ids", "visible_relation_ids", "blinded_relation_ids",
    "emitted_proposition_ids", "independence_demonstrated",
    "task_envelope_digest", "executor_task_specification_digest",
    "executor_episode_version", "canonical_producer_execution_id",
    "canonical_episode_snapshot_digest", "canonical_output_digest",
    "source_refs", "source_versions", "reported_source_refs",
    "reported_source_versions", "failures",
}


class RezonEvidenceError(ValueError):
    pass


@dataclass(frozen=True)
class RezonEvidenceVerification:
    """Mechanical result only; no Rezon truth/admission/qualification state."""

    schema_version: str
    evidence_digest: str
    execution_count: int


def _object(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise RezonEvidenceError(f"{label} must be a JSON object")
    return value


def _strings(value: Any, label: str) -> list[str]:
    if type(value) is not list or any(type(item) is not str for item in value):
        raise RezonEvidenceError(f"{label} must be a string array")
    return value


def _pairs(value: Any, label: str) -> list[list[str]]:
    if type(value) is not list or any(
        type(pair) is not list
        or len(pair) != 2
        or any(type(item) is not str for item in pair)
        for pair in value
    ):
        raise RezonEvidenceError(f"{label} must be an array of string pairs")
    return value


def _optional_string(value: Any, label: str) -> str | None:
    if value is not None and type(value) is not str:
        raise RezonEvidenceError(f"{label} must be a string or null")
    return value


def _producer_id(execution: dict[str, Any]) -> str:
    node_id = execution["node_id"]
    snapshot = execution["canonical_episode_snapshot_digest"]
    task_spec = execution["executor_task_specification_digest"]
    output = execution["canonical_output_digest"]
    if type(node_id) is not str or type(snapshot) is not str or type(output) is not str:
        raise RezonEvidenceError("producer-bound execution digests are malformed")
    _optional_string(task_spec, "executor_task_specification_digest")
    payload = "\x1f".join((node_id, snapshot, task_spec or "no-task-spec", output))
    digest = sha256(payload.encode("utf-8")).hexdigest()
    return f"canonical:exec:{node_id}:{digest}"


def verify_rezon_run_evidence(evidence: dict[str, Any]) -> RezonEvidenceVerification:
    """Verify a Rezon v1 export without interpreting its epistemic semantics."""

    evidence = _object(evidence, "run evidence")
    if set(evidence) != {"schema_version", "receipt", "executions", "evidence_digest"}:
        raise RezonEvidenceError("run evidence top-level shape does not match v1")
    if evidence["schema_version"] != REZON_RUN_EVIDENCE_SCHEMA:
        raise RezonEvidenceError("unsupported Rezon run-evidence schema")

    receipt = _object(evidence["receipt"], "receipt")
    if set(receipt) != _RECEIPT_KEYS:
        raise RezonEvidenceError("receipt shape does not match v1")

    raw_executions = evidence["executions"]
    if type(raw_executions) is not list:
        raise RezonEvidenceError("executions must be a JSON array")
    executions = [_object(item, f"executions[{i}]") for i, item in enumerate(raw_executions)]
    if any(set(execution) != _EXECUTION_KEYS for execution in executions):
        raise RezonEvidenceError("execution shape does not match v1")

    digest = evidence["evidence_digest"]
    if type(digest) is not str:
        raise RezonEvidenceError("evidence_digest must be a string")
    body = {key: value for key, value in evidence.items() if key != "evidence_digest"}
    encoded = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    if not hmac.compare_digest(digest, sha256(encoded).hexdigest()):
        raise RezonEvidenceError("evidence digest mismatch")

    execution_ids = _strings(receipt["execution_ids"], "receipt.execution_ids")
    observed_ids = [execution["execution_id"] for execution in executions]
    if any(type(item) is not str for item in observed_ids) or execution_ids != observed_ids:
        raise RezonEvidenceError("receipt execution ids do not match executions")

    observed_versions: list[str] = []
    for i, execution in enumerate(executions):
        for version in _strings(execution["source_versions"], f"executions[{i}].source_versions"):
            if version not in observed_versions:
                observed_versions.append(version)
    if _strings(receipt["source_versions"], "receipt.source_versions") != observed_versions:
        raise RezonEvidenceError("receipt source versions do not match executions")

    receipt_failures = _strings(receipt["failures"], "receipt.failures")
    for i, execution in enumerate(executions):
        if any(
            failure not in receipt_failures
            for failure in _strings(execution["failures"], f"executions[{i}].failures")
        ):
            raise RezonEvidenceError("receipt failure summary does not cover executions")

    task_digest = _optional_string(receipt["task_envelope_digest"], "receipt.task_envelope_digest")
    output_bindings: list[list[str]] = []
    producer_bindings: list[list[str]] = []
    for i, execution in enumerate(executions):
        execution_id = execution["execution_id"]
        if _optional_string(execution["task_envelope_digest"], f"executions[{i}].task_envelope_digest") != task_digest:
            raise RezonEvidenceError("task envelope binding mismatch")
        output = _optional_string(execution["canonical_output_digest"], f"executions[{i}].canonical_output_digest")
        producer = _optional_string(execution["canonical_producer_execution_id"], f"executions[{i}].canonical_producer_execution_id")
        if output is not None:
            output_bindings.append([execution_id, output])
        if producer is not None:
            producer_bindings.append([execution_id, producer])
            if producer != _producer_id(execution):
                raise RezonEvidenceError("canonical producer identity does not recompute")

    if _pairs(receipt["execution_output_digests"], "receipt.execution_output_digests") != output_bindings:
        raise RezonEvidenceError("output bindings do not match executions")
    if _pairs(receipt["execution_producer_ids"], "receipt.execution_producer_ids") != producer_bindings:
        raise RezonEvidenceError("producer bindings do not match executions")

    return RezonEvidenceVerification(
        schema_version=REZON_RUN_EVIDENCE_SCHEMA,
        evidence_digest=digest,
        execution_count=len(executions),
    )
