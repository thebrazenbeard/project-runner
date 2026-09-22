import hashlib
import json
from pathlib import Path

import pytest

from runner import cli as cli_module
from runner.cli import main


def _pin_external_registry(registry, monkeypatch):
    monkeypatch.setenv(
        "PROJECT_RUNNER_PROJECT_REGISTRY",
        str(registry.resolve()),
    )
    monkeypatch.setenv(
        "PROJECT_RUNNER_PROJECT_REGISTRY_SHA256",
        hashlib.sha256(registry.read_bytes()).hexdigest(),
    )
    monkeypatch.setenv(
        "PROJECT_RUNNER_PRIVATE_COLLISION_KEY",
        "11" * 32,
    )


def test_validate_command_returns_zero(capsys):
    assert main(["validate"]) == 0
    assert "registries valid" in capsys.readouterr().out.lower()


def test_inventory_reports_twelve_registered_workers(capsys):
    assert main(["inventory"]) == 0
    out = capsys.readouterr().out
    assert "projects: 15" in out.lower()
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
  scheduling_state: SCHEDULABLE
""".lstrip(),
        encoding="utf-8",
    )
    _pin_external_registry(registry, monkeypatch)

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
    _pin_external_registry(registry, monkeypatch)

    with pytest.raises(ValueError, match="requires explicit assignment_scope") as exc:
        main(["inventory"])

    message = str(exc.value)
    assert "private-project-name" not in message
    assert "private-owner" not in message


def test_external_registry_missing_path_is_redacted(tmp_path, monkeypatch):
    secret_path = tmp_path / "private-client-project.yaml"
    monkeypatch.setenv("PROJECT_RUNNER_PROJECT_REGISTRY", str(secret_path.resolve()))
    monkeypatch.setenv("PROJECT_RUNNER_PROJECT_REGISTRY_SHA256", "a" * 64)

    with pytest.raises(ValueError, match="external project registry is unavailable") as exc:
        main(["inventory"])

    assert "private-client-project" not in str(exc.value)


def test_external_registry_rejects_relative_path(monkeypatch):
    monkeypatch.setenv("PROJECT_RUNNER_PROJECT_REGISTRY", "private/projects.yaml")
    monkeypatch.setenv("PROJECT_RUNNER_PROJECT_REGISTRY_SHA256", "a" * 64)

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
  scheduling_state: SCHEDULABLE
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli_module, "ROOT", checkout)
    _pin_external_registry(registry, monkeypatch)

    with pytest.raises(ValueError, match="outside the Project Runner checkout"):
        main(["inventory"])


def test_external_registry_requires_expected_digest(tmp_path, monkeypatch):
    registry = tmp_path / "private-client-alpha.yaml"
    registry.write_text(
        """
projects:
- id: private-client-alpha
  name: Private Client Alpha
  visibility: private
  repositories: [secret-owner/secret-repository]
  capabilities: [read]
  assignment_scope: EXTERNAL_BOUNDED
  review_scope: STANDING
  family_id: private-alpha
  scheduling_state: SCHEDULABLE
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("PROJECT_RUNNER_PROJECT_REGISTRY", str(registry.resolve()))

    with pytest.raises(ValueError, match="requires an expected lowercase SHA-256") as exc:
        main(["inventory"])

    message = str(exc.value)
    assert "private-client-alpha" not in message
    assert "secret-owner" not in message


