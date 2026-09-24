from pathlib import Path

import pytest

from runner.portfolio_advancement import (
    AdvancementItem,
    AdvancementWave,
    load_advancement_wave,
)
from runner.portfolio_wave_scheduler import (
    WaveExecutionBudget,
    collision_keys,
    plan_wave_admission,
)


ROOT = Path(__file__).resolve().parents[2]


def item(
    subject_id,
    *,
    repository="owner/repo",
    priority="P1",
    lead="ONE",
    action="EXECUTE_FRONTIER",
    state="QUEUED",
    ceiling="SOURCE_ONLY",
    kind="repository",
    family="test-family",
):
    kwargs = {
        "subject_kind": kind,
        "subject_id": subject_id,
        "repositories": (repository,),
        "priority": priority,
        "family_id": family,
        "activity_state": "ACTIVE",
        "lead_identity": lead,
        "reviewer_identities": ("REZON",),
        "action": action,
        "execution_state": state,
        "effect_ceiling": ceiling,
        "review_gate": "EXACT_HEAD_REVIEW",
        "frontier": "test frontier",
        "source_status": "test status",
    }
    return AdvancementItem(**kwargs)


def wave(*items):
    return AdvancementWave(
        wave_id="PROJECT_RUNNER_PORTFOLIO_ADVANCEMENT_WAVE_V1",
        generated_at="2026-09-24T00:00:00Z",
        corpus_binding={},
        identities={
            "ONE": "orchestrator",
            "REZON": "assurance",
            "VOSS": "forensic",
        },
        policy={},
        items=tuple(items),
    )


def test_budget_must_be_explicit_and_valid():
    with pytest.raises(ValueError, match="positive integer"):
        plan_wave_admission(
            wave(item("a")),
            budget=WaveExecutionBudget(max_parallel=0, max_per_identity=1, max_per_family=1),
        )
    with pytest.raises(ValueError, match="cannot exceed"):
        plan_wave_admission(
            wave(item("a")),
            budget=WaveExecutionBudget(max_parallel=1, max_per_identity=2, max_per_family=1),
        )


def test_priority_and_identity_budget_bound_selection():
    planned = plan_wave_admission(
        wave(
            item("p1-a", priority="P1", lead="ONE", repository="owner/a"),
            item("p0-b", priority="P0", lead="ONE", repository="owner/b"),
            item("p0-c", priority="P0", lead="VOSS", repository="owner/c"),
            item("p2-d", priority="P2", lead="REZON", repository="owner/d"),
        ),
        budget=WaveExecutionBudget(max_parallel=3, max_per_identity=1, max_per_family=3),
    )
    assert [selected.subject_id for selected in planned.selected] == [
        "p0-b",
        "p0-c",
        "p2-d",
    ]
    assert any(
        deferred.subject_id == "p1-a"
        and deferred.reason == "IDENTITY_BUDGET"
        for deferred in planned.deferred
    )


def test_family_budget_blocks_cross_identity_same_family():
    planned = plan_wave_admission(
        wave(
            item(
                "alpha",
                repository="owner/alpha",
                priority="P0",
                lead="ONE",
            ),
            item(
                "beta",
                repository="owner/beta",
                priority="P0",
                lead="VOSS",
            ),
        ),
        budget=WaveExecutionBudget(
            max_parallel=2,
            max_per_identity=1,
            max_per_family=1,
        ),
    )
    assert [selected.subject_id for selected in planned.selected] == ["alpha"]
    blocked = next(
        deferred for deferred in planned.deferred
        if deferred.subject_id == "beta"
    )
    assert blocked.reason == "FAMILY_BUDGET"


def test_repository_collision_blocks_overlapping_workstream():
    repository = item(
        "repo",
        priority="P0",
        lead="ONE",
        repository="owner/shared",
    )
    workstream = item(
        "workstream",
        priority="P1",
        lead="VOSS",
        repository="owner/shared",
        kind="workstream",
    )
    planned = plan_wave_admission(
        wave(repository, workstream),
        budget=WaveExecutionBudget(max_parallel=2, max_per_identity=1, max_per_family=2),
    )
    assert [selected.subject_id for selected in planned.selected] == ["repo"]
    blocked = next(
        deferred for deferred in planned.deferred
        if deferred.subject_id == "workstream"
    )
    assert blocked.reason == "COLLISION"
    assert blocked.collision_keys == ("repository:owner/shared",)


def test_existing_occupied_collision_key_blocks_admission():
    planned = plan_wave_admission(
        wave(item("repo", repository="owner/shared")),
        budget=WaveExecutionBudget(max_parallel=1, max_per_identity=1, max_per_family=1),
        occupied_collision_keys=("repository:owner/shared",),
    )
    assert planned.selected == ()
    assert planned.deferred[0].reason == "COLLISION"


def test_held_or_no_effect_item_never_executes():
    held = item(
        "old",
        state="HELD",
        action="PRESERVE_ONLY",
        ceiling="NO_EFFECT",
    )
    planned = plan_wave_admission(
        wave(held),
        budget=WaveExecutionBudget(max_parallel=1, max_per_identity=1, max_per_family=1),
    )
    assert planned.selected == ()
    assert planned.deferred[0].reason == "NOT_QUEUED"


def test_real_public_wave_produces_bounded_collision_free_slice():
    public_wave = load_advancement_wave(
        ROOT / "portfolio" / "advancement_wave.public.json"
    )
    planned = plan_wave_admission(
        public_wave,
        budget=WaveExecutionBudget(max_parallel=6, max_per_identity=1, max_per_family=1),
    )
    assert len(planned.selected) <= 6
    assert len({item.lead_identity for item in planned.selected}) == len(
        planned.selected
    )
    all_keys = [
        key
        for selected in planned.selected
        for key in selected.collision_keys
    ]
    assert len(all_keys) == len(set(all_keys))
    assert all(selected.priority in {"P0", "P1", "P2", "P3", "P4"} for selected in planned.selected)


def test_non_repository_surface_gets_explicit_collision_key():
    workstream = item(
        "workspace",
        repository="Google Drive staging",
        kind="workstream",
    )
    assert collision_keys(workstream) == ("surface:google drive staging",)
