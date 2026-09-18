import pytest

from runner import cli as cli_module
from runner.cli import main


def test_validate_command_returns_zero(capsys):
    assert main(["validate"]) == 0
    assert "registries valid" in capsys.readouterr().out.lower()


def test_inventory_reports_twelve_registered_workers(capsys):
    assert main(["inventory"]) == 0
    out = capsys.readouterr().out
    assert "projects: 13" in out.lower()
    assert "workers: 12" in out.lower()
    assert "registered: 12" in out.lower()


def test_inventory_uses_explicit_external_project_registry(tmp_path, monkeypatch, capsys):
    registry = tmp_path / "private-projects.yaml"
    registry.write_text(
        """
projects:
- id: private-example
  name: Private Example
  visibility: private
  repositories:
  - example-owner/private-example
  capabilities:
  - read
  - analyze
  - propose
  assignment_scope: EXTERNAL_BOUNDED
  review_scope: STANDING
  family_id: private-family
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("PROJECT_RUNNER_PROJECT_REGISTRY", str(registry.resolve()))

    assert main(["inventory"]) == 0
    out = capsys.readouterr().out.lower()
    assert "projects: 1" in out
    assert "workers: 12" in out


def test_external_registry_requires_explicit_scope_metadata(tmp_path, monkeypatch):
    registry = tmp_path / "secret-portfolio.yaml"
    registry.write_text(
        """
projects:
- id: private-project-name
  name: Private Project Name
  visibility: private
  repositories:
  - private-owner/private-repository
  capabilities:
  - read
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("PROJECT_RUNNER_PROJECT_REGISTRY", str(registry.resolve()))

    with pytest.raises(ValueError, match="requires explicit assignment_scope") as exc:
        main(["inventory"])

    message = str(exc.value)
    assert "private-project-name" not in message
    assert "private-owner" not in message


def test_external_registry_missing_path_is_redacted(tmp_path, monkeypatch):
    secret_path = tmp_path / "private-client-project.yaml"
    monkeypatch.setenv("PROJECT_RUNNER_PROJECT_REGISTRY", str(secret_path.resolve()))

    with pytest.raises(ValueError, match="external project registry is unavailable") as exc:
        main(["inventory"])

    assert "private-client-project" not in str(exc.value)


def test_external_registry_rejects_relative_path(monkeypatch):
    monkeypatch.setenv("PROJECT_RUNNER_PROJECT_REGISTRY", "private/projects.yaml")

    with pytest.raises(ValueError, match="requires an absolute path"):
        main(["inventory"])


def test_external_registry_must_live_outside_checkout(tmp_path, monkeypatch):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    registry = checkout / "private-projects.yaml"
    registry.write_text(
        """
projects:
- id: example
  name: Example
  visibility: private
  repositories: [owner/example]
  capabilities: [read]
  assignment_scope: EXTERNAL_BOUNDED
  review_scope: STANDING
  family_id: example-family
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli_module, "ROOT", checkout)
    monkeypatch.setenv("PROJECT_RUNNER_PROJECT_REGISTRY", str(registry.resolve()))

    with pytest.raises(ValueError, match="outside the Project Runner checkout"):
        main(["inventory"])
