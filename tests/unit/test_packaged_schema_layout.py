"""Guard the wheel's private JSON Schema resource layout.

Live wheel installation is qualified separately: source-tree tests cannot
by themselves prove an installed artifact includes these resources.
"""
from __future__ import annotations

import json
from pathlib import Path
import tomllib
import pytest
import runpy

from runner.schema import _SCHEMA_FILES


ROOT = Path(__file__).resolve().parents[2]


def test_schema_wheel_uses_runner_private_package() -> None:
    packaging = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    setuptools = packaging["tool"]["setuptools"]
    assert setuptools["packages"] == ["runner", "runner._schemas", "runner._data.policy", "runner._data.registry", "runner._data.topology", "runner._data.portfolio"]
    assert setuptools["package-dir"]["runner._schemas"] == "schemas"
    assert setuptools["package-data"]["runner._schemas"] == ["*.json"]
    assert "schemas" not in setuptools["packages"]


def test_all_schema_resources_are_named_and_parseable() -> None:
    canonical = sorted(path.name for path in (ROOT / "schemas").glob("*.json"))
    resolved = sorted(path.name for path in _SCHEMA_FILES.values())
    assert len(canonical) == len(_SCHEMA_FILES) == 9
    assert resolved == canonical
    for path in _SCHEMA_FILES.values():
        assert path.is_file(), path.name
        parsed = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(parsed, dict)


def test_missing_wheel_resource_cannot_use_foreign_top_level_schemas(tmp_path: Path) -> None:
    """A broken wheel must not silently accept unrelated schemas in site-packages."""
    import runpy
    site_packages = tmp_path / "site-packages"
    candidate = site_packages / "runner"
    candidate.mkdir(parents=True)
    foreign = site_packages / "schemas"
    foreign.mkdir()
    (foreign / "worker.schema.json").write_text(
        '{"type":"object"}', encoding="utf-8"
    )
    source = ROOT / "runner" / "schema.py"
    target = candidate / "schema.py"
    target.write_bytes(source.read_bytes())
    context = runpy.run_path(str(target))
    assert context["_SCHEMA_FILES"]["worker"] == (
        candidate / "_schemas" / "worker.schema.json"
    )
    import pytest
    with pytest.raises(FileNotFoundError):
        context["validate_document"]("worker", {})

@pytest.mark.parametrize("private_state", ["intact", "missing-file", "missing-directory"])
@pytest.mark.parametrize("marker", ["foreign", "runner-like"])
def test_installed_schema_never_uses_sibling_project(tmp_path, private_state, marker):
    site = tmp_path / "site-packages"
    candidate = site / "runner"
    candidate.mkdir(parents=True)
    target = candidate / "schema.py"
    target.write_bytes((ROOT / "runner" / "schema.py").read_bytes())
    (candidate / "__init__.py").touch()
    foreign = site / "schemas"
    foreign.mkdir()
    (foreign / "worker.schema.json").write_text('{"type":"object"}', encoding="utf8")
    # The latter marker even has the distribution's real source manifest;
    # installed wheel metadata still makes this an installed layout.
    project = site / "pyproject.toml"
    project.write_text('[project]\nname="unrelated"\n', encoding="utf8") if marker == "foreign" else project.write_bytes((ROOT / "pyproject.toml").read_bytes())
    dist = site / "project_runner-0.1.0.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text("Name: project-runner\nVersion: 0.1.0\n", encoding="utf8")
    private = candidate / "_schemas"
    expected = private / "worker.schema.json"
    if private_state != "missing-directory":
        private.mkdir()
    if private_state == "intact":
        expected.write_text('{"type":"object","required":["owned"]}', encoding="utf8")
    context = runpy.run_path(str(target))
    assert context["_SCHEMA_FILES"]["worker"] == expected
    if private_state == "intact":
        from jsonschema.exceptions import ValidationError
        with pytest.raises(ValidationError):
            context["validate_document"]("worker", {})
        context["validate_document"]("worker", {"owned": True})
    else:
        with pytest.raises(FileNotFoundError):
            context["validate_document"]("worker", {})

def test_unrelated_source_marker_is_not_runner_checkout(tmp_path):
    candidate = tmp_path / "runner"
    candidate.mkdir()
    target = candidate / "schema.py"
    target.write_bytes((ROOT / "runner" / "schema.py").read_bytes())
    (tmp_path / "pyproject.toml").write_text('[project]\nname="unrelated"\n', encoding="utf8")
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas" / "worker.schema.json").write_text('{"type":"object"}', encoding="utf8")
    context = runpy.run_path(str(target))
    assert context["_SCHEMA_FILES"]["worker"] == candidate / "_schemas" / "worker.schema.json"
    with pytest.raises(FileNotFoundError):
        context["validate_document"]("worker", {})
