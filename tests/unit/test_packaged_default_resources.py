from pathlib import Path
import runpy
import pytest
from runner._resources import resource_root

ROOT = Path(__file__).resolve().parents[2]
FILES = ("policy/scheduling.yaml", "registry/projects.yaml", "registry/workers.yaml",
         "topology/dependencies.yaml", "portfolio/advancement_wave.public.json", "portfolio/corpus.public.json")

def test_checkout_uses_own_public_defaults():
    assert resource_root() == ROOT
    assert all((resource_root() / f).is_file() for f in FILES)

@pytest.mark.parametrize("private_state", ["intact", "missing-file", "missing-directory"])
@pytest.mark.parametrize("manifest_kind", ["foreign", "matching"])
def test_installed_resources_refuse_sibling_fallback(tmp_path, private_state, manifest_kind):
    package = tmp_path / "runner"
    package.mkdir()
    module = package / "_resources.py"
    module.write_bytes((ROOT / "runner/_resources.py").read_bytes())
    (tmp_path / "project_runner-0.1.0.dist-info").mkdir()
    manifest = tmp_path / "pyproject.toml"
    manifest.write_bytes((ROOT / "pyproject.toml").read_bytes() if manifest_kind == "matching" else b'[project]\nname="other"\n')
    sibling = tmp_path / "policy/scheduling.yaml"
    sibling.parent.mkdir()
    sibling.write_text("foreign")
    private = package / "_data"
    if private_state != "missing-directory":
        private.mkdir()
    if private_state == "intact":
        (private / "policy").mkdir()
        (private / "policy/scheduling.yaml").write_text("owned")
    root = runpy.run_path(str(module))["resource_root"]()
    assert root == private
    if private_state == "intact":
        assert (root / "policy/scheduling.yaml").read_text() == "owned"
    else:
        with pytest.raises(FileNotFoundError):
            (root / "policy/scheduling.yaml").read_text()
