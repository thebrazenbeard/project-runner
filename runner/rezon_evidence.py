from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any, Mapping


REZON_RUN_EVIDENCE_SCHEMA = "rezon.run-evidence.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class RezonEvidenceError(ValueError):
    pass


@dataclass(frozen=True)
class RezonEvidenceVerification:
    evidence_digest: str
    execution_count: int
    receipt_failure_count: int
    trace_failure_count: int
    source_versions: tuple[str, ...]
    status: str = "STRUCTURALLY_VALID_NON_PROMOTIONAL"


_TOP_LEVEL_FIELDS = {
    "schema_version",
    "receipt",
    "executions",
    "evidence_digest",
}
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


def _require_exact_fields(
    value: Mapping[str, Any],
    expected: set[str],
    label: str,
) -> None:
    keys = set(value)
    missing = expected - keys
    extra = keys - expected
    if missing:
        raise RezonEvidenceError(f"{label} missing fields: {sorted(missing)}")
    if extra:
        raise RezonEvidenceError(f"{label} unexpected fields: {sorted(extra)}")


def _string(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if type(value) is not str or (not allow_empty and not value):
        raise RezonEvidenceError(f"{label} must be an exact string")
    return value


def _optional_string(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _string(value, label)


def _sha256_string(value: Any, label: str) -> str:
    value = _string(value, label)
    if _SHA256.fullmatch(value) is None:
        raise RezonEvidenceError(f"{label} must be lowercase SHA-256")
    return value


def _optional_sha256(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _sha256_string(value, label)


def _string_list(value: Any, label: str) -> list[str]:
    if type(value) is not list:
        raise RezonEvidenceError(f"{label} must be a list")
    out: list[str] = []
    for index, item in enumerate(value):
        out.append(_string(item, f"{label}[{index}]"))
    return out


def _pair_list(value: Any, label: str) -> list[list[str]]:
    if type(value) is not list:
        raise RezonEvidenceError(f"{label} must be a list")
    out: list[list[str]] = []
    seen_execution_ids: set[str] = set()
    for index, item in enumerate(value):
        if type(item) is not list or len(item) != 2:
            raise RezonEvidenceError(f"{label}[{index}] must be a two-string list")
        execution_id = _string(item[0], f"{label}[{index}][0]")
        if execution_id in seen_execution_ids:
            raise RezonEvidenceError(f"{label} cannot duplicate execution id")
        seen_execution_ids.add(execution_id)
        out.append(
            [
                execution_id,
                _string(item[1], f"{label}[{index}][1]"),
            ]
        )
    return out


def _canonical_body_digest(evidence: Mapping[str, Any]) -> str:
    body = {
        "schema_version": evidence["schema_version"],
        "receipt": evidence["receipt"],
        "executions": evidence["executions"],
    }
    encoded = json.dumps(
        body,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def verify_rezon_run_evidence(
    evidence: Mapping[str, Any],
) -> RezonEvidenceVerification:
    """Verify Rezon run evidence without interpreting Rezon epistemics.

    This verifier checks deterministic structural bindings only. It does not
    decide truth, admission, qualification, authority, completion, or whether
    accepted/rejected/unresolved claim IDs are semantically correct.
    """
    if type(evidence) is not dict:
        raise RezonEvidenceError("run evidence must be an exact object")
    _require_exact_fields(evidence, _TOP_LEVEL_FIELDS, "run evidence")

    if evidence["schema_version"] != REZON_RUN_EVIDENCE_SCHEMA:
        raise RezonEvidenceError("unsupported Rezon run-evidence schema")

    digest = _string(evidence["evidence_digest"], "evidence_digest")
    if _SHA256.fullmatch(digest) is None:
        raise RezonEvidenceError("evidence_digest must be lowercase SHA-256")
    expected_digest = _canonical_body_digest(evidence)
    if digest != expected_digest:
        raise RezonEvidenceError("evidence digest does not match canonical body")

    receipt = evidence["receipt"]
    executions = evidence["executions"]
    if type(receipt) is not dict:
        raise RezonEvidenceError("receipt must be an exact object")
    if type(executions) is not list:
        raise RezonEvidenceError("executions must be a list")
    _require_exact_fields(receipt, _RECEIPT_FIELDS, "receipt")

    _string(receipt["task_id"], "receipt.task_id")
    _string(receipt["episode_version"], "receipt.episode_version")
    accepted_claim_ids = _string_list(
        receipt["accepted_claim_ids"],
        "receipt.accepted_claim_ids",
    )
    rejected_claim_ids = _string_list(
        receipt["rejected_claim_ids"],
        "receipt.rejected_claim_ids",
    )
    if accepted_claim_ids or rejected_claim_ids:
        raise RezonEvidenceError(
            "generic Rezon run evidence cannot carry claim disposition"
        )
    _string_list(receipt["unresolved"], "receipt.unresolved")
    receipt_failures = _string_list(receipt["failures"], "receipt.failures")
    if receipt["effect_state"] != "plan":
        raise RezonEvidenceError("Rezon run evidence must remain PLAN-only")
    receipt_sources = _string_list(
        receipt["source_versions"],
        "receipt.source_versions",
    )
    receipt_execution_ids = _string_list(
        receipt["execution_ids"],
        "receipt.execution_ids",
    )
    receipt_output_bindings = _pair_list(
        receipt["execution_output_digests"],
        "receipt.execution_output_digests",
    )
    receipt_producer_bindings = _pair_list(
        receipt["execution_producer_ids"],
        "receipt.execution_producer_ids",
    )
    receipt_task_digest = _optional_sha256(
        receipt["task_envelope_digest"],
        "receipt.task_envelope_digest",
    )
    if type(receipt["claim_disposition_complete"]) is not bool:
        raise RezonEvidenceError("receipt.claim_disposition_complete must be bool")
    if receipt["claim_disposition_complete"]:
        raise RezonEvidenceError(
            "generic Rezon run evidence cannot assert claim disposition completeness"
        )

    expected_execution_ids: list[str] = []
    expected_sources: list[str] = []
    expected_output_bindings: list[list[str]] = []
    expected_producer_bindings: list[list[str]] = []
    trace_failures: list[str] = []

    for index, record in enumerate(executions):
        if type(record) is not dict:
            raise RezonEvidenceError(f"executions[{index}] must be an exact object")
        _require_exact_fields(record, _EXECUTION_FIELDS, f"executions[{index}]")

        execution_id = _string(
            record["execution_id"],
            f"executions[{index}].execution_id",
        )
        _string(record["node_id"], f"executions[{index}].node_id")
        _string(record["episode_version"], f"executions[{index}].episode_version")

        for field in (
            "visible_proposition_ids",
            "blinded_proposition_ids",
            "visible_relation_ids",
            "blinded_relation_ids",
            "emitted_proposition_ids",
            "source_refs",
            "reported_source_refs",
            "reported_source_versions",
        ):
            _string_list(record[field], f"executions[{index}].{field}")

        if type(record["independence_demonstrated"]) is not bool:
            raise RezonEvidenceError(
                f"executions[{index}].independence_demonstrated must be bool"
            )

        task_digest = _optional_sha256(
            record["task_envelope_digest"],
            f"executions[{index}].task_envelope_digest",
        )
        _optional_sha256(
            record["executor_task_specification_digest"],
            f"executions[{index}].executor_task_specification_digest",
        )
        _optional_string(
            record["executor_episode_version"],
            f"executions[{index}].executor_episode_version",
        )
        producer_id = _optional_string(
            record["canonical_producer_execution_id"],
            f"executions[{index}].canonical_producer_execution_id",
        )
        snapshot_digest = _optional_sha256(
            record["canonical_episode_snapshot_digest"],
            f"executions[{index}].canonical_episode_snapshot_digest",
        )
        output_digest = _optional_sha256(
            record["canonical_output_digest"],
            f"executions[{index}].canonical_output_digest",
        )
        sources = _string_list(
            record["source_versions"],
            f"executions[{index}].source_versions",
        )
        failures = _string_list(
            record["failures"],
            f"executions[{index}].failures",
        )

        if task_digest != receipt_task_digest:
            raise RezonEvidenceError("receipt task envelope digest does not match trace")
        if producer_id is not None and (
            snapshot_digest is None or output_digest is None
        ):
            raise RezonEvidenceError(
                "canonical producer binding requires snapshot and output digests"
            )

        expected_execution_ids.append(execution_id)
        for source in sources:
            if source not in expected_sources:
                expected_sources.append(source)
        for failure in failures:
            if failure not in trace_failures:
                trace_failures.append(failure)
        if output_digest is not None:
            expected_output_bindings.append([execution_id, output_digest])
        if producer_id is not None:
            expected_producer_bindings.append([execution_id, producer_id])

    if receipt_execution_ids != expected_execution_ids:
        raise RezonEvidenceError("receipt execution ids do not match trace")
    if receipt_sources != expected_sources:
        raise RezonEvidenceError("receipt source versions do not match trace")
    if receipt_output_bindings != expected_output_bindings:
        raise RezonEvidenceError("receipt output bindings do not match trace")
    if receipt_producer_bindings != expected_producer_bindings:
        raise RezonEvidenceError("receipt producer bindings do not match trace")

    missing_failures = [
        failure for failure in trace_failures if failure not in receipt_failures
    ]
    if missing_failures:
        raise RezonEvidenceError("receipt failure summary does not cover trace failures")

    return RezonEvidenceVerification(
        evidence_digest=digest,
        execution_count=len(executions),
        receipt_failure_count=len(receipt_failures),
        trace_failure_count=len(trace_failures),
        source_versions=tuple(receipt_sources),
    )


__all__ = [
    "REZON_RUN_EVIDENCE_SCHEMA",
    "RezonEvidenceError",
    "RezonEvidenceVerification",
    "verify_rezon_run_evidence",
]
