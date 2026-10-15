"""Portfolio 8×64 currentness wave: pure mocks, real admission and durable receipts."""
from pathlib import Path
import json
import pytest

from runner import live_portfolio_wave as wave


def _mocked_gh(*argv, deadline=24.0):
    if argv[:2] == ("repo", "list"):
        return [
            {"nameWithOwner": "thebrazenbeard/thebrazenbeard", "isArchived":False,"isPrivate":False},
            *({"nameWithOwner": f"thebrazenbeard/{x}", "isArchived": False, "isPrivate": True}
                for x in ("alpha", "bravo", "charlie")),
            {"nameWithOwner": "thebrazenbeard/archived", "isArchived": True, "isPrivate": False},
        ]
    path=argv[1]
    if path.startswith("repos/") and path.endswith("/actions/runs?branch=main&per_page=5"):
        return {"workflow_runs": []}
    if path.endswith("/pulls?state=open&per_page=100"):
        return []
    if "/git/trees/" in path:
        return {"tree":[{"path":"pyproject.toml"}]}
    if path.endswith("/branches/main"):
        return {"commit":{"sha":"a"*40}}
    if path.startswith("repos/"):
        return {"full_name":path.removeprefix("repos/"),"default_branch":"main",
                "archived":False,"private":True}
    raise AssertionError(f"Unexpected GitHub endpoint: {argv}")


def test_owner_scope_requires_exact_live_membership(monkeypatch):
    monkeypatch.setattr(wave,"gh",_mocked_gh)
    assert wave.owner_scope("thebrazenbeard",expected_count=3) == (
        "thebrazenbeard/alpha", "thebrazenbeard/bravo", "thebrazenbeard/charlie"
    )
    with pytest.raises(RuntimeError, match="scope mismatch"):
        wave.owner_scope("thebrazenbeard",expected_count=4)
    with pytest.raises(ValueError,match="unqualified owner"):
        wave.owner_scope("--injected",expected_count=3)


def test_runner_reconciles_exact_scope_across_execution_and_logic_windows(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(wave,"gh",_mocked_gh)
    target=tmp_path/"private-receipts"
    assert wave.main([
        "--owner","thebrazenbeard","--expected","3",
        "--output",str(target),"--execution-lanes","2","--logic-slots","2"
    ]) == 0
    summary=json.loads((target/"summary.json").read_text())
    assert summary["scope_count"]==3 and summary["receipts"]==3
    assert summary["state_counts"]=={"SOURCE_CURRENTNESS_VERIFIED":3}
    assert summary["max_concurrent_executions"]==2
    assert summary["max_logical_queue"]==2
    assert summary["source_code_executed"]==0
    assert summary["repositories_modified"]==0
    assert len(list((target/"subjects").rglob("attempt.json")))==3
    assert len(list((target/"subjects").rglob("final.json")))==3
    assert len(list((target/"batches").glob("*.json")))>=2
    for record in (target/"subjects").rglob("final.json"):
        detail=json.loads(record.read_text())
        assert detail["head_sha"]=="a"*40
        assert detail["source_code_executed"] is False
        assert detail["github_repository_mutated"] is False
    with pytest.raises(RuntimeError,match="already exists"):
        wave.main(["--expected","3","--output",str(target),
                   "--execution-lanes","2","--logic-slots","2"])


def test_8_by_64_limits_and_no_checkout_receipts(tmp_path):
    for lane,queue in ((9,64),(8,65),(0,8),(2,0)):
        with pytest.raises(ValueError,match="limited to"):
            wave.main(["--expected","3","--output",str(tmp_path/"bad"),
                       "--execution-lanes",str(lane),"--logic-slots",str(queue)])
    with pytest.raises(ValueError,match="outside repository"):
        wave.main(["--expected","3",
            "--output",str(Path(wave.__file__).resolve().parents[1]/"secret-receipts")])


def test_cross_repository_identity_mismatch_is_held(monkeypatch,tmp_path):
    wave.OUTPUT=tmp_path
    def wrong(*args,**kwargs):
        return {"full_name":"thebrazenbeard/not-alpha","default_branch":"main"}
    monkeypatch.setattr(wave,"gh",wrong)
    result=wave.inspect("thebrazenbeard/alpha","lane-1",1)
    assert result["state"]=="VERIFIED_HELD"
    assert "identity" in result["reason"]
    assert result["github_repository_mutated"] is False
    assert (tmp_path/"subjects"/"alpha"/"attempt.json").is_file()
    assert (tmp_path/"subjects"/"alpha"/"final.json").is_file()