def test_external_registry_digest_mismatch_fails_closed_and_redacted(
    tmp_path,
    monkeypatch,
):
    registry = tmp_path / "private-client-beta.yaml"
    registry.write_text(
        """
projects:
- id: private-client-beta
  name: Private Client Beta
  visibility: private
  repositories: [secret-owner/secret-beta]
  capabilities: [read]
  assignment_scope: EXTERNAL_BOUNDED
  review_scope: STANDING
  family_id: private-beta
  scheduling_state: SCHEDULABLE
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("PROJECT_RUNNER_PROJECT_REGISTRY", str(registry.resolve()))
    monkeypatch.setenv("PROJECT_RUNNER_PROJECT_REGISTRY_SHA256", "0" * 64)

    with pytest.raises(ValueError, match="external project registry digest mismatch") as exc:
        main(["inventory"])

    message = str(exc.value)
    assert "private-client-beta" not in message
    assert "secret-owner" not in message
    assert "private-client-beta.yaml" not in message


@pytest.mark.parametrize(
    "command",
    ["evaluate-change", "frontier-report", "dispatch-report"],
)
def test_external_registry_disables_detailed_reporting_before_private_inputs_load(
    command,
    tmp_path,
    monkeypatch,
    capsys,
):
    registry = tmp_path / "private-registry.yaml"
    registry.write_text(
        """
projects:
- id: private-example
  name: Private Example
  visibility: private
  repositories: [secret-owner/private-example]
  capabilities: [read, analyze]
  assignment_scope: EXTERNAL_BOUNDED
  review_scope: STANDING
  family_id: private-family
  scheduling_state: SCHEDULABLE
""".lstrip(),
        encoding="utf-8",
    )
    _pin_external_registry(registry, monkeypatch)

    secret_before = tmp_path / "secret-before-do-not-read.yaml"
    secret_after = tmp_path / "secret-after-do-not-read.yaml"
    secret_dependencies = tmp_path / "secret-dependencies-do-not-read.yaml"

    with pytest.raises(
        ValueError,
        match="detailed reports are disabled with an external project registry",
    ):
        main(
            [
                command,
                "--before",
                str(secret_before),
                "--after",
                str(secret_after),
                "--dependencies",
                str(secret_dependencies),
            ]
        )

    assert capsys.readouterr().out == ""


def test_external_held_project_cannot_become_ready_frontier(tmp_path, monkeypatch):
    registry = tmp_path / "private-held.yaml"
    registry.write_text(
        """
projects:
- id: transcendence
  name: Held Transcendence
  visibility: private
  repositories: [secret-owner/private-transcendence]
  capabilities: [read, analyze]
  assignment_scope: EXTERNAL_BOUNDED
  review_scope: STANDING
  family_id: transcendence-family
  scheduling_state: HELD
""".lstrip(),
        encoding="utf-8",
    )
    _pin_external_registry(registry, monkeypatch)

    fixtures = Path(__file__).resolve().parents[1] / "fixtures"
    frontiers = cli_module._derive_frontier_set(
        fixtures / "m6-hc-substantive.yaml",
        fixtures / "m6-hc-current.yaml",
        fixtures / "m6-hc-transcendence-dependencies.yaml",
    )

    assert len(frontiers) == 1
    assert frontiers[0].project == "transcendence"
    assert frontiers[0].status.value == "WAITING_SCHEDULING"


def test_external_registry_obscures_collision_keys(tmp_path, monkeypatch):
    registry = tmp_path / "private-schedulable.yaml"
    registry.write_text(
        """
projects:
- id: transcendence
  name: Private Transcendence
  visibility: private
  repositories: [secret-owner/private-transcendence]
  capabilities: [read, analyze]
  assignment_scope: EXTERNAL_BOUNDED
  review_scope: STANDING
  family_id: transcendence-family
  scheduling_state: SCHEDULABLE
""".lstrip(),
        encoding="utf-8",
    )
    _pin_external_registry(registry, monkeypatch)

    fixtures = Path(__file__).resolve().parents[1] / "fixtures"
    first = cli_module._derive_frontier_set(
        fixtures / "m6-hc-substantive.yaml",
        fixtures / "m6-hc-current.yaml",
        fixtures / "m6-hc-transcendence-dependencies.yaml",
    )
    second = cli_module._derive_frontier_set(
        fixtures / "m6-hc-substantive.yaml",
        fixtures / "m6-hc-current.yaml",
        fixtures / "m6-hc-transcendence-dependencies.yaml",
    )

    assert len(first) == len(second) == 1
    assert first[0].status.value == "READY"
    assert first[0].collision_keys == second[0].collision_keys
    assert len(first[0].collision_keys) == 1
    collision_key = first[0].collision_keys[0]
    assert collision_key.startswith("private:")
    assert "transcendence" not in collision_key
    assert "secret-owner" not in collision_key
    assert "project:" not in collision_key


def test_external_registry_requires_secret_collision_key_for_frontier_derivation(
    tmp_path,
    monkeypatch,
):
    registry = tmp_path / "private-collision-key.yaml"
    registry.write_text(
        """
projects:
- id: transcendence
  name: Private Transcendence
  visibility: private
  repositories: [secret-owner/private-transcendence]
  capabilities: [read, analyze]
  assignment_scope: EXTERNAL_BOUNDED
  review_scope: STANDING
  family_id: transcendence-family
  scheduling_state: SCHEDULABLE
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "PROJECT_RUNNER_PROJECT_REGISTRY",
        str(registry.resolve()),
    )
    monkeypatch.setenv(
        "PROJECT_RUNNER_PROJECT_REGISTRY_SHA256",
        hashlib.sha256(registry.read_bytes()).hexdigest(),
    )
    monkeypatch.delenv("PROJECT_RUNNER_PRIVATE_COLLISION_KEY", raising=False)

    fixtures = Path(__file__).resolve().parents[1] / "fixtures"
    with pytest.raises(
        ValueError,
        match="requires a private collision key",
    ):
        cli_module._derive_frontier_set(
            fixtures / "m6-hc-substantive.yaml",
            fixtures / "m6-hc-current.yaml",
            fixtures / "m6-hc-transcendence-dependencies.yaml",
        )


