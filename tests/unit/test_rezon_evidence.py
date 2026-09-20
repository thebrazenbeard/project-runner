from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from runner.rezon_evidence import (
    RezonEvidenceError,
    verify_rezon_run_evidence,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "rezon_run_evidence_v1.json"
FAILURE_FIXTURE = ROOT / "tests" / "fixtures" / "rezon_run_evidence_failure_v1.json"
BINDING = ROOT / "tests" / "fixtures" / "rezon_run_evidence_v1.binding.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def rehash(evidence: dict) -> dict:
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
    evidence["evidence_digest"] = sha256(encoded).hexdigest()
    return evidence


def test_real_rezon_r51_fixture_verifies_mechanically():
    evidence = load_fixture()
    result = verify_rezon_run_evidence(evidence)
    assert result.status == "STRUCTURALLY_VALID_NON_PROMOTIONAL"
    assert result.evidence_digest == (
        "98bca73ae71697601cd7c9c10e2067cd8fef83aa58e7bad2f1fec59c18508c48"
    )
    assert result.execution_count == 1
    assert result.source_versions == ("source:fixture@v1",)


def test_fixture_file_is_bound_to_exact_generated_bytes():
    binding = json.loads(BINDING.read_text(encoding="utf-8"))
    raw = FIXTURE.read_bytes()
    assert sha256(raw).hexdigest() == binding["fixture"]["persisted_fixture_sha256_lf"]
    assert binding["source"]["exact_head"] == (
        "8289914ec500a1392b10fe1a3774dee166e73b40"
    )
    assert binding["fixture"]["generation_method"].endswith("NO_PACKAGE_INSTALL")
    assert binding["fixture"]["source_generated_sha256_windows_crlf"] == (
        "86266b74d807e3fb98fec13a5f8ccd2d05ff509b27bd3beb7e2abfe61e4952b5"
    )
    assert binding["fixture"]["transport_normalization"] == "CRLF_TO_LF_ONLY"


def test_digest_tampering_fails_closed():
    evidence = load_fixture()
    evidence["receipt"]["task_id"] = "forged-task"
    with pytest.raises(RezonEvidenceError, match="digest"):
        verify_rezon_run_evidence(evidence)


def test_trace_failure_cannot_be_hidden_by_receipt_after_valid_rehash():
    evidence = load_fixture()
    evidence["executions"][0]["failures"] = ["contract_violation"]
    rehash(evidence)
    with pytest.raises(RezonEvidenceError, match="failure summary"):
        verify_rezon_run_evidence(evidence)


def test_receipt_source_versions_must_match_trace_ordered_dedupe():
    evidence = load_fixture()
    evidence["receipt"]["source_versions"] = ["source:forged@v9"]
    rehash(evidence)
    with pytest.raises(RezonEvidenceError, match="source versions"):
        verify_rezon_run_evidence(evidence)


def test_non_plan_effect_state_cannot_be_promoted_through_runner():
    evidence = load_fixture()
    evidence["receipt"]["effect_state"] = "qualified"
    rehash(evidence)
    with pytest.raises(RezonEvidenceError, match="PLAN-only"):
        verify_rezon_run_evidence(evidence)


def test_generic_receipt_cannot_carry_claim_dispositions():
    evidence = load_fixture()
    evidence["receipt"]["accepted_claim_ids"] = ["claim-runner-must-not-interpret"]
    rehash(evidence)
    with pytest.raises(RezonEvidenceError, match="claim disposition"):
        verify_rezon_run_evidence(evidence)

    evidence = load_fixture()
    evidence["receipt"]["rejected_claim_ids"] = ["another-opaque-claim"]
    rehash(evidence)
    with pytest.raises(RezonEvidenceError, match="claim disposition"):
        verify_rezon_run_evidence(evidence)

    evidence = load_fixture()
    evidence["receipt"]["claim_disposition_complete"] = True
    rehash(evidence)
    with pytest.raises(RezonEvidenceError, match="disposition completeness"):
        verify_rezon_run_evidence(evidence)


def test_duplicate_execution_bindings_are_rejected():
    evidence = load_fixture()
    record = deepcopy(evidence["executions"][0])
    evidence["executions"].append(record)
    evidence["receipt"]["execution_ids"].append(record["execution_id"])
    evidence["receipt"]["execution_output_digests"].append(
        deepcopy(evidence["receipt"]["execution_output_digests"][0])
    )
    evidence["receipt"]["execution_producer_ids"].append(
        deepcopy(evidence["receipt"]["execution_producer_ids"][0])
    )
    rehash(evidence)

    with pytest.raises(RezonEvidenceError, match="duplicate execution id"):
        verify_rezon_run_evidence(evidence)


def test_duplicate_failure_execution_ids_are_rejected_without_bindings():
    evidence = json.loads(FAILURE_FIXTURE.read_text(encoding="utf-8"))
    record = deepcopy(evidence["executions"][0])
    evidence["executions"].append(record)
    evidence["receipt"]["execution_ids"].append(record["execution_id"])
    assert evidence["receipt"]["execution_output_digests"] == []
    assert evidence["receipt"]["execution_producer_ids"] == []
    rehash(evidence)

    with pytest.raises(RezonEvidenceError, match="duplicate execution id"):
        verify_rezon_run_evidence(evidence)


def test_canonical_output_digest_must_be_sha256():
    evidence = load_fixture()
    evidence["executions"][0]["canonical_output_digest"] = "not-a-digest"
    evidence["receipt"]["execution_output_digests"][0][1] = "not-a-digest"
    rehash(evidence)

    with pytest.raises(RezonEvidenceError, match="lowercase SHA-256"):
        verify_rezon_run_evidence(evidence)


def test_task_envelope_digest_must_be_sha256():
    evidence = load_fixture()
    evidence["executions"][0]["task_envelope_digest"] = "not-a-digest"
    evidence["receipt"]["task_envelope_digest"] = "not-a-digest"
    rehash(evidence)

    with pytest.raises(RezonEvidenceError, match="lowercase SHA-256"):
        verify_rezon_run_evidence(evidence)


def test_producer_binding_requires_snapshot_and_output_digests():
    evidence = load_fixture()
    evidence["executions"][0]["canonical_episode_snapshot_digest"] = None
    rehash(evidence)

    with pytest.raises(
        RezonEvidenceError,
        match="requires snapshot and output digests",
    ):
        verify_rezon_run_evidence(evidence)


def test_unknown_schema_field_fails_closed():
    evidence = load_fixture()
    evidence["runner_should_not_guess"] = True
    rehash(evidence)
    with pytest.raises(RezonEvidenceError, match="unexpected fields"):
        verify_rezon_run_evidence(evidence)


def test_binding_forbids_epistemic_authority_transfer():
    binding = json.loads(BINDING.read_text(encoding="utf-8"))
    forbidden = set(binding["verifier_boundary"]["must_not_decide"])
    assert {
        "REZON_TRUTH",
        "REZON_ADMISSION",
        "REZON_CLAIM_CORRECTNESS",
        "REZON_QUALIFICATION",
        "REZON_AUTHORITY",
        "EXTERNAL_EFFECT_AUTHORIZATION",
    } <= forbidden
