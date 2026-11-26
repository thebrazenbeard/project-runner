from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


_RUNNER_DIR = Path(__file__).resolve().parent
_SOURCE_ROOT = _RUNNER_DIR.parent
# Packaged resources take precedence, including a broken/incomplete wheel.
# Only a matching source-project manifest permits the source layout.
def _schema_directory() -> Path:
    private = _RUNNER_DIR / "_schemas"
    if private.exists() or private.is_symlink():
        return private
    if any(_SOURCE_ROOT.glob("project_runner-*.dist-info")):
        return private
    try:
        with (_SOURCE_ROOT / "pyproject.toml").open("rb") as manifest:
            config = tomllib.load(manifest)
        if (
            config["project"]["name"] == "project-runner"
            and config["tool"]["setuptools"]["package-dir"]["runner._schemas"] == "schemas"
        ):
            return _SOURCE_ROOT / "schemas"
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError):
        pass
    return private


_SCHEMA_DIR = _schema_directory()
_SCHEMA_FILES = {
    "project": _SCHEMA_DIR / "project.schema.json",
    "worker": _SCHEMA_DIR / "worker.schema.json",
    "observation": _SCHEMA_DIR / "observation.schema.json",
    "dependency": _SCHEMA_DIR / "dependency.schema.json",
    "frontier": _SCHEMA_DIR / "frontier.schema.json",
    "work-unit": _SCHEMA_DIR / "work-unit.schema.json",
    "portfolio-corpus": _SCHEMA_DIR / "portfolio-corpus.schema.json",
    "portfolio-advancement": _SCHEMA_DIR / "portfolio-advancement.schema.json",
    "p0-project-manifest": _SCHEMA_DIR / "p0-project-manifest.schema.json",
}


def validate_document(schema_name: str, payload: Any) -> None:
    try:
        schema_path = _SCHEMA_FILES[schema_name]
    except KeyError as exc:
        raise ValueError(f"unknown schema: {schema_name}") from exc
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(payload)
