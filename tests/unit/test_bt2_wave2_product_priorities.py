"""The BT2 Wave 2 public priority cut is descriptive, not dispatch authority."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CUT = ROOT / "portfolio" / "bt2_wave2_product_priorities.public.json"


def test_wave2_counts_and_user_priority_basis():
    data = json.loads(CUT.read_text(encoding="utf-8"))
    assert data["schema"] == "BT2_WAVE2_PRODUCT_PRIORITY_SELECTION_V1"
    assert data["not_an_execution_grant"] is True
    assert data["public_corpus_restaging_required"] is True
    assert data["private_repository_names_intentionally_omitted"] is True
    entries = data["proposed_public_subjects"]
    assert len(entries) == data["public_repository_count"] == 12
    assert data["private_repository_count"] == 1
    assert len(entries) + data["private_repository_count"] == 13
    assert sum(e["selection_basis"] == "USER_NAMED" for e in entries) == 8
    assert sum(e["selection_basis"] == "BT2_PROPOSED" for e in entries) == 4


def test_wave2_protects_private_membership_and_effect_boundary():
    source = CUT.read_text(encoding="utf-8")
    data = json.loads(source)
    assert "vera-os" not in source
    entries = data["proposed_public_subjects"]
    names = [item["repository"].lower() for item in entries]
    assert len(names) == len(set(names))
    assert set(names) == {"thebrazenbeard/" + name for name in (
        "portal", "project-runner", "tattler", "sql-connectome",
        "blotter", "pre-active", "meso-crct", "vera_model_training",
        "vera-mono", "executor", "volition", "vera-mesh",
    )}
    assert all(re.fullmatch(r"[0-9a-f]{40}", e["head_sha"]) for e in entries)
    assert all(e["effect_ceiling"] == "SOURCE_ONLY" for e in entries)
    assert all(e["integration_status"] == "CANDIDATE_ONLY" for e in entries)
    assert all(e["frontier"] for e in entries)
