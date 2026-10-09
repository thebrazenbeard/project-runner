"""A priority wave may exceed the worker budget, not the execution boundary."""
from runner.portfolio_advancement import AdvancementItem, AdvancementWave
from runner.portfolio_wave_scheduler import WaveExecutionBudget, plan_wave_admission


def test_thirteen_p0_frontiers_are_fenced_by_one_slot_global_budget():
    items = tuple(
        AdvancementItem(
            subject_kind="repository",
            subject_id=f"build-{i:02d}",
            repositories=(f"owner/project-{i:02d}",),
            priority="P0",
            family_id=f"family-{i:02d}",
            activity_state="ACTIVE",
            lead_identity=f"BUILD-{i:02d}",
            reviewer_identities=("REZON",),
            action="EXECUTE_FRONTIER",
            execution_state="QUEUED",
            effect_ceiling="SOURCE_ONLY",
            review_gate="EXACT_HEAD_REVIEW",
            frontier="source repair",
            source_status="NOT_VERIFIED",
        )
        for i in range(13)
    )
    work = AdvancementWave(
        wave_id="PROJECT_RUNNER_PORTFOLIO_ADVANCEMENT_WAVE_V1",
        generated_at="2026-10-09",
        corpus_binding={},
        identities={},
        policy={},
        items=items,
    )
    plan = plan_wave_admission(
        work,
        budget=WaveExecutionBudget(
            max_parallel=1, max_per_identity=1, max_per_family=1,
            max_per_lane=1,
        ),
    )
    assert len(plan.selected) == 1
    assert len(plan.deferred) == 12
    assert {x.reason for x in plan.deferred} == {"GLOBAL_BUDGET"}
    assert all(x.effect_ceiling == "SOURCE_ONLY" for x in plan.selected)
    assert len({key for x in plan.selected for key in x.collision_keys}) == 1
