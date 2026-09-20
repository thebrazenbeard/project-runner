from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from runner.rezon_evidence import verify_rezon_run_evidence


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "rezon_run_evidence_failure_v1.json"
BINDING = ROOT / "tests" / "fixtures" / "rezon_run_evidence_failure_v1.binding.json"


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


def test_real_rezon_failure_fixture_passes_unchanged_verifier():
    evidence = load_fixture()
    result = verify_rezon_run_evidence(evidence)

    assert result.status == "STRUCTURALLY_VALID_NON_PROMOTIONAL"
    assert result.evidence_digest == (
        "516146d1f01291510e5b31e645520ed5434760ff953139d6aba71ea4cc37e752"
    )
    assert result.execution_count == 1
    assert result.receipt_failure_count == 1
    assert result.trace_failure_count == 1
    assert result.source_versions == ("source:failure-fixture@v1",)


def test_failure_fixture_persisted_bytes_are_exactly_bound():
    binding = json.loads(BINDING.read_text(encoding="utf-8"))
    assert sha256(FIXTURE.read_bytes()).hexdigest() == (
        binding["fixture"]["persisted_fixture_sha256_lf"]
    )
    assert binding["fixture"]["source_generated_sha256_windows_crlf"] == (
        "938ca1cfc60e055e61fa11f27156fa4226ee27f2dd0d9ff78348c0dfa04783a1"
    )
    assert binding["fixture"]["transport_normalization"] == "CRLF_TO_LF_ONLY"


def test_failure_taxonomy_remains_opaque_if_coverage_is_preserved():
    evidence = load_fixture()
    native_future_failure = "future_rezon_failure_runner_must_not_interpret"
    evidence["executions"][0]["failures"] = [native_future_failure]
    evidence["receipt"]["failures"] = [native_future_failure]
    rehash(evidence)

    result = verify_rezon_run_evidence(evidence)

    assert result.status == "STRUCTURALLY_VALID_NON_PROMOTIONAL"
    assert result.receipt_failure_count == 1
    assert result.trace_failure_count == 1


def test_unresolved_marker_is_opaque_not_runner_completion_semantics():
    evidence = load_fixture()
    evidence["receipt"]["unresolved"] = [
        "future:opaque:rezon:unresolved:marker"
    ]
    rehash(evidence)

    result = verify_rezon_run_evidence(evidence)

    assert result.status == "STRUCTURALLY_VALID_NON_PROMOTIONAL"
    assert not hasattr(result, "complete")
    assert not hasattr(result, "admitted")
    assert not hasattr(result, "truth")


def test_binding_requires_unchanged_production_verifier():
    binding = json.loads(BINDING.read_text(encoding="utf-8"))
    verifier = binding["runner_verifier"]
    assert verifier["git_blob_sha1"] == (
        "d7827dec743e69fff7f981d91d7a86f6cd4a4839"
    )
    assert verifier["production_change_required"] is False


def test_real_failure_fixture_contains_no_output_or_producer_binding():
    evidence = load_fixture()
    assert evidence["receipt"]["execution_output_digests"] == []
    assert evidence["receipt"]["execution_producer_ids"] == []
    assert evidence["executions"][0]["canonical_output_digest"] is None
    assert evidence["executions"][0]["canonical_producer_execution_id"] is None
