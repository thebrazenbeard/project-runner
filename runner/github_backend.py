from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
from enum import Enum
import json
from typing import Iterable, Mapping, Protocol
from urllib import error, parse, request

from .backends import BackendResult
from .work_units import WorkUnit, work_unit_fingerprint


class GitHubOperation(str, Enum):
    READ_REF = "READ_REF"
    READ_FILE = "READ_FILE"
    CREATE_BRANCH = "CREATE_BRANCH"
    PUT_FILE = "PUT_FILE"


_ROUTE_CAPABILITY = {
    GitHubOperation.READ_REF: "github.read_ref",
    GitHubOperation.READ_FILE: "github.read_file",
    GitHubOperation.CREATE_BRANCH: "github.create_branch",
    GitHubOperation.PUT_FILE: "github.put_file",
}


@dataclass(frozen=True)
class GitHubFileState:
    sha: str
    content: str


@dataclass(frozen=True)
class GitHubRequest:
    operation: GitHubOperation
    repository: str
    ref: str
    expected_head: str | None = None
    source_ref: str | None = None
    path: str | None = None
    content: str | None = None
    message: str | None = None
    expected_blob_sha: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> "GitHubRequest":
        operation = GitHubOperation(str(data["operation"]))
        repository = str(data["repository"]).strip()
        ref = str(data["ref"]).strip()
        if not repository or "/" not in repository:
            raise ValueError("github request requires owner/repository")
        if not ref:
            raise ValueError("github request requires ref")
        return cls(
            operation=operation,
            repository=repository,
            ref=ref,
            expected_head=str(data["expected_head"]) if data.get("expected_head") is not None else None,
            source_ref=str(data["source_ref"]) if data.get("source_ref") is not None else None,
            path=str(data["path"]) if data.get("path") is not None else None,
            content=str(data["content"]) if data.get("content") is not None else None,
            message=str(data["message"]) if data.get("message") is not None else None,
            expected_blob_sha=str(data["expected_blob_sha"]) if data.get("expected_blob_sha") is not None else None,
        )


@dataclass(frozen=True)
class TargetAuthorityGrant:
    repository: str
    operations: tuple[GitHubOperation, ...]
    ref_prefixes: tuple[str, ...]
    path_prefixes: tuple[str, ...] = ()

    def allows(self, req: GitHubRequest) -> bool:
        if req.repository != self.repository or req.operation not in self.operations:
            return False
        if not any(_scope_match(req.ref, item) for item in self.ref_prefixes):
            return False
        if req.operation in {GitHubOperation.READ_FILE, GitHubOperation.PUT_FILE}:
            if req.path is None or not self.path_prefixes:
                return False
            if not any(_path_scope_match(req.path, item) for item in self.path_prefixes):
                return False
        return True


def _scope_match(value: str, scope: str) -> bool:
    return value.startswith(scope) if scope.endswith("/") else value == scope


def _path_scope_match(value: str, scope: str) -> bool:
    normalized = scope.lstrip("/")
    return value == normalized or value.startswith(normalized.rstrip("/") + "/")


class GitHubTransport(Protocol):
    def read_ref(self, repository: str, ref: str) -> str: ...
    def read_file(self, repository: str, path: str, ref: str) -> GitHubFileState | None: ...
    def create_branch(self, repository: str, branch: str, sha: str) -> None: ...
    def put_file(
        self,
        repository: str,
        path: str,
        branch: str,
        content: str,
        message: str,
        expected_blob_sha: str | None = None,
    ) -> str: ...


