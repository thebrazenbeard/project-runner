from pathlib import Path

from runner.portfolio_advancement import load_advancement_wave
from runner.portfolio_corpus import load_portfolio_corpus

ROOT = Path(__file__).resolve().parents[2]
WORKSTREAMS = {"yeshua-real-testament", "nature-of-existence"}


def test_no_public_wave_subject_remains_inherited_or_currentness_audit():
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    assert not [
        item
        for item in wave.items
        if item.action == "CURRENTNESS_AUDIT"
        or "INHERITED_" in item.source_status
    ]


def test_public_workstreams_are_refreshed_and_held():
    wave = load_advancement_wave(ROOT / "portfolio" / "advancement_wave.public.json")
    items = {
        item.subject_id: item
        for item in wave.items
        if item.subject_kind == "workstream"
    }
    assert set(items) == WORKSTREAMS
    assert all(item.execution_state == "HELD" for item in items.values())
    assert all(item.effect_ceiling == "SOURCE_ONLY" for item in items.values())
    assert all(
        item.source_status.startswith("CURRENTNESS_REFRESHED_DURABLE_SURFACES__EXECUTION_HELD")
        for item in items.values()
    )
    assert items["yeshua-real-testament"].review_gate == "UPSTREAM_SOURCE_AND_DOWNSTREAM_QUALIFICATION"
    assert items["nature-of-existence"].review_gate == "SOURCE_HYPOTHESIS_BOUNDARY"


def test_corpus_status_declares_repository_and_workstream_currentness_complete():
    corpus = load_portfolio_corpus(
        ROOT / "portfolio" / "corpus.public.json",
        public_safe=True,
    )
    assert len(corpus.records) == 58
    assert len(corpus.workstreams) == 2
    assert "No public repository or public workstream remains on inherited 2026-09-28 currentness" in corpus.status_basis
