"""Guard the wheel's private JSON Schema resource layout.

Live wheel installation is qualified separately: source-tree tests cannot
by themselves prove an installed artifact includes these resources.
"""
from __future__ import annotations

import json
from pathlib import Path
import tomllib

from runner.schema import _SCHEMA_FILES


ROOT = Path(__file__).resolve().parents[2]


def test_schema_wheel_uses_runner_private_package() -> None:
    packaging = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    setuptools = packaging["tool"]["setuptools"]
    assert setuptools["packages"] == ["runner", "runner._schemas"]
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