class GitHubRestTransport:
    """Small GitHub REST transport using only the Python standard library."""

    def __init__(self, *, token: str | None = None, api_base: str = "https://api.github.com") -> None:
        self.token = token
        self.api_base = api_base.rstrip("/")

    def _request(self, method: str, url: str, body: Mapping[str, object] | None = None):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "project-runner-m5",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        req = request.Request(url, data=data, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=30) as response:
                raw = response.read()
        except error.HTTPError as exc:
            if exc.code == 404:
                return None
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"github http {exc.code}: {detail}") from exc
        return json.loads(raw.decode("utf-8")) if raw else {}

    def read_ref(self, repository: str, ref: str) -> str:
        owner, repo = repository.split("/", 1)
        encoded_ref = parse.quote(f"heads/{ref}", safe="/")
        payload = self._request(
            "GET",
            f"{self.api_base}/repos/{parse.quote(owner)}/{parse.quote(repo)}/git/ref/{encoded_ref}",
        )
        if payload is None:
            raise KeyError(f"missing ref {repository}@{ref}")
        return str(payload["object"]["sha"])

    def read_file(self, repository: str, path: str, ref: str) -> GitHubFileState | None:
        owner, repo = repository.split("/", 1)
        encoded_path = parse.quote(path.lstrip("/"), safe="/")
        encoded_ref = parse.quote(ref, safe="")
        payload = self._request(
            "GET",
            f"{self.api_base}/repos/{parse.quote(owner)}/{parse.quote(repo)}/contents/{encoded_path}?ref={encoded_ref}",
        )
        if payload is None:
            return None
        if payload.get("type") != "file":
            raise RuntimeError("github contents target is not a file")
        encoding = payload.get("encoding")
        raw_content = str(payload.get("content", "")).replace("\n", "")
        if encoding != "base64":
            raise RuntimeError("unsupported github file encoding")
        content = base64.b64decode(raw_content).decode("utf-8")
        return GitHubFileState(sha=str(payload["sha"]), content=content)

    def create_branch(self, repository: str, branch: str, sha: str) -> None:
        owner, repo = repository.split("/", 1)
        self._request(
            "POST",
            f"{self.api_base}/repos/{parse.quote(owner)}/{parse.quote(repo)}/git/refs",
            {"ref": f"refs/heads/{branch}", "sha": sha},
        )

    def put_file(
        self,
        repository: str,
        path: str,
        branch: str,
        content: str,
        message: str,
        expected_blob_sha: str | None = None,
    ) -> str:
        owner, repo = repository.split("/", 1)
        encoded_path = parse.quote(path.lstrip("/"), safe="/")
        payload: dict[str, object] = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if expected_blob_sha is not None:
            payload["sha"] = expected_blob_sha
        response = self._request(
            "PUT",
            f"{self.api_base}/repos/{parse.quote(owner)}/{parse.quote(repo)}/contents/{encoded_path}",
            payload,
        )
        return str(response["commit"]["sha"])


