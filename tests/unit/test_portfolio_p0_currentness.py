import json
from pathlib import Path

import pytest

from runner.portfolio_p0_currentness import load_p0_currentness_overlay


ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "portfolio" / "p0-currentness.public.json"
CORPUS = ROOT / "portfolio" / "corpus.public.json"


def _write_overlay(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "overlay.json"
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def test_real_p0_currentness_overlay_covers_exact_corpus_p0_set():
    payload = load_p0_currentness_overlay(OVERLAY, CORPUS)

    assert payload["coverage"] == {
        "priority": "P0",
        "subject_kind": "repository",
        "repository_count": 10,
        "complete_for_scope": True,
    }
    assert {item["subject_id"] for item in payload["subjects"]} == {
        "bt2",
        "discovery",
        "project-lantern",
        "project-runner",
        "vera",
        "vera-control-plane",
        "vera-mesh",
        "vera-model-training",
        "vera-mono",
        "workbridgemcp",
    }
    assert payload["governance"]["priority_is_authority"] is False
    assert payload["governance"]["merge_authorized"] is False
    assert payload["governance"]["deploy_authorized"] is False


def test_p0_currentness_overlay_rejects_wrong_corpus_blob(tmp_path):
    payload = json.loads(OVERLAY.read_text(encoding="utf-8"))
    payload["corpus_binding"]["git_blob_sha"] = "0" * 40

    with pytest.raises(
        ValueError,
        match="corpus blob binding mismatch",
    ):
        load_p0_currentness_overlay(
            _write_overlay(tmp_path, payload),
            CORPUS,
        )


def test_p0_currentness_overlay_rejects_missing_p0_subject(tmp_path):
    payload = json.loads(OVERLAY.read_text(encoding="utf-8"))
    payload["subjects"] = payload["subjects"][:-1]
    payload["coverage"]["repository_count"] -= 1

    with pytest.raises(
        ValueError,
        match="does not cover exact corpus P0 set",
    ):
        load_p0_currentness_overlay(
            _write_overlay(tmp_path, payload),
            CORPUS,
        )


def test_p0_currentness_overlay_rejects_repository_identity_drift(tmp_path):
    payload = json.loads(OVERLAY.read_text(encoding="utf-8"))
    payload["subjects"][0]["repository"] = "thebrazenbeard/not-bt2"

    with pytest.raises(
        ValueError,
        match="repository mismatch for bt2",
    ):
        load_p0_currentness_overlay(
            _write_overlay(tmp_path, payload),
            CORPUS,
        )


def test_p0_currentness_overlay_rejects_duplicate_subject_id(tmp_path):
    payload = json.loads(OVERLAY.read_text(encoding="utf-8"))
    payload["subjects"][1]["subject_id"] = payload["subjects"][0]["subject_id"]

    with pytest.raises(
        ValueError,
        match="duplicate P0 currentness subject id",
    ):
        load_p0_currentness_overlay(
            _write_overlay(tmp_path, payload),
            CORPUS,
        )
