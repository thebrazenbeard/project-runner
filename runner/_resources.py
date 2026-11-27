"""Resolve public-safe bundled defaults without sibling-package fallback."""
from pathlib import Path
import tomllib


def resource_root() -> Path:
    package = Path(__file__).resolve().parent
    source = package.parent
    private = package / "_data"
    if private.exists() or private.is_symlink():
        return private
    if any(source.glob("project_runner-*.dist-info")):
        return private
    try:
        with (source / "pyproject.toml").open("rb") as manifest:
            config = tomllib.load(manifest)
        mapping = config["tool"]["setuptools"]["package-dir"]
        if (
            config["project"]["name"] == "project-runner"
            and all(mapping["runner._data." + name] == name
                    for name in ("policy", "registry", "topology", "portfolio"))
        ):
            return source
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError):
        pass
    return private
