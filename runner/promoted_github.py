from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping

from .backends import BackendResult
from .execution_promotion import PromotedExecution, SOURCE_WRITE
from .github_backend import (
    GitHubBackend,
    GitHubOperation,
    GitHubRequest,
    GitHubTransport,
    TargetAuthorityGrant,
)
from .work_units import WorkUnit, WorkUnitStatus


_SOURCE_WRITE_SCHEMA = "PROJECT_RUNNER_GITHUB_SOURCE_WRITE_V1"


@dataclass(frozen=True)
class GitHubSourceWriteRequest:
    repository: str
    ref: str
    expected_head: str
    path: str
    content: str
    message: str
    expected_blob_sha: str | None

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, object],
    ) -> "GitHubSourceWriteRequest":
        if value.get("schema") != _SOURCE_WRITE_SCHEMA:
            raise ValueError("unexpected promoted GitHub source-write schema")
        if value.get("operation") != GitHubOperation.PUT_FILE.value:
            raise ValueError("promoted GitHub source write must use PUT_FILE")
        request = GitHubRequest.from_mapping(value)
        if request.operation is not GitHubOperation.PUT_FILE:
            raise ValueError("promoted GitHub source write must use PUT_FILE")
        if request.expected_head is None:
            raise ValueError("promoted GitHub source write requires exact head")
        if request.path is None or not request.path.strip():
            raise ValueError("promoted GitHub source write requires a path")
        if request.content is None:
            raise ValueError("promoted GitHub source write requires content")
        if request.message is None or not request.message.strip():
            raise ValueError("promoted GitHub source write requires a commit message")
        return cls(
            repository=request.repository,
            ref=request.ref,
            expected_head=request.expected_head,
            path=request.path.lstrip("/"),
            content=request.content,
            message=request.message,
            expected_blob_sha=request.expected_blob_sha,
        )


def source_write_request_sha256(value: Mapping[str, object]) -> str:
    canonical = json.dumps(
        dict(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class PromotedGitHubSourceWriteBackend:
    """Execute one promotion-bound PUT_FILE with exact CAS and readback.

    The promotion gate already proves the active fence and authority windows.
    This adapter independently binds the durable request to the promotion receipt
    and delegates the mutation to the existing exact-head/blob GitHub backend.
    """

    def __init__(self, *, transport: GitHubTransport) -> None:
        self.transport = transport

    def execute_promoted(self, execution: PromotedExecution) -> BackendResult:
        fingerprint = execution.promotion.work_fingerprint

        if execution.effect_class != SOURCE_WRITE:
            return self._failure(
                fingerprint,
                "EFFECT_CLASS_DENIED",
                "promoted GitHub adapter requires SOURCE_WRITE",
            )
        if execution.execution_request is None:
            return self._failure(
                fingerprint,
                "REQUEST_MISSING",
                "promoted source write has no durable execution request",
            )

        try:
            request = GitHubSourceWriteRequest.from_mapping(
                execution.execution_request
            )
        except (KeyError, TypeError, ValueError):
            return self._failure(
                fingerprint,
                "INVALID_REQUEST",
                "promoted source-write request is invalid",
            )

        request_sha256 = source_write_request_sha256(
            execution.execution_request
        )
        if execution.promotion.execution_request_sha256 != request_sha256:
            return self._failure(
                fingerprint,
                "REQUEST_BINDING_MISMATCH",
                "promoted request does not match durable promotion",
            )

        promotion = execution.promotion
        if (
            request.repository != promotion.repository
            or request.ref != promotion.ref
            or request.expected_head != promotion.exact_head
        ):
            return self._failure(
                fingerprint,
                "PROMOTION_BINDING_MISMATCH",
                "source-write request target diverges from promotion",
            )

        github_work = WorkUnit(
            id=f"promoted-github-source-write:{execution.work.id}",
            root_frontier_id=execution.work.root_frontier_id,
            parent_work_id=execution.work.parent_work_id,
            inputs=execution.work.inputs,
            operation="GITHUB",
            required_capabilities=("github.put_file",),
            collision_keys=execution.work.collision_keys,
            recursion_depth=execution.work.recursion_depth,
            budget_allocation=execution.work.budget_allocation,
            expected_outputs=("commit-sha", "blob-sha"),
            completion_criteria=(
                "exact-head/blob preconditions passed",
                "written content independently read back",
            ),
            status=WorkUnitStatus.RUNNING,
            payload={
                "github": {
                    "operation": GitHubOperation.PUT_FILE.value,
                    "repository": request.repository,
                    "ref": request.ref,
                    "expected_head": request.expected_head,
                    "path": request.path,
                    "content": request.content,
                    "message": request.message,
                    "expected_blob_sha": request.expected_blob_sha,
                }
            },
        )
        backend = GitHubBackend(
            transport=self.transport,
            route_capabilities=("github.put_file",),
            grants=(
                TargetAuthorityGrant(
                    repository=request.repository,
                    operations=(GitHubOperation.PUT_FILE,),
                    ref_prefixes=(request.ref,),
                    path_prefixes=(request.path,),
                ),
            ),
        )
        observed = backend.execute(github_work)
        if not observed.succeeded:
            return BackendResult(
                work_fingerprint=fingerprint,
                succeeded=False,
                outputs=(),
                evidence=observed.evidence,
                classification=observed.classification,
            )

        return BackendResult(
            work_fingerprint=fingerprint,
            succeeded=True,
            outputs=observed.outputs,
            evidence=(
                "github:promoted-source-write",
                "github:exact-cas",
                "github:readback-verified",
            ),
            classification="SUCCEEDED",
        )

    @staticmethod
    def _failure(
        fingerprint: str,
        classification: str,
        detail: str,
    ) -> BackendResult:
        return BackendResult(
            work_fingerprint=fingerprint,
            succeeded=False,
            outputs=(),
            evidence=(f"github:{classification.lower()}", detail),
            classification=classification,
        )
