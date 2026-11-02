from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


_RUNNER_DIR = Path(__file__).resolve().parent
_SOURCE_ROOT = _RUNNER_DIR.parent
# Source checkouts use the canonical schema files. Installed wheels must use
# their private resources and fail closed when those resources are absent.
_SCHEMA_DIR = (
    _SOURCE_ROOT / "schemas"
    if (_SOURCE_ROOT / "pyproject.toml").is_file()
    and (_SOURCE_ROOT / "schemas").is_dir()
    else _RUNNER_DIR / "_schemas"
)
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
