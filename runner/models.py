from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Mapping


class WorkerLifecycle(str, Enum):
    REGISTERED = "REGISTERED"
    DISCOVERED = "DISCOVERED"
    PROFILED = "PROFILED"
    CONNECTED = "CONNECTED"
    EXECUTABLE = "EXECUTABLE"
    UNAVAILABLE = "UNAVAILABLE"


class RouteState(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    CONNECTED = "CONNECTED"
    VERIFIED = "VERIFIED"
    UNAVAILABLE = "UNAVAILABLE"


class WorkerType(str, Enum):
    CHATGPT_CUSTOM_GPT = "CHATGPT_CUSTOM_GPT"
    CHATGPT_PLUGIN = "CHATGPT_PLUGIN"
    OPENAI_AGENT = "OPENAI_AGENT"
    GITHUB_ACTION = "GITHUB_ACTION"
    EXTERNAL_API = "EXTERNAL_API"
    HUMAN = "HUMAN"


class InvocationRoute(str, Enum):
    CHATGPT_INVOCATION = "CHATGPT_INVOCATION"
    RUNNER_ACTION_PULL = "RUNNER_ACTION_PULL"
    DIRECT_EXTERNAL_DISPATCH = "DIRECT_EXTERNAL_DISPATCH"
    PLUGIN_TOOL_CALL = "PLUGIN_TOOL_CALL"
    OPENAI_AGENT_API = "OPENAI_AGENT_API"
    GITHUB_ACTION = "GITHUB_ACTION"
    HUMAN_MANUAL = "HUMAN_MANUAL"


_GPT_ID_RE = re.compile(r"^g-[A-Za-z0-9]+$")


@dataclass(frozen=True)
class WorkerDefinition:
    id: str
    name: str
    worker_type: WorkerType
    lifecycle: WorkerLifecycle
    locators: Mapping[str, str]
    roles: tuple[str, ...]
    routes: Mapping[InvocationRoute, RouteState]

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> "WorkerDefinition":
        worker_type = WorkerType(str(data["worker_type"]))
        lifecycle = WorkerLifecycle(str(data["lifecycle"]))
        raw_locators = data.get("locators", {})
        raw_routes = data.get("routes", {})
        if not isinstance(raw_locators, Mapping):
            raise ValueError("locators must be a mapping")
        if not isinstance(raw_routes, Mapping):
            raise ValueError("routes must be a mapping")

        locators = {str(k): str(v) for k, v in raw_locators.items()}
        if worker_type is WorkerType.CHATGPT_CUSTOM_GPT:
            gpt_id = locators.get("gpt_id")
            if gpt_id is None or _GPT_ID_RE.fullmatch(gpt_id) is None:
                raise ValueError("GPT id must match ^g-[A-Za-z0-9]+$")

        routes = {
            InvocationRoute(str(route)): RouteState(str(state))
            for route, state in raw_routes.items()
        }
        route_states = set(routes.values())
        if lifecycle is WorkerLifecycle.CONNECTED and not (
            RouteState.CONNECTED in route_states or RouteState.VERIFIED in route_states
        ):
            raise ValueError("CONNECTED worker requires a connected or verified route")
        if lifecycle is WorkerLifecycle.EXECUTABLE and RouteState.VERIFIED not in route_states:
            raise ValueError("EXECUTABLE worker requires at least one VERIFIED route")

        raw_roles = data.get("roles", [])
        if not isinstance(raw_roles, list):
            raise ValueError("roles must be a list")

        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            worker_type=worker_type,
            lifecycle=lifecycle,
            locators=locators,
            roles=tuple(str(role) for role in raw_roles),
            routes=routes,
        )


class ProjectAssignmentScope(str, Enum):
    NONE = "NONE"
    BT2_ASSIGNMENT = "BT2_ASSIGNMENT"
    EXTERNAL_BOUNDED = "EXTERNAL_BOUNDED"


class ProjectReviewScope(str, Enum):
    NONE = "NONE"
    STANDING = "STANDING"


@dataclass(frozen=True)
class ProjectDefinition:
    id: str
    name: str
    visibility: str
    repositories: tuple[str, ...]
    capabilities: tuple[str, ...]
    assignment_scope: ProjectAssignmentScope
    review_scope: ProjectReviewScope
    family_id: str
    scope_note: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> "ProjectDefinition":
        raw_repositories = data.get("repositories", [])
        raw_capabilities = data.get("capabilities", [])
        if not isinstance(raw_repositories, list):
            raise ValueError("repositories must be a list")
        if not isinstance(raw_capabilities, list):
            raise ValueError("capabilities must be a list")
        visibility = str(data["visibility"])
        if visibility not in {"public", "private"}:
            raise ValueError("visibility must be public or private")
        project_id = str(data["id"])
        family_id = str(data.get("family_id", project_id)).strip()
        if not family_id:
            raise ValueError("family_id must not be empty")
        scope_note = data.get("scope_note")
        return cls(
            id=project_id,
            name=str(data["name"]),
            visibility=visibility,
            repositories=tuple(str(repo) for repo in raw_repositories),
            capabilities=tuple(str(capability) for capability in raw_capabilities),
            assignment_scope=ProjectAssignmentScope(
                str(data.get("assignment_scope", ProjectAssignmentScope.NONE.value))
            ),
            review_scope=ProjectReviewScope(
                str(data.get("review_scope", ProjectReviewScope.NONE.value))
            ),
            family_id=family_id,
            scope_note=str(scope_note) if scope_note is not None else None,
        )


