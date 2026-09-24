from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
from typing import Iterable

from .portfolio_advancement import AdvancementItem, AdvancementWave


_REPOSITORY = re.compile(r"^[^/\s]+/[^/\s]+$")
_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}
_INERT_ACTIONS = {"PRESERVE_ONLY", "REFRESH_IF_REACTIVATED"}


@dataclass(frozen=True)
class WaveExecutionBudget:
    max_parallel: int
    max_per_identity: int

    def validate(self) -> None:
        if type(self.max_parallel) is not int or self.max_parallel < 1:
            raise ValueError("max_parallel must be a positive integer")
        if type(self.max_per_identity) is not int or self.max_per_identity < 1:
            raise ValueError("max_per_identity must be a positive integer")
        if self.max_per_identity > self.max_parallel:
            raise ValueError("max_per_identity cannot exceed max_parallel")


@dataclass(frozen=True)
class WaveAdmission:
    subject_kind: str
    subject_id: str
    lead_identity: str
    priority: str
    collision_keys: tuple[str, ...]


@dataclass(frozen=True)
class WaveDeferral:
    subject_kind: str
    subject_id: str
    lead_identity: str
    priority: str
    reason: str
    collision_keys: tuple[str, ...]


@dataclass(frozen=True)
class WaveAdmissionPlan:
    selected: tuple[WaveAdmission, ...]
    deferred: tuple[WaveDeferral, ...]
    budget: WaveExecutionBudget
    occupied_collision_keys: tuple[str, ...]

    def summary(self) -> dict[str, object]:
        return {
            "selected": len(self.selected),
            "deferred": len(self.deferred),
            "max_parallel": self.budget.max_parallel,
            "max_per_identity": self.budget.max_per_identity,
            "selected_by_identity": dict(sorted(Counter(
                item.lead_identity for item in self.selected
            ).items())),
            "selected_by_priority": dict(sorted(Counter(
                item.priority for item in self.selected
            ).items())),
            "deferred_by_reason": dict(sorted(Counter(
                item.reason for item in self.deferred
            ).items())),
            "occupied_collision_keys": list(self.occupied_collision_keys),
        }


def collision_keys(item: AdvancementItem) -> tuple[str, ...]:
    keys: set[str] = set()
    for surface in item.repositories:
        value = surface.strip()
        if not value:
            continue
        if _REPOSITORY.fullmatch(value):
            keys.add(f"repository:{value.lower()}")
        else:
            keys.add(f"surface:{value.lower()}")
    if not keys:
        keys.add(f"{item.subject_kind}:{item.subject_id}")
    return tuple(sorted(keys))


def _admission_sort_key(item: AdvancementItem) -> tuple[object, ...]:
    return (
        _PRIORITY_ORDER.get(item.priority, 99),
        item.lead_identity,
        item.subject_kind,
        item.subject_id,
    )


def plan_wave_admission(
    wave: AdvancementWave,
    *,
    budget: WaveExecutionBudget,
    occupied_collision_keys: Iterable[str] = (),
) -> WaveAdmissionPlan:
    """Select a deterministic, collision-free source-work slice.

    Admission is scheduling evidence only. It grants no repository/provider
    authority and does not perform execution, merge, deployment, installation,
    credential mutation, or any other protected effect.
    """
    budget.validate()
    occupied = {str(value).strip().lower() for value in occupied_collision_keys}
    if "" in occupied:
        raise ValueError("occupied collision keys must be non-empty strings")

    selected: list[WaveAdmission] = []
    deferred: list[WaveDeferral] = []
    reserved = set(occupied)
    identity_load: Counter[str] = Counter()

    for item in sorted(wave.items, key=_admission_sort_key):
        keys = collision_keys(item)

        if item.execution_state != "QUEUED":
            deferred.append(WaveDeferral(
                subject_kind=item.subject_kind,
                subject_id=item.subject_id,
                lead_identity=item.lead_identity,
                priority=item.priority,
                reason="NOT_QUEUED",
                collision_keys=keys,
            ))
            continue

        if item.action in _INERT_ACTIONS or item.effect_ceiling == "NO_EFFECT":
            deferred.append(WaveDeferral(
                subject_kind=item.subject_kind,
                subject_id=item.subject_id,
                lead_identity=item.lead_identity,
                priority=item.priority,
                reason="INERT_OR_NO_EFFECT",
                collision_keys=keys,
            ))
            continue

        if item.effect_ceiling != "SOURCE_ONLY":
            raise ValueError(
                f"wave item exceeds source-only admission ceiling: {item.subject_id}"
            )

        if len(selected) >= budget.max_parallel:
            deferred.append(WaveDeferral(
                subject_kind=item.subject_kind,
                subject_id=item.subject_id,
                lead_identity=item.lead_identity,
                priority=item.priority,
                reason="GLOBAL_BUDGET",
                collision_keys=keys,
            ))
            continue

        if identity_load[item.lead_identity] >= budget.max_per_identity:
            deferred.append(WaveDeferral(
                subject_kind=item.subject_kind,
                subject_id=item.subject_id,
                lead_identity=item.lead_identity,
                priority=item.priority,
                reason="IDENTITY_BUDGET",
                collision_keys=keys,
            ))
            continue

        if reserved.intersection(keys):
            deferred.append(WaveDeferral(
                subject_kind=item.subject_kind,
                subject_id=item.subject_id,
                lead_identity=item.lead_identity,
                priority=item.priority,
                reason="COLLISION",
                collision_keys=keys,
            ))
            continue

        selected.append(WaveAdmission(
            subject_kind=item.subject_kind,
            subject_id=item.subject_id,
            lead_identity=item.lead_identity,
            priority=item.priority,
            collision_keys=keys,
        ))
        identity_load[item.lead_identity] += 1
        reserved.update(keys)

    return WaveAdmissionPlan(
        selected=tuple(selected),
        deferred=tuple(deferred),
        budget=budget,
        occupied_collision_keys=tuple(sorted(occupied)),
    )
