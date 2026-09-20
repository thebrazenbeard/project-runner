from __future__ import annotations

import json
from pathlib import Path

import pytest

from runner.discovery_census import (
    DiscoveryCensusBinding,
    load_binding,
    validate_discovery_census_bytes,
)


ROOT = Path(__file__).resolve().parents[2]
BINDING = ROOT / "registry" / "discovery_census_binding.json"
FIXTURE = ROOT / "tests" / "fixtures" / "discovery-portfolio-census-v1.json"


def test_exact_discovery_census_fixture_is_accepted():
    binding = load_binding(BINDING.read_bytes())
    payload = validate_discovery_census_bytes(
        FIXTURE.read_bytes(),
        binding=binding,
    )
    assert payload["counts"]["total"] == 57
    assert (
        payload["inventory_digests"]["all_names_sha256"]
        == "43dfda1fa3dd24dec39e2aa345d93ab192dbda777433feae384da632b3d008dd"
    )
    assert payload["status"] == "OBSERVED_INVENTORY_NOT_ARCHITECTURAL_AUTHORITY"


def test_binding_is_observational_not_runtime_registry():
    binding = load_binding(BINDING.read_bytes())
    assert binding.repository == "thebrazenbeard/discovery"
    assert binding.authority_ceiling == "OBSERVATIONAL_DRIFT_INPUT_NOT_RUNTIME_REGISTRY"


def test_mutated_census_bytes_fail_exact_blob_binding(tmp_path: Path):
    binding = load_binding(BINDING.read_bytes())
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["counts"]["total"] = 58
    raw = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
    with pytest.raises(ValueError, match="exact bound Git blob"):
        validate_discovery_census_bytes(raw, binding=binding)


def test_binding_rejects_authority_promotion():
    raw = json.loads(BINDING.read_text(encoding="utf-8"))
    raw["authority_ceiling"] = "RUNTIME_REGISTRY"
    with pytest.raises(ValueError, match="authority ceiling"):
        DiscoveryCensusBinding.from_mapping(raw)
