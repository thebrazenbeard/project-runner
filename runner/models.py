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


@dataclass(frozen=True)
class ProjectDefinition:
    id: str
    name: str
    visibility: str
    repositories: tuple[str, ...]
    capabilities: tuple[str, ...]

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
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            visibility=visibility,
            repositories=tuple(str(repo) for repo in raw_repositories),
            capabilities=tuple(str(capability) for capability in raw_capabilities),
        )
