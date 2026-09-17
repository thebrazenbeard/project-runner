from runner.cli import main


def test_validate_command_returns_zero(capsys):
    assert main(["validate"]) == 0
    assert "registries valid" in capsys.readouterr().out.lower()


def test_inventory_reports_twelve_registered_workers(capsys):
    assert main(["inventory"]) == 0
    out = capsys.readouterr().out
    assert "projects: 5" in out.lower()
    assert "workers: 12" in out.lower()
    assert "registered: 12" in out.lower()
