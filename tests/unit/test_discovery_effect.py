from __future__ import annotations

import copy

import pytest

from runner.backends import BackendResult
from runner.discovery_effect import (
    pre_effect_envelope,
    verification_outcome_envelope,
)
from runner.models import ExactSubject
from runner.verify import VerificationOutcome
from runner.work_units import WorkUnit, WorkUnitStatus, work_unit_fingerprint


def mutation_work(operation: str = "PUT_FILE") -> WorkUnit:
    subject = ExactSubject(
        repository="thebrazenbeard/project-runner",
        ref="proof/discovery-envelope",
        commit="a" * 40,
    )
    if operation == "PUT_FILE":
        request = {
            "operation": "PUT_FILE",
            "repository": "thebrazenbeard/project-runner",
            "ref": "proof/discovery-envelope",
            "path": "README.md",
            "content": "updated\n",
            "message": "test",
            "expected_head": "a" * 40,
            "expected_blob_sha": "b" * 40,
        }
    elif operation == "CREATE_BRANCH":
        request = {
            "operation": "CREATE_BRANCH",
            "repository": "thebrazenbeard/project-runner",
            "ref": "proof/discovery-envelope",
            "source_ref": "main",
            "expected_head": "a" * 40,
        }
    else:
        request = {
            "operation": operation,
            "repository": "thebrazenbeard/project-runner",
            "ref": "main",
            "expected_head": "a" * 40,
        }

    return WorkUnit(
        id="discovery-effect-test",
        root_frontier_id="frontier-discovery-effect-test",
        parent_work_id=None,
        inputs=(subject,),
        operation="GITHUB",
        required_capabilities=("github.put_file",),
        collision_keys=("repo:project-runner",),
        recursion_depth=0,
        budget_allocation={
            "children": 0,
            "active": 1,
            "retries": 0,
            "backend_jobs": 1,
        },
        expected_outputs=("github-result",),
        completion_criteria=(
            "exact-precondition",
            "independent-postcondition-readback",
        ),
        status=WorkUnitStatus.RUNNING,
        payload={"github": request},
    )


def backend_result(work: WorkUnit, *, succeeded: bool = True) -> BackendResult:
    return BackendResult(
        work_fingerprint=work_unit_fingerprint(work),
        succeeded=succeeded,
        outputs=("c" * 40, "d" * 40) if succeeded else (),
        evidence=("github:put-file", "github:readback-verified"),
        classification="SUCCEEDED" if succeeded else "TRANSPORT_FAILED",
    )


def outcome(work: WorkUnit, status: WorkUnitStatus, reason: str) -> VerificationOutcome:
    return VerificationOutcome(work=work, status=status, reason=reason)


def test_pre_effect_export_binds_target_and_precondition_without_authority():
    work = mutation_work()
    envelope = pre_effect_envelope(work)
    assert envelope["normalized_phase"] == "PRE_EFFECT"
    assert envelope["retry_disposition"] == "DOMAIN_DECIDES"
    assert envelope["target"]["kind"] == "github-file"
    assert envelope["source_operation_id"] == work_unit_fingerprint(work)
    assert envelope["source_payload_sha256"] == work_unit_fingerprint(work)


@pytest.mark.parametrize(
    ("status", "phase", "retry"),
    [
        (WorkUnitStatus.VERIFYING, "POST_EFFECT_UNVERIFIED", "DOMAIN_DECIDES"),
        (WorkUnitStatus.COMPLETE, "POST_EFFECT_VERIFIED", "DO_NOT_RETRY"),
        (WorkUnitStatus.FAILED_DETERMINISTIC, "TERMINAL_FAILURE", "DOMAIN_DECIDES"),
        (WorkUnitStatus.OUTCOME_UNKNOWN, "OUTCOME_UNKNOWN", "INSPECT_BEFORE_RETRY"),
    ],
)
def test_native_verification_states_map_without_semantic_promotion(
    status: WorkUnitStatus,
    phase: str,
    retry: str,
):
    work = mutation_work()
    result = backend_result(
        work,
        succeeded=status not in {WorkUnitStatus.FAILED_DETERMINISTIC},
    )
    envelope = verification_outcome_envelope(
        work=work,
        result=result,
        outcome=outcome(work, status, f"native-{status.value.lower()}"),
    )
    assert envelope["source_state"] == status.value
    assert envelope["normalized_phase"] == phase
    assert envelope["retry_disposition"] == retry


def test_outcome_unknown_preserves_reconcile_before_retry_ceiling():
    work = mutation_work()
    envelope = verification_outcome_envelope(
        work=work,
        result=backend_result(work),
        outcome=outcome(
            work,
            WorkUnitStatus.OUTCOME_UNKNOWN,
            "final independent branch readback is unavailable",
        ),
    )
    assert {
        "kind": "claim_ceiling",
        "value": "EFFECT_MAY_HAVE_OCCURRED_RECONCILE_BEFORE_RETRY",
    } in envelope["receipts"]


def test_complete_requires_native_complete_status_not_backend_success_alone():
    work = mutation_work()
    result = backend_result(work)
    envelope = verification_outcome_envelope(
        work=work,
        result=result,
        outcome=outcome(
            work,
            WorkUnitStatus.VERIFYING,
            "worker/backend claim requires independent completion evidence",
        ),
    )
    assert envelope["normalized_phase"] == "POST_EFFECT_UNVERIFIED"
    assert envelope["normalized_phase"] != "POST_EFFECT_VERIFIED"


def test_superseded_is_not_laundered_into_effect_outcome():
    work = mutation_work()
    with pytest.raises(ValueError, match="source-native currentness state"):
        verification_outcome_envelope(
            work=work,
            result=backend_result(work),
            outcome=outcome(
                work,
                WorkUnitStatus.SUPERSEDED,
                "mutated branch moved during independent verification",
            ),
        )


def test_read_only_operation_is_not_effect_attempt():
    work = mutation_work("READ_REF")
    with pytest.raises(ValueError, match="consequential GitHub mutations"):
        pre_effect_envelope(work)


def test_exporter_does_not_mutate_native_work():
    work = mutation_work()
    before = copy.deepcopy(work)
    pre_effect_envelope(work)
    assert work == before
