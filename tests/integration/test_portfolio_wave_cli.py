import json

from runner.cli import main


def test_portfolio_wave_plan_cli_is_bounded_and_non_authorizing(capsys):
    code = main(
        [
            "portfolio-wave-plan",
            "--max-parallel",
            "5",
            "--max-per-identity",
            "1",
            "--max-per-family",
            "1",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "PORTFOLIO_WAVE_ADMISSION_PLAN_V1"
    assert payload["execution_authority"] is False
    assert payload["protected_effects_authorized"] is False
    assert payload["summary"]["selected"] <= 5
    assert max(payload["summary"]["selected_by_identity"].values()) <= 1
    assert max(payload["summary"]["selected_by_family"].values()) <= 1


def test_portfolio_wave_plan_cli_respects_occupied_collision(capsys):
    code = main(
        [
            "portfolio-wave-plan",
            "--max-parallel",
            "10",
            "--max-per-identity",
            "2",
            "--max-per-family",
            "2",
            "--occupied-collision-key",
            "repository:thebrazenbeard/project-runner",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    selected = {item["subject_id"] for item in payload["selected"]}
    assert "project-runner" not in selected
    blocked = [
        item
        for item in payload["deferred"]
        if item["subject_id"] == "project-runner"
    ]
    assert blocked
    assert blocked[0]["reason"] == "COLLISION"