def test_private_collision_key_is_secret_keyed_not_registry_digest(
    tmp_path,
    monkeypatch,
):
    registry = tmp_path / "private-collision-rotation.yaml"
    registry.write_text(
        """
projects:
- id: transcendence
  name: Private Transcendence
  visibility: private
  repositories: [secret-owner/private-transcendence]
  capabilities: [read, analyze]
  assignment_scope: EXTERNAL_BOUNDED
  review_scope: STANDING
  family_id: transcendence-family
  scheduling_state: SCHEDULABLE
""".lstrip(),
        encoding="utf-8",
    )
    _pin_external_registry(registry, monkeypatch)
    fixtures = Path(__file__).resolve().parents[1] / "fixtures"

    first = cli_module._derive_frontier_set(
        fixtures / "m6-hc-substantive.yaml",
        fixtures / "m6-hc-current.yaml",
        fixtures / "m6-hc-transcendence-dependencies.yaml",
    )
    monkeypatch.setenv("PROJECT_RUNNER_PRIVATE_COLLISION_KEY", "22" * 32)
    second = cli_module._derive_frontier_set(
        fixtures / "m6-hc-substantive.yaml",
        fixtures / "m6-hc-current.yaml",
        fixtures / "m6-hc-transcendence-dependencies.yaml",
    )

    assert first[0].collision_keys != second[0].collision_keys
    for collision_key in first[0].collision_keys + second[0].collision_keys:
        assert collision_key.startswith("private:")
        assert "transcendence" not in collision_key
        assert "secret-owner" not in collision_key


def test_external_registry_frontier_summary_exposes_counts_not_private_identity(
    tmp_path,
    monkeypatch,
    capsys,
):
    registry = tmp_path / "private-summary.yaml"
    registry.write_text(
        """
projects:
- id: transcendence
  name: Private Transcendence
  visibility: private
  repositories: [secret-owner/private-transcendence]
  capabilities: [read, analyze]
  assignment_scope: EXTERNAL_BOUNDED
  review_scope: STANDING
  family_id: transcendence-family
  scheduling_state: HELD
""".lstrip(),
        encoding="utf-8",
    )
    _pin_external_registry(registry, monkeypatch)
    fixtures = Path(__file__).resolve().parents[1] / "fixtures"

    assert main(
        [
            "frontier-summary",
            "--before",
            str(fixtures / "m6-hc-substantive.yaml"),
            "--after",
            str(fixtures / "m6-hc-current.yaml"),
            "--dependencies",
            str(fixtures / "m6-hc-transcendence-dependencies.yaml"),
        ]
    ) == 0

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload == {
        "blocked": 1,
        "ready": 0,
        "statuses": {"WAITING_SCHEDULING": 1},
        "total": 1,
    }
    assert "transcendence" not in output
    assert "secret-owner" not in output
    assert "private-summary" not in output
    assert "collision" not in output


