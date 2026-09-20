from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest

from runner.rezon_evidence import (
    RezonEvidenceError,
    validate_rezon_plan_evidence,
)


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "runner" / "rezon_evidence.py"
BINDING = ROOT / "registry" / "rezon_plan_evidence_binding.json"


def evidence_fixture() -> dict:
    value = {
        "schema_version": "rezon.run-evidence.v1",
        "receipt": {
            "task_id": "task-boundary-v1",
            "episode_version": "episode-v1",
            "accepted_claim_ids": [],
            "rejected_claim_ids": [],
            "unresolved": ["outer-currentness-not-established"],
            "failures": [],
            "effect_state": "plan",
            "source_versions": ["source:A@v1"],
            "execution_ids": ["exec-1"],
            "execution_output_digests": [["exec-1", "a" * 64]],
            "execution_producer_ids": [["exec-1", "producer-opaque-1"]],
            "task_envelope_digest": "b" * 64,
            "claim_disposition_complete": False,
        },
        "executions": [
            {
                "execution_id": "exec-1",
                "node_id": "bounded-reasoner",
                "episode_version": "episode-v1",
                "visible_proposition_ids": ["p1"],
                "blinded_proposition_ids": [],
                "visible_relation_ids": [],
                "blinded_relation_ids": [],
                "emitted_proposition_ids": ["h1"],
                "independence_demonstrated": False,
                "task_envelope_digest": "b" * 64,
                "executor_task_specification_digest": "c" * 64,
                "executor_episode_version": "episode-v1",
                "canonical_producer_execution_id": "producer-opaque-1",
                "canonical_episode_snapshot_digest": "d" * 64,
                "canonical_output_digest": "a" * 64,
                "source_refs": ["source:A"],
                "source_versions": ["source:A@v1"],
                "reported_source_refs": ["source:A"],
                "reported_source_versions": ["source:A@v1"],
                "failures": [],
            }
        ],
    }
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
    value["evidence_digest"] = hashlib.sha256(encoded).hexdigest()
    return value


class RezonPlanEvidenceBoundaryTests(unittest.TestCase):
    def test_valid_plan_evidence_stays_observational(self):
        observation = validate_rezon_plan_evidence(evidence_fixture())
        self.assertTrue(observation.structurally_consistent)
        self.assertFalse(observation.origin_authenticated)
        self.assertFalse(observation.inner_semantics_independently_verified)
        self.assertFalse(observation.completion_eligible)
        self.assertFalse(observation.authority_eligible)
        self.assertEqual(observation.effect_state, "plan")
        self.assertEqual(observation.execution_count, 1)

    def test_outer_adapter_recomputes_transport_digest(self):
        value = evidence_fixture()
        value["receipt"]["unresolved"].append("tampered")
        with self.assertRaisesRegex(RezonEvidenceError, "digest mismatch"):
            validate_rezon_plan_evidence(value)

    def test_non_plan_effect_state_is_rejected(self):
        value = evidence_fixture()
        value["receipt"]["effect_state"] = "qualified"
        body = {
            "schema_version": value["schema_version"],
            "receipt": value["receipt"],
            "executions": value["executions"],
        }
        value["evidence_digest"] = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        with self.assertRaisesRegex(RezonEvidenceError, "PLAN only"):
            validate_rezon_plan_evidence(value)

    def test_claim_disposition_cannot_self_promote(self):
        value = evidence_fixture()
        value["receipt"]["accepted_claim_ids"] = ["claim-1"]
        body = {
            "schema_version": value["schema_version"],
            "receipt": value["receipt"],
            "executions": value["executions"],
        }
        value["evidence_digest"] = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        with self.assertRaisesRegex(RezonEvidenceError, "cannot carry claim admission"):
            validate_rezon_plan_evidence(value)

    def test_receipt_trace_binding_is_checked_without_rezon_truth_algorithm(self):
        value = evidence_fixture()
        value["receipt"]["execution_output_digests"] = [["exec-1", "e" * 64]]
        body = {
            "schema_version": value["schema_version"],
            "receipt": value["receipt"],
            "executions": value["executions"],
        }
        value["evidence_digest"] = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        with self.assertRaisesRegex(RezonEvidenceError, "output bindings"):
            validate_rezon_plan_evidence(value)

    def test_failure_concealment_is_rejected(self):
        value = evidence_fixture()
        value["executions"][0]["failures"] = ["contract_violation"]
        body = {
            "schema_version": value["schema_version"],
            "receipt": value["receipt"],
            "executions": value["executions"],
        }
        value["evidence_digest"] = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        with self.assertRaisesRegex(RezonEvidenceError, "failure summary"):
            validate_rezon_plan_evidence(value)

    def test_adapter_does_not_expose_backend_or_completion_mapping(self):
        source = MODULE.read_text(encoding="utf-8")
        self.assertNotIn("from .backends", source)
        self.assertNotIn("BackendResult", source)
        self.assertNotIn("WorkUnitStatus.COMPLETE", source)
        self.assertNotIn("TargetAuthorityGrant", source)

    def test_binding_keeps_rezon_and_runner_authority_separate(self):
        binding = json.loads(BINDING.read_text(encoding="utf-8"))
        self.assertFalse(binding["adapter"]["backend_registered"])
        self.assertFalse(binding["adapter"]["completion_eligible"])
        self.assertFalse(binding["adapter"]["authority_eligible"])
        self.assertFalse(
            binding["adapter"]["recomputes_rezon_epistemic_algorithms"]
        )
        self.assertEqual(
            binding["rezon_source"]["hosted_exact_head"],
            "NOT_EXECUTED",
        )


if __name__ == "__main__":
    unittest.main()
