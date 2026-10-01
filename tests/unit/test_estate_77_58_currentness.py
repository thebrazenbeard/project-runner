from pathlib import Path

from runner.portfolio_advancement import load_advancement_wave
from runner.portfolio_corpus import load_portfolio_corpus
from runner.registry import load_projects

ROOT = Path(__file__).resolve().parents[2]


def test_77_58_corpus_and_wave_are_complete():
    corpus = load_portfolio_corpus(ROOT / "portfolio" / "corpus.public.json", public_safe=True)
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    assert corpus.counts.total == 77
    assert corpus.counts.public == 58
    assert corpus.counts.private == 19
    assert len(corpus.records) == 58
    assert len([item for item in wave.items if item.subject_kind == "repository"]) == 58


def test_pro_run_logical_identity_survives_repository_rename():
    corpus = load_portfolio_corpus(ROOT / "portfolio" / "corpus.public.json", public_safe=True)
    record = next(record for record in corpus.records if record.id == "pro-run")
    assert record.repository == "thebrazenbeard/pre-active"
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    item = next(item for item in wave.items if item.subject_kind == "repository" and item.subject_id == "pro-run")
    assert item.repositories == ("thebrazenbeard/pre-active",)
    assert item.review_gate == "CONSUMER_EVIDENCE"
    assert item.execution_state == "HELD"


def test_executor_main_and_draft_candidate_remain_separate_and_held():
    corpus = load_portfolio_corpus(ROOT / "portfolio" / "corpus.public.json", public_safe=True)
    record = next(record for record in corpus.records if record.id == "executor")
    assert record.repository == "thebrazenbeard/executor"
    assert "bootstrap" in record.status.lower()
    assert "Draft PR #1" in record.status
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    item = next(item for item in wave.items if item.subject_kind == "repository" and item.subject_id == "executor")
    assert item.execution_state == "HELD"
    assert item.effect_ceiling == "SOURCE_ONLY"
    assert item.review_gate == "DRAFT_CANDIDATE_SECURITY_AND_AUTHORITY_REVIEW"
    projects = {project.id: project for project in load_projects(ROOT / "registry" / "projects.yaml")}
    project = projects["executor"]
    assert project.scheduling_state.value == "HELD"
    assert set(project.capabilities) == {"read", "analyze", "propose"}
    assert project.execution_targets == ()