def test_external_registry_frontier_summary_redacts_input_failure(
    tmp_path,
    monkeypatch,
):
    registry = tmp_path / "private-summary.yaml"
    registry.write_text(
        """
projects:
- id: private-example
  name: Private Example
  visibility: private
  repositories: [secret-owner/private-example]
  capabilities: [read]
  assignment_scope: EXTERNAL_BOUNDED
  review_scope: STANDING
  family_id: private-family
  scheduling_state: SCHEDULABLE
""".lstrip(),
        encoding="utf-8",
    )
    _pin_external_registry(registry, monkeypatch)
    secret_before = tmp_path / "do-not-leak-private-before.yaml"
    secret_after = tmp_path / "do-not-leak-private-after.yaml"
    secret_dependencies = tmp_path / "do-not-leak-private-dependencies.yaml"

    with pytest.raises(
        ValueError,
        match="external frontier summary is unavailable or structurally invalid",
    ) as exc:
        main(
            [
                "frontier-summary",
                "--before",
                str(secret_before),
                "--after",
                str(secret_after),
                "--dependencies",
                str(secret_dependencies),
            ]
        )

    message = str(exc.value)
    assert "do-not-leak" not in message
    assert "private-example" not in message
    assert "secret-owner" not in message


@pytest.mark.parametrize(
    "state",
    ["HELD", "ARCHIVED", "DORMANT", "SENSITIVE_HELD", "DECISION_HELD"],
)
def test_external_non_schedulable_states_never_become_ready(
    state,
    tmp_path,
    monkeypatch,
):
    registry = tmp_path / "private-held-state.yaml"
    registry.write_text(
        f"""projects:
- id: transcendence
  name: Held Project
  visibility: private
  repositories: [secret-owner/private-project]
  capabilities: [read, analyze]
  assignment_scope: EXTERNAL_BOUNDED
  review_scope: STANDING
  family_id: held-family
  scheduling_state: {state}
""",
        encoding="utf-8",
    )
    _pin_external_registry(registry, monkeypatch)
    fixtures = Path(__file__).resolve().parents[1] / "fixtures"
    frontiers = cli_module._derive_frontier_set(
        fixtures / "m6-hc-substantive.yaml",
        fixtures / "m6-hc-current.yaml",
        fixtures / "m6-hc-transcendence-dependencies.yaml",
    )
    assert len(frontiers) == 1
    assert frontiers[0].status.value == "WAITING_SCHEDULING"


def test_operator_status_missing_database_is_safe_and_empty(tmp_path, capsys):
    state_db = tmp_path / "missing-state.sqlite3"

    assert main(
        [
            "operator-status",
            "--state-db",
            str(state_db),
        ]
    ) == 0

    assert json.loads(capsys.readouterr().out) == {
        "actions": {},
        "live_fences": 0,
        "phases": {},
        "unresolved": 0,
    }


def test_external_registry_disables_detailed_operator_status(
    tmp_path,
    monkeypatch,
):
    registry = tmp_path / "private-operator.yaml"
    registry.write_text(
        """
projects:
- id: private-example
  name: Private Example
  visibility: private
  repositories: [secret-owner/private-example]
  capabilities: [read, analyze]
  assignment_scope: EXTERNAL_BOUNDED
  review_scope: STANDING
  family_id: private-family
  scheduling_state: SCHEDULABLE
""".lstrip(),
        encoding="utf-8",
    )
    _pin_external_registry(registry, monkeypatch)

    with pytest.raises(
        ValueError,
        match="detailed reports are disabled with an external project registry",
    ):
        main(
            [
                "operator-status",
                "--state-db",
                str(tmp_path / "state.sqlite3"),
                "--detailed",
            ]
        )



