from pathlib import Path

from runner.portfolio_advancement import load_advancement_wave
from runner.registry import load_projects

ROOT = Path(__file__).resolve().parents[2]
TRANCHE = {"roots", "world-zero", "on-theo", "testament", "meso-crct"}


def test_final_p1_registry_is_fail_closed():
    projects = {project.id: project for project in load_projects(ROOT / "registry" / "projects.yaml")}
    for project_id in TRANCHE:
        project = projects[project_id]
        assert project.scheduling_state.value == "HELD"
        assert set(project.capabilities) == {"read", "analyze", "propose"}
        assert project.execution_targets == ()


def test_final_p1_is_refreshed_but_held():
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    items = {
        item.subject_id: item
        for item in wave.items
        if item.subject_kind == "repository" and item.subject_id in TRANCHE
    }
    assert set(items) == TRANCHE
    assert all(item.execution_state == "HELD" for item in items.values())
    assert all(
        item.source_status.startswith("CURRENTNESS_REFRESHED_EXACT_SOURCE__EXECUTION_HELD")
        for item in items.values()
    )


def test_final_p1_preserves_mixed_evidence_gates():
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    items = {
        item.subject_id: item
        for item in wave.items
        if item.subject_kind == "repository" and item.subject_id in TRANCHE
    }
    assert items["roots"].review_gate == "CONSUMER_EVIDENCE"
    assert items["world-zero"].review_gate == "RESULT_INTERPRETATION_REVIEW"
    assert items["on-theo"].review_gate == "REPAIR_CANDIDATE_AND_EXACT_MAIN_REQUALIFICATION"
    assert items["testament"].review_gate == "EXACT_MAIN_QUALIFICATION"
    assert items["meso-crct"].review_gate == "WELFARE_AND_EFFECT_QUALIFICATION"


def test_no_p1_repository_remains_in_inherited_currentness_audit():
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    inherited_p1 = [
        item.subject_id
        for item in wave.items
        if item.subject_kind == "repository"
        and item.priority == "P1"
        and item.action == "CURRENTNESS_AUDIT"
    ]
    assert inherited_p1 == []
