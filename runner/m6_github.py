from __future__ import annotations

from dataclasses import replace

from .backends import BackendResult
from .github_backend import GitHubBackend
from .models import ExactSubject, Frontier
from .work_units import WorkUnit, WorkUnitStatus, work_unit_fingerprint


def _require_ref_subject(subject: ExactSubject) -> None:
    if not subject.repository or not subject.ref or not subject.commit:
        raise ValueError(
            "M6 GitHub inspection requires repository, ref, and exact commit"
        )


def frontier_to_github_inspection_work(
    frontier: Frontier,
    target_subject: ExactSubject,
    depth: int = 0,
) -> WorkUnit:
    if frontier.work_type != "INSPECT":
        raise ValueError("M6 GitHub inspection factory only accepts INSPECT frontiers")
    _require_ref_subject(frontier.subject)
    _require_ref_subject(target_subject)

    inputs = (frontier.subject,)
    if target_subject.identity() != frontier.subject.identity():
        inputs = inputs + (target_subject,)

    return WorkUnit(
        id=f"m6-read-{frontier.id}",
        root_frontier_id=frontier.id,
        parent_work_id=None,
        inputs=inputs,
        operation="INSPECT",
        required_capabilities=frontier.required_capabilities,
        collision_keys=frontier.collision_keys,
        recursion_depth=depth,
        budget_allocation={
            "children": 0,
            "active": 1,
            "retries": 0,
            "backend_jobs": 1,
        },
        expected_outputs=("read-ref-ok",),
        completion_criteria=(
            "exact-subject-current",
            "completion-evidence-verified",
        ),
        status=WorkUnitStatus.PENDING,
        payload={"m6": {"kind": "github-read-inspection"}},
    )


def _github_read_work(subject: ExactSubject, *, expected: bool) -> WorkUnit:
    _require_ref_subject(subject)
    request: dict[str, str] = {
        "operation": "READ_REF",
        "repository": subject.repository,
        "ref": subject.ref,
    }
    if expected:
        request["expected_head"] = subject.commit

    return WorkUnit(
        id="m6-internal-github-read",
        root_frontier_id="m6-internal-github-read",
        parent_work_id=None,
        inputs=(subject,),
        operation="GITHUB",
        required_capabilities=("github.read_ref",),
        collision_keys=(),
        recursion_depth=0,
        budget_allocation={
            "children": 0,
            "active": 0,
            "retries": 0,
            "backend_jobs": 0,
        },
        expected_outputs=("github-ref-head",),
        completion_criteria=("github-readback-verified",),
        status=WorkUnitStatus.RUNNING,
        payload={"github": request},
    )


def _redacted_failure(work: WorkUnit, classification: str) -> BackendResult:
    return BackendResult(
        work_fingerprint=work_unit_fingerprint(work),
        succeeded=False,
        outputs=(),
        evidence=(
            "m6:github-read-inspection",
            f"github:{classification.lower()}",
        ),
        classification=classification,
    )


class GitHubReadInspectionBackend:
    """Read-only M6 adapter with explicit route + target-authority enforcement.

    The wrapped GitHub backend performs the actual authority checks and ref reads.
    This adapter intentionally does not propagate repository, ref, commit, or
    backend failure-detail strings into its result evidence.
    """

    def __init__(self, backend: GitHubBackend) -> None:
        self.backend = backend

    def execute(self, work: WorkUnit) -> BackendResult:
        if work.operation != "INSPECT":
            return _redacted_failure(work, "UNSUPPORTED_OPERATION")
        if not work.inputs:
            return _redacted_failure(work, "INVALID_REQUEST")

        for subject in work.inputs:
            try:
                inner = _github_read_work(subject, expected=True)
            except ValueError:
                return _redacted_failure(work, "INVALID_REQUEST")
            result = self.backend.execute(inner)
            if not result.succeeded:
                return _redacted_failure(work, result.classification)

        return BackendResult(
            work_fingerprint=work_unit_fingerprint(work),
            succeeded=True,
            outputs=tuple("READ_REF_OK" for _ in work.inputs),
            evidence=(
                "m6:github-read-inspection",
                "github:readback-verified",
                f"subjects={len(work.inputs)}",
            ),
            classification="SUCCEEDED",
        )


class GitHubCurrentSubjectReader:
    """Independent exact-head reader using the authority-gated GitHub backend."""

    def __init__(self, backend: GitHubBackend) -> None:
        self.backend = backend

    def read(self, subject: ExactSubject) -> ExactSubject | None:
        try:
            inner = _github_read_work(subject, expected=False)
        except ValueError:
            return None
        result = self.backend.execute(inner)
        if not result.succeeded or len(result.outputs) != 1:
            return None
        observed = result.outputs[0]
        if not observed:
            return None
        return replace(subject, commit=observed)