class EvidenceClass(str, Enum):
    AUTHORITATIVE = "AUTHORITATIVE"
    DECLARED = "DECLARED"
    DERIVED = "DERIVED"
    CACHED = "CACHED"


@dataclass(frozen=True)
class ExactSubject:
    repository: str
    ref: str
    commit: str | None = None
    path: str | None = None
    digest: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> "ExactSubject":
        repository = str(data.get("repository", "")).strip()
        ref = str(data.get("ref", "")).strip()
        if not repository or not ref:
            raise ValueError("subject requires repository and ref")
        return cls(
            repository=repository,
            ref=ref,
            commit=str(data["commit"]) if data.get("commit") is not None else None,
            path=str(data["path"]) if data.get("path") is not None else None,
            digest=str(data["digest"]) if data.get("digest") is not None else None,
        )

    def identity(self) -> tuple[str, str, str | None, str | None, str | None]:
        return (self.repository, self.ref, self.commit, self.path, self.digest)


@dataclass(frozen=True)
class Observation:
    target: str
    evidence_class: EvidenceClass
    subject: ExactSubject
    observed_value: str
    observed_at: str
    observer: str

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> "Observation":
        raw_subject = data.get("subject")
        if not isinstance(raw_subject, Mapping):
            raise ValueError("observation subject must be a mapping")
        return cls(
            target=str(data["target"]),
            evidence_class=EvidenceClass(str(data["evidence_class"])),
            subject=ExactSubject.from_mapping(raw_subject),
            observed_value=str(data["observed_value"]),
            observed_at=str(data["observed_at"]),
            observer=str(data["observer"]),
        )


class DependencyReaction(str, Enum):
    NO_ACTION = "NO_ACTION"
    INSPECT = "INSPECT"
    RETEST = "RETEST"
    REREVIEW = "REREVIEW"
    REQUALIFY = "REQUALIFY"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class DependencySelector:
    repository: str
    ref: str | None = None
    path_prefix: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> "DependencySelector":
        repository = str(data.get("repository", "")).strip()
        if not repository:
            raise ValueError("dependency selector requires repository")
        return cls(
            repository=repository,
            ref=str(data["ref"]) if data.get("ref") is not None else None,
            path_prefix=str(data["path_prefix"]) if data.get("path_prefix") is not None else None,
        )


@dataclass(frozen=True)
class DependencyEdge:
    id: str
    provider: str
    consumer: str
    kind: str
    selector: DependencySelector
    reaction: DependencyReaction
    evidence: str

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> "DependencyEdge":
        raw_selector = data.get("selector")
        if not isinstance(raw_selector, Mapping):
            raise ValueError("dependency selector must be a mapping")
        return cls(
            id=str(data["id"]),
            provider=str(data["provider"]),
            consumer=str(data["consumer"]),
            kind=str(data["kind"]),
            selector=DependencySelector.from_mapping(raw_selector),
            reaction=DependencyReaction(str(data["reaction"])),
            evidence=str(data["evidence"]),
        )


class FrontierStatus(str, Enum):
    READY = "READY"
    WAITING_DEPENDENCY = "WAITING_DEPENDENCY"
    WAITING_AUTHORITY = "WAITING_AUTHORITY"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    COMPLETE = "COMPLETE"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_DETERMINISTIC = "FAILED_DETERMINISTIC"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"
    SUPERSEDED = "SUPERSEDED"


class CostClass(str, Enum):
    TRIVIAL = "TRIVIAL"
    SMALL = "SMALL"
    MEDIUM = "MEDIUM"
    LARGE = "LARGE"


@dataclass(frozen=True)
class Frontier:
    id: str
    project: str
    subject: ExactSubject
    work_type: str
    reason: str
    dependencies: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    collision_keys: tuple[str, ...]
    cost_class: CostClass
    priority_inputs: Mapping[str, int]
    status: FrontierStatus

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> "Frontier":
        raw_subject = data.get("subject")
        if not isinstance(raw_subject, Mapping):
            raise ValueError("frontier subject must be a mapping")
        raw_dependencies = data["dependencies"]
        raw_capabilities = data["required_capabilities"]
        raw_collision_keys = data["collision_keys"]
        raw_priority_inputs = data["priority_inputs"]
        if not isinstance(raw_dependencies, list):
            raise ValueError("dependencies must be a list")
        if not isinstance(raw_capabilities, list):
            raise ValueError("required_capabilities must be a list")
        if not isinstance(raw_collision_keys, list):
            raise ValueError("collision_keys must be a list")
        if not isinstance(raw_priority_inputs, Mapping):
            raise ValueError("priority_inputs must be a mapping")
        return cls(
            id=str(data["id"]),
            project=str(data["project"]),
            subject=ExactSubject.from_mapping(raw_subject),
            work_type=str(data["work_type"]),
            reason=str(data["reason"]),
            dependencies=tuple(str(item) for item in raw_dependencies),
            required_capabilities=tuple(str(item) for item in raw_capabilities),
            collision_keys=tuple(str(item) for item in raw_collision_keys),
            cost_class=CostClass(str(data["cost_class"])),
            priority_inputs={str(k): int(v) for k, v in raw_priority_inputs.items()},
            status=FrontierStatus(str(data["status"])),
        )