class GitHubBackend:
    """Authority-separated GitHub execution backend.

    Technical route capability and target authorization are independent gates.
    """

    def __init__(
        self,
        *,
        transport: GitHubTransport,
        route_capabilities: Iterable[str],
        grants: Iterable[TargetAuthorityGrant],
    ) -> None:
        self.transport = transport
        self.route_capabilities = frozenset(route_capabilities)
        self.grants = tuple(grants)

    def execute(self, work: WorkUnit) -> BackendResult:
        fingerprint = work_unit_fingerprint(work)
        try:
            raw = work.payload.get("github")
            if not isinstance(raw, Mapping):
                raise ValueError("work payload missing github request")
            req = GitHubRequest.from_mapping(raw)
        except (KeyError, TypeError, ValueError) as exc:
            return _failure(fingerprint, "INVALID_REQUEST", str(exc))

        route_capability = _ROUTE_CAPABILITY[req.operation]
        if route_capability not in self.route_capabilities:
            return _failure(fingerprint, "ROUTE_UNAVAILABLE", route_capability)

        if not any(grant.allows(req) for grant in self.grants):
            return _failure(fingerprint, "AUTHORITY_DENIED", "target authority denied")

        try:
            if req.operation is GitHubOperation.READ_REF:
                return self._read_ref(fingerprint, req)
            if req.operation is GitHubOperation.READ_FILE:
                return self._read_file(fingerprint, req)
            if req.operation is GitHubOperation.CREATE_BRANCH:
                return self._create_branch(fingerprint, req)
            if req.operation is GitHubOperation.PUT_FILE:
                return self._put_file(fingerprint, req)
        except (KeyError, RuntimeError, ValueError):
            return _failure(fingerprint, "TRANSPORT_FAILED", "github transport failed")

        return _failure(fingerprint, "INVALID_REQUEST", "unsupported operation")

    def _read_ref(self, fingerprint: str, req: GitHubRequest) -> BackendResult:
        observed = self.transport.read_ref(req.repository, req.ref)
        if req.expected_head is not None and observed != req.expected_head:
            return _failure(fingerprint, "PRECONDITION_FAILED", "exact ref precondition failed")
        return BackendResult(
            work_fingerprint=fingerprint,
            succeeded=True,
            outputs=(observed,),
            evidence=("github:read-ref", "github:readback-verified"),
            classification="SUCCEEDED",
        )

    def _read_file(self, fingerprint: str, req: GitHubRequest) -> BackendResult:
        if req.path is None:
            return _failure(fingerprint, "INVALID_REQUEST", "read file requires path")
        read_ref = req.ref
        if req.expected_head is not None:
            observed_head = self.transport.read_ref(req.repository, req.ref)
            if observed_head != req.expected_head:
                return _failure(fingerprint, "PRECONDITION_FAILED", "exact ref precondition failed")
            read_ref = req.expected_head
        observed = self.transport.read_file(req.repository, req.path, read_ref)
        if observed is None:
            return _failure(fingerprint, "NOT_FOUND", "file not found")
        if req.expected_blob_sha is not None and observed.sha != req.expected_blob_sha:
            return _failure(fingerprint, "PRECONDITION_FAILED", "blob mismatch")
        content_digest = hashlib.sha256(observed.content.encode("utf-8")).hexdigest()
        return BackendResult(
            work_fingerprint=fingerprint,
            succeeded=True,
            outputs=(observed.sha, content_digest),
            evidence=("github:file-read", "github:readback-verified"),
            classification="SUCCEEDED",
        )

    def _create_branch(self, fingerprint: str, req: GitHubRequest) -> BackendResult:
        if req.source_ref is None or req.expected_head is None:
            return _failure(fingerprint, "INVALID_REQUEST", "create branch requires source_ref and expected_head")
        observed_source = self.transport.read_ref(req.repository, req.source_ref)
        if observed_source != req.expected_head:
            return _failure(fingerprint, "PRECONDITION_FAILED", "source ref precondition failed")
        self.transport.create_branch(req.repository, req.ref, req.expected_head)
        readback = self.transport.read_ref(req.repository, req.ref)
        if readback != req.expected_head:
            return _failure(fingerprint, "READBACK_FAILED", "branch readback failed")
        return BackendResult(
            work_fingerprint=fingerprint,
            succeeded=True,
            outputs=(readback,),
            evidence=(
                "github:create-branch",
                "github:readback-verified",
            ),
            classification="SUCCEEDED",
        )

    def _put_file(self, fingerprint: str, req: GitHubRequest) -> BackendResult:
        if req.path is None or req.content is None or req.message is None or req.expected_head is None:
            return _failure(fingerprint, "INVALID_REQUEST", "put file requires path/content/message/expected_head")
        observed_head = self.transport.read_ref(req.repository, req.ref)
        if observed_head != req.expected_head:
            return _failure(fingerprint, "PRECONDITION_FAILED", "target ref precondition failed")

        existing = self.transport.read_file(req.repository, req.path, req.ref)
        if existing is not None and req.expected_blob_sha is None:
            return _failure(fingerprint, "PRECONDITION_FAILED", "existing file requires expected_blob_sha")
        if req.expected_blob_sha is not None:
            if existing is None or existing.sha != req.expected_blob_sha:
                return _failure(fingerprint, "PRECONDITION_FAILED", "target blob precondition failed")

        commit_sha = self.transport.put_file(
            req.repository,
            req.path,
            req.ref,
            req.content,
            req.message,
            expected_blob_sha=req.expected_blob_sha,
        )
        readback_head = self.transport.read_ref(req.repository, req.ref)
        readback_file = self.transport.read_file(req.repository, req.path, req.ref)
        if readback_head != commit_sha or readback_file is None or readback_file.content != req.content:
            return _failure(fingerprint, "READBACK_FAILED", "file mutation readback failed")
        return BackendResult(
            work_fingerprint=fingerprint,
            succeeded=True,
            outputs=(commit_sha, readback_file.sha),
            evidence=(
                "github:put-file",
                "github:readback-verified",
            ),
            classification="SUCCEEDED",
        )


def _failure(fingerprint: str, classification: str, detail: str) -> BackendResult:
    return BackendResult(
        work_fingerprint=fingerprint,
        succeeded=False,
        outputs=(),
        evidence=(f"github:{classification.lower()}", detail),
        classification=classification,
    )