def test_portfolio_status_missing_database_is_safe_and_empty(tmp_path, capsys):
    state_db = tmp_path / "missing-portfolio.sqlite3"

    assert main(
        [
            "portfolio-status",
            "--state-db",
            str(state_db),
        ]
    ) == 0

    assert json.loads(capsys.readouterr().out) == {
        "baseline": None,
        "blocked": 0,
        "changed": 0,
        "frontiers": 0,
        "latest_snapshot_digest": None,
        "latest_snapshot_id": None,
        "observations": 0,
        "queued_total": 0,
        "ready": 0,
        "snapshots": 0,
    }


def test_portfolio_cycle_collects_then_schedules_changed_dependency(
    tmp_path,
    monkeypatch,
    capsys,
):
    from runner import portfolio as portfolio_module

    class FakeTransport:
        def __init__(self):
            self.heads = {
                ("thebrazenbeard/chat-communication-bus", "main"): "a" * 40,
                ("thebrazenbeard/vera-control-plane", "main"): "b" * 40,
            }

        def read_ref(self, repository, ref):
            return self.heads[(repository, ref)]

        def read_file(self, repository, path, ref):
            raise AssertionError("portfolio cycle is ref-read only")

        def create_branch(self, repository, branch, sha):
            raise AssertionError("portfolio cycle is read-only")

        def put_file(
            self,
            repository,
            path,
            branch,
            content,
            message,
            expected_blob_sha=None,
        ):
            raise AssertionError("portfolio cycle is read-only")

    transport = FakeTransport()
    monkeypatch.setattr(
        portfolio_module,
        "GitHubRestTransport",
        lambda token=None: transport,
    )
    state_db = tmp_path / "portfolio.sqlite3"

    assert main(
        [
            "portfolio-cycle",
            "--state-db",
            str(state_db),
        ]
    ) == 0
    baseline = json.loads(capsys.readouterr().out)
    assert baseline["baseline"] is True
    assert baseline["observations"] == 2
    assert baseline["frontiers"] == 0
    assert baseline["queued"] == 0

    transport.heads[
        ("thebrazenbeard/chat-communication-bus", "main")
    ] = "c" * 40

    assert main(
        [
            "portfolio-cycle",
            "--state-db",
            str(state_db),
        ]
    ) == 0
    changed = json.loads(capsys.readouterr().out)
    assert changed["baseline"] is False
    assert changed["changed"] == 1
    assert changed["frontiers"] == 1
    assert changed["ready"] == 1
    assert changed["queued"] == 1

    assert main(
        [
            "portfolio-status",
            "--state-db",
            str(state_db),
        ]
    ) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["snapshots"] == 2
    assert status["queued_total"] == 1



def test_external_portfolio_cycle_redacts_private_dependency_failure(
    tmp_path,
    monkeypatch,
):
    registry = tmp_path / "private-portfolio.yaml"
    registry.write_text(
        """
projects:
- id: private-provider
  name: Private Provider
  visibility: private
  repositories: [secret-owner/private-provider]
  capabilities: [read, analyze]
  assignment_scope: EXTERNAL_BOUNDED
  review_scope: STANDING
  family_id: private-provider-family
  scheduling_state: SCHEDULABLE
- id: private-consumer
  name: Private Consumer
  visibility: private
  repositories: [secret-owner/private-consumer]
  capabilities: [read, analyze]
  assignment_scope: EXTERNAL_BOUNDED
  review_scope: STANDING
  family_id: private-consumer-family
  scheduling_state: SCHEDULABLE
""".lstrip(),
        encoding="utf-8",
    )
    _pin_external_registry(registry, monkeypatch)
    private_dependencies = tmp_path / "do-not-leak-client-topology.yaml"

    with pytest.raises(
        ValueError,
        match="external portfolio cycle is unavailable or structurally invalid",
    ) as exc:
        main(
            [
                "portfolio-cycle",
                "--dependencies",
                str(private_dependencies),
                "--state-db",
                str(tmp_path / "state.sqlite3"),
            ]
        )

    message = str(exc.value)
    assert "do-not-leak" not in message
    assert "private-provider" not in message
    assert "private-consumer" not in message
    assert "secret-owner" not in message
