from pathlib import Path

from runner.portfolio_advancement import load_advancement_wave

ROOT = Path(__file__).resolve().parents[2]


def test_driftguard_candidate_review_is_closed_but_execution_is_held():
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    item = next(
        item for item in wave.items
        if item.subject_kind == "repository" and item.subject_id == "driftguard"
    )
    assert item.execution_state == "HELD"
    assert item.effect_ceiling == "SOURCE_ONLY"
    assert item.review_gate == "EXECUTION_ROUTE_ADMISSION"
    assert item.source_status.startswith(
        "CURRENTNESS_REFRESHED_GREEN_CANDIDATE_HOSTILE_REVIEWED__EXECUTION_HELD"
    )


def test_driftguard_frontier_does_not_promote_provider_authority():
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    item = next(
        item for item in wave.items
        if item.subject_kind == "repository" and item.subject_id == "driftguard"
    )
    assert "protected-effect authority" in item.frontier
    assert "provider readback/reconciliation" in item.frontier
    assert "trust root" in item.frontier
