from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[2]


def test_setuptools_packages_only_runner_owned_namespaces():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    packaging = config["tool"]["setuptools"]
    assert packaging["packages"] == ["runner", "runner._schemas"]
    assert packaging["package-dir"]["runner._schemas"] == "schemas"
    assert packaging["package-data"]["runner._schemas"] == ["*.json"]
    assert "schemas" not in packaging["packages"]
