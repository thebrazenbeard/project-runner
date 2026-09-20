from __future__ import annotations

import json
from typing import Any

from .backends import BackendResult
from .github_backend import GitHubOperation, GitHubRequest
from .verify import VerificationOutcome
from .work_units import WorkUnit, WorkUnitStatus, work_unit_fingerprint


DISCOVERY_EFFECT_SCHEMA_VERSION = "DISCOVERY_EFFECT_ATTEMPT_V0"
PROJECT_RUNNER_SOURCE_REF = (
    "work/exodus-current-m6-discovery-v1-20260919"
    "@bee7e720ba923ef38ce87fca4c9c2560163a9360"
)


def _request(work: WorkUnit) -> GitHubRequest:
    if type(work) is not WorkUnit:
        raise ValueError("work must be exact WorkUnit")
    raw = work.payload.get("github")
    if not isinstance(raw, dict):
        raise ValueError("work payload missing github request")
    request = GitHubRequest.from_mapping(raw)
    if request.operation not in {
        GitHubOperation.CREATE_BRANCH,
        GitHubOperation.PUT_FILE,
    }:
        raise ValueError("only consequential GitHub mutations map to effect envelope")
    return request


def _target(request: GitHubRequest) -> dict[str, str | None]:
    if request.operation is GitHubOperation.CREATE_BRANCH:
        locator = f"{request.repository}@{request.ref}"
        expected = json.dumps(
            {
                "source_ref": request.source_ref,
                "expected_head": request.expected_head,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return {
            "kind": "github-branch",
            "locator": locator,
            "expected_precondition": expected,
        }

    assert request.operation is GitHubOperation.PUT_FILE
    if request.path is None:
        raise ValueError("PUT_FILE request requires path")
    expected = json.dumps(
        {
            "expected_head": request.expected_head,
            "expected_blob_sha": request.expected_blob_sha,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "kind": "github-file",
        "locator": f"{request.repository}:{request.path}@{request.ref}",
        "expected_precondition": expected,
    }


def _base_envelope(work: WorkUnit) -> dict[str, Any]:
    request = _request(work)
    return {
        "schema_version": DISCOVERY_EFFECT_SCHEMA_VERSION,
        "source_system": "project-runner",
        "source_operation_id": work_unit_fingerprint(work),
        "source_state": work.status.value,
        "source_ref": PROJECT_RUNNER_SOURCE_REF,
        "source_payload_sha256": work_unit_fingerprint(work),
        "action_class": f"GITHUB_{request.operation.value}",
        "target": _target(request),
        "normalized_phase": "PRE_EFFECT",
        "retry_disposition": "DOMAIN_DECIDES",
        "receipts": [
            {"kind": "work_id", "value": work.id},
            {"kind": "root_frontier_id", "value": work.root_frontier_id},
        ],
    }


def pre_effect_envelope(work: WorkUnit) -> dict[str, Any]:
    """Export a mutation work unit before execution.

    The envelope is observational/interchange-only and carries no target
    authority, lease authority, retry authority, or permission to execute.
    """
    return _base_envelope(work)


_PHASE_BY_STATUS = {
    WorkUnitStatus.VERIFYING: "POST_EFFECT_UNVERIFIED",
    WorkUnitStatus.COMPLETE: "POST_EFFECT_VERIFIED",
    WorkUnitStatus.FAILED_DETERMINISTIC: "TERMINAL_FAILURE",
    WorkUnitStatus.OUTCOME_UNKNOWN: "OUTCOME_UNKNOWN",
}

_RETRY_BY_STATUS = {
    WorkUnitStatus.VERIFYING: "DOMAIN_DECIDES",
    WorkUnitStatus.COMPLETE: "DO_NOT_RETRY",
    WorkUnitStatus.FAILED_DETERMINISTIC: "DOMAIN_DECIDES",
    WorkUnitStatus.OUTCOME_UNKNOWN: "INSPECT_BEFORE_RETRY",
}


def verification_outcome_envelope(
    *,
    work: WorkUnit,
    result: BackendResult,
    outcome: VerificationOutcome,
) -> dict[str, Any]:
    """Export a native verification result without replacing native semantics."""
    if type(result) is not BackendResult:
        raise ValueError("result must be exact BackendResult")
    if type(outcome) is not VerificationOutcome:
        raise ValueError("outcome must be exact VerificationOutcome")
    fingerprint = work_unit_fingerprint(work)
    if result.work_fingerprint != fingerprint:
        raise ValueError("backend result fingerprint does not match work")
    if outcome.work != work:
        raise ValueError("verification outcome does not bind the supplied work")
    if outcome.status is WorkUnitStatus.SUPERSEDED:
        raise ValueError(
            "SUPERSEDED is source-native currentness state, not a normalized effect outcome"
        )
    if outcome.status not in _PHASE_BY_STATUS:
        raise ValueError(
            f"unsupported verification status for effect envelope: {outcome.status.value}"
        )

    envelope = _base_envelope(work)
    envelope["source_state"] = outcome.status.value
    envelope["normalized_phase"] = _PHASE_BY_STATUS[outcome.status]
    envelope["retry_disposition"] = _RETRY_BY_STATUS[outcome.status]

    receipts = list(envelope["receipts"])
    receipts.extend(
        [
            {"kind": "backend_classification", "value": result.classification},
            {"kind": "verification_reason", "value": outcome.reason},
        ]
    )
    for index, value in enumerate(result.outputs):
        receipts.append({"kind": f"backend_output_{index}", "value": value})
    for index, value in enumerate(result.evidence):
        receipts.append({"kind": f"backend_evidence_{index}", "value": value})
    if outcome.status is WorkUnitStatus.COMPLETE:
        receipts.append(
            {
                "kind": "claim_ceiling",
                "value": "NATIVE_COMPLETION_EVIDENCE_VERIFIED",
            }
        )
    elif outcome.status is WorkUnitStatus.OUTCOME_UNKNOWN:
        receipts.append(
            {
                "kind": "claim_ceiling",
                "value": "EFFECT_MAY_HAVE_OCCURRED_RECONCILE_BEFORE_RETRY",
            }
        )
    envelope["receipts"] = receipts
    return envelope


__all__ = [
    "DISCOVERY_EFFECT_SCHEMA_VERSION",
    "PROJECT_RUNNER_SOURCE_REF",
    "pre_effect_envelope",
    "verification_outcome_envelope",
]
