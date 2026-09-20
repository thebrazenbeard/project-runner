from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json

import pytest

from runner.rezon_evidence import RezonEvidenceError, verify_rezon_run_evidence


def _producer_id(node_id: str, snapshot: str, task_spec: str | None, output: str) -> str:
    payload = "\x1f".join((node_id, snapshot, task_spec or "no-task-spec", output))
    return f"canonical:exec:{node_id}:{sha256(payload.encode('utf-8')).hexdigest()}"


def _evidence() -> dict[str, object]:
    execution_id = "exec-1"
    node_id = "opaque-node"
    snapshot = "a" * 64
    output = "b" * 64
    task_spec = "c" * 64
    task_envelope = "d" * 64
    producer_id = _producer_id(node_id, snapshot, task_spec, output)

    body = {
        "schema_version": "rezon.run-evidence.v1",
        "receipt": {
            "task_id": "opaque-task",
            "episode_version": 7,
            "accepted_claim_ids": ["claim-content-not-interpreted"],
            "rejected_claim_ids": [],
            "unresolved": ["opaque-unresolved"],
            "failures": ["OPAQUE_FAILURE"],
            "effect_state": "PLAN",
            "source_versions": ["source-v1"],
            "execution_ids": [execution_id],
            "execution_output_digests": [[execution_id, output]],
            "execution_producer_ids": [[execution_id, producer_id]],
            "task_envelope_digest": task_envelope,
            "claim_disposition_complete": False,
        },
        "executions": [
            {
                "execution_id": execution_id,
                "node_id": node_id,
                "episode_version": 7,
                "visible_proposition_ids": ["p-visible"],
                "blinded_proposition_ids": ["p-hidden"],
                "visible_relation_ids": [],
                "blinded_relation_ids": [],
                "emitted_proposition_ids": ["p-output"],
                "independence_demonstrated": False,
                "task_envelope_digest": task_envelope,
                "executor_task_specification_digest": task_spec,
                "executor_episode_version": 7,
                "canonical_producer_execution_id": producer_id,
                "canonical_episode_snapshot_digest": snapshot,
                "canonical_output_digest": output,
                "source_refs": ["opaque-source"],
                "source_versions": ["source-v1"],
                "reported_source_refs": [],
                "reported_source_versions": [],
                "failures": ["OPAQUE_FAILURE"],
            }
        ],
    }
    encoded = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return {**body, "evidence_digest": sha256(encoded).hexdigest()}


def _redigest(evidence: dict[str, object]) -> None:
    body = {key: value for key, value in evidence.items() if key != "evidence_digest"}
    encoded = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    evidence["evidence_digest"] = sha256(encoded).hexdigest()


def test_structurally_valid_evidence_is_accepted_without_epistemic_interpretation():
    evidence = _evidence()

    result = verify_rezon_run_evidence(evidence)

    assert result.execution_count == 1
    assert asdict(result) == {
        "schema_version": "rezon.run-evidence.v1",
        "evidence_digest": evidence["evidence_digest"],
        "execution_count": 1,
    }


def test_forged_evidence_digest_fails_closed():
    evidence = _evidence()
    evidence["evidence_digest"] = "0" * 64

    with pytest.raises(RezonEvidenceError, match="digest mismatch"):
        verify_rezon_run_evidence(evidence)


def test_mismatched_receipt_binding_fails_even_with_matching_outer_digest():
    evidence = _evidence()
    evidence["receipt"]["execution_ids"] = ["forged-exec"]
    _redigest(evidence)

    with pytest.raises(RezonEvidenceError, match="execution ids"):
        verify_rezon_run_evidence(evidence)


def test_execution_failure_must_be_covered_by_receipt_summary():
    evidence = _evidence()
    evidence["receipt"]["failures"] = []
    _redigest(evidence)

    with pytest.raises(RezonEvidenceError, match="failure summary"):
        verify_rezon_run_evidence(evidence)


def test_canonical_producer_binding_is_recomputed():
    evidence = _evidence()
    evidence["executions"][0]["canonical_producer_execution_id"] = (
        "canonical:exec:opaque-node:" + "0" * 64
    )
    evidence["receipt"]["execution_producer_ids"][0][1] = (
        evidence["executions"][0]["canonical_producer_execution_id"]
    )
    _redigest(evidence)

    with pytest.raises(RezonEvidenceError, match="producer identity"):
        verify_rezon_run_evidence(evidence)


def test_verification_is_read_only_and_does_not_promote_claims():
    evidence = _evidence()
    before = deepcopy(evidence)

    result = verify_rezon_run_evidence(evidence)

    assert evidence == before
    assert "admission" not in asdict(result)
    assert "truth" not in asdict(result)
    assert "qualification" not in asdict(result)
