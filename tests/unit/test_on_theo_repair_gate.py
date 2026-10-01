from pathlib import Path

from runner.portfolio_advancement import load_advancement_wave

ROOT = Path(__file__).resolve().parents[2]


def test_on_theo_repair_review_is_closed_but_main_remains_unqualified():
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    item = next(
        item for item in wave.items
        if item.subject_kind == "repository" and item.subject_id == "on-theo"
    )
    assert item.execution_state == "HELD"
    assert item.effect_ceiling == "SOURCE_ONLY"
    assert item.review_gate == "INTEGRATE_REPAIR_AND_EXACT_MAIN_REQUALIFICATION"
    assert item.source_status.startswith(
        "CURRENTNESS_REFRESHED_REPAIR_CANDIDATE_HOSTILE_REVIEWED__MAIN_UNQUALIFIED__EXECUTION_HELD"
    )


def test_on_theo_frontier_preserves_research_claim_boundary():
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    item = next(
        item for item in wave.items
        if item.subject_kind == "repository" and item.subject_id == "on-theo"
    )
    assert "historical/religious claims" in item.frontier
    assert "witness judgments" in item.frontier
    assert "research confidence" in item.frontier
