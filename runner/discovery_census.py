from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any


_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class DiscoveryCensusBinding:
    repository: str
    subject: str
    path: str
    git_blob_sha1: str
    total_count: int
    all_names_sha256: str
    authority_ceiling: str

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "DiscoveryCensusBinding":
        expected = {
            "repository",
            "subject",
            "path",
            "git_blob_sha1",
            "total_count",
            "all_names_sha256",
            "authority_ceiling",
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise ValueError("Discovery census binding fields do not match exact schema")
        out = cls(**value)
        out.validate()
        return out

    def validate(self) -> None:
        if self.repository != "thebrazenbeard/discovery":
            raise ValueError("Discovery census repository mismatch")
        if not isinstance(self.subject, str) or "@" not in self.subject:
            raise ValueError("Discovery census subject must be ref@commit")
        ref, sha = self.subject.rsplit("@", 1)
        if not ref or not _SHA1.fullmatch(sha):
            raise ValueError("Discovery census subject must end in exact commit SHA")
        if self.path != "portfolio/PORTFOLIO_CENSUS_V1.json":
            raise ValueError("Discovery census path mismatch")
        if not _SHA1.fullmatch(self.git_blob_sha1):
            raise ValueError("Discovery census Git blob SHA-1 invalid")
        if type(self.total_count) is not int or self.total_count < 1:
            raise ValueError("Discovery census total_count invalid")
        if not _SHA256.fullmatch(self.all_names_sha256):
            raise ValueError("Discovery census all-name digest invalid")
        if self.authority_ceiling != "OBSERVATIONAL_DRIFT_INPUT_NOT_RUNTIME_REGISTRY":
            raise ValueError("Discovery census authority ceiling mismatch")


def _git_blob_sha1(raw: bytes) -> str:
    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw).hexdigest()


def validate_discovery_census_bytes(
    raw: bytes,
    *,
    binding: DiscoveryCensusBinding,
) -> dict[str, Any]:
    binding.validate()
    if _git_blob_sha1(raw) != binding.git_blob_sha1:
        raise ValueError("Discovery census bytes do not match exact bound Git blob")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ValueError("Discovery census is not valid UTF-8 JSON") from exc

    if payload.get("schema") != "DISCOVERY_PORTFOLIO_CENSUS_V1":
        raise ValueError("Discovery census schema mismatch")
    if payload.get("status") != "OBSERVED_INVENTORY_NOT_ARCHITECTURAL_AUTHORITY":
        raise ValueError("Discovery census authority status mismatch")

    counts = payload.get("counts")
    digests = payload.get("inventory_digests")
    if not isinstance(counts, dict) or counts.get("total") != binding.total_count:
        raise ValueError("Discovery census repository count mismatch")
    if (
        not isinstance(digests, dict)
        or digests.get("all_names_sha256") != binding.all_names_sha256
    ):
        raise ValueError("Discovery census all-name digest mismatch")

    if not payload.get("privacy_rule"):
        raise ValueError("Discovery census privacy rule missing")
    if not payload.get("refresh_rule"):
        raise ValueError("Discovery census refresh rule missing")

    return payload


def load_binding(raw: bytes) -> DiscoveryCensusBinding:
    try:
        value = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ValueError("Discovery census binding is not valid UTF-8 JSON") from exc
    return DiscoveryCensusBinding.from_mapping(value)


__all__ = [
    "DiscoveryCensusBinding",
    "load_binding",
    "validate_discovery_census_bytes",
]
