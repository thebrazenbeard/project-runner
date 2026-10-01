from pathlib import Path

from runner.portfolio_advancement import load_advancement_wave

ROOT = Path(__file__).resolve().parents[2]
GREEN = {
    "lgcm",
    "unvtrslr",
    "spm",
    "mosaic",
    "voss",
    "transcendence",
    "vera-r9a0",
}


def test_green_qualification_candidates_remain_held():
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    items = {
        item.subject_id: item
        for item in wave.items
        if item.subject_kind == "repository" and item.subject_id in GREEN
    }
    assert set(items) == GREEN
    assert all(item.execution_state == "HELD" for item in items.values())
    assert all(item.effect_ceiling == "SOURCE_ONLY" for item in items.values())
    assert all(
        item.source_status.startswith("CURRENTNESS_REFRESHED_EXACT_SOURCE__GREEN_CANDIDATE_HELD")
        for item in items.values()
    )


def test_green_candidates_leave_the_bare_exact_main_qualification_bucket():
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    exact_main_gaps = {
        item.subject_id
        for item in wave.items
        if item.subject_kind == "repository"
        and item.review_gate == "EXACT_MAIN_QUALIFICATION"
    }
    assert GREEN.isdisjoint(exact_main_gaps)
    assert {"testament", "hephaestus"} <= exact_main_gaps
    assert exact_main_gaps == {
        "conations",
        "hephaestus",
        "intranel",
        "personification",
        "temporal",
        "testament",
    }


def test_green_candidate_gates_do_not_claim_main_qualification():
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    items = {
        item.subject_id: item
        for item in wave.items
        if item.subject_kind == "repository" and item.subject_id in GREEN
    }
    assert items["lgcm"].review_gate == "GREEN_CANDIDATE_INTEGRATION_AND_MAIN_REQUALIFICATION"
    assert items["unvtrslr"].review_gate == "GREEN_CANDIDATE_INTEGRATION_AND_MAIN_REQUALIFICATION"
    assert items["spm"].review_gate == "GREEN_TEST_CANDIDATE_INTEGRATION_AND_CLAIM_REVIEW"
    assert items["mosaic"].review_gate == "GREEN_CANDIDATE_INTEGRATION_AND_MAIN_REQUALIFICATION"
    assert items["voss"].review_gate == "GREEN_CANDIDATE_INTEGRATION_AND_REVIEW_AUTHORITY_SEPARATION"
    assert items["transcendence"].review_gate == "GREEN_CURRENT_MAIN_CANDIDATE_CONTINUITY_REVIEW"
    assert items["vera-r9a0"].review_gate == "GREEN_CURRENT_MAIN_CANDIDATE_DONOR_REVIEW"
