"""Read-only, fail-closed identity probe for an *editable* Project Runner install.

This does not import `runner`, execute a worker, qualify a wheel, or attest
the OS/process. It only checks current interpreter metadata and import-finder
origin against a caller-supplied exact checkout root and expected version.
"""

from __future__ import annotations

import argparse
from importlib import metadata, util
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname


def _same_file(left: Path, right: Path) -> bool:
    try:
        return left.resolve(strict=True).samefile(right.resolve(strict=True))
    except (OSError, RuntimeError, ValueError):
        return False


def _editable_source(dist: object) -> Path | None:
    try:
        raw = dist.read_text("direct_url.json")
        value = json.loads(raw) if raw else None
        if type(value) is not dict or value.get("dir_info", {}).get("editable") is not True:
            return None
        parsed = urlsplit(value.get("url", ""))
        if (parsed.scheme != "file" or parsed.netloc not in ("", "localhost")
                or parsed.query or parsed.fragment or not parsed.path):
            return None
        return Path(url2pathname(unquote(parsed.path)))
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def _portal_namespace_overlap(dist: object) -> bool | None:
    """True for collision, None for unverifiable RECORD, False for disjoint."""
    try:
        files = dist.files
        if not files:
            return None
        entries = [str(f).replace("\\", "/") for f in files]
        return any(f == "runner.py" or f.startswith("runner/") for f in entries)
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def inspect(
    expected_root: str | Path,
    expected_version: str,
    *,
    distribution_lookup=metadata.distribution,
    spec_lookup=util.find_spec,
) -> dict[str, object]:
    """No package import, filesystem write, network request, or subprocess.

    Current interpreter discovery is an observational diagnostic only; a
    malicious environment or import finder can lie. A wheel installation
    without editable provenance is UNKNOWN and deliberately fails this probe.
    """
    failures: list[str] = []
    target = Path(expected_root)
    if not target.is_dir() or not (target / "runner" / "__init__.py").is_file():
        failures.append("EXPECTED_CHECKOUT_UNAVAILABLE")
    if type(expected_version) is not str or not expected_version.strip():
        failures.append("INVALID_EXPECTED_VERSION")

    try:
        dist = distribution_lookup("project-runner")
    except metadata.PackageNotFoundError:
        failures.append("RUNNER_DISTRIBUTION_MISSING")
    except Exception:
        failures.append("RUNNER_DISTRIBUTION_UNREADABLE")
    else:
        name = dist.metadata.get("Name")
        if type(name) is not str or name.lower().replace("_", "-") != "project-runner":
            failures.append("RUNNER_DISTRIBUTION_NAME_MISMATCH")
        if dist.version != expected_version:
            failures.append("RUNNER_DISTRIBUTION_VERSION_MISMATCH")
        origin = _editable_source(dist)
        if origin is None:
            failures.append("RUNNER_EDITABLE_PROVENANCE_MISSING")
        elif not _same_file(origin, target):
            failures.append("RUNNER_DISTRIBUTION_SOURCE_MISMATCH")

    try:
        found = spec_lookup("runner")
        file_path = getattr(found, "origin", None)
        if type(file_path) is not str or not _same_file(
            Path(file_path), target / "runner" / "__init__.py"
        ):
            failures.append("RUNNER_IMPORT_ORIGIN_MISMATCH")
    except Exception:
        failures.append("RUNNER_IMPORT_ORIGIN_UNREADABLE")

    try:
        portal = distribution_lookup("portal-coordinator")
    except metadata.PackageNotFoundError:
        pass
    except Exception:
        failures.append("PORTAL_DISTRIBUTION_UNREADABLE")
    else:
        overlap = _portal_namespace_overlap(portal)
        if overlap is True:
            failures.append("PORTAL_OWNS_RUNNER_NAMESPACE")
        elif overlap is None:
            failures.append("PORTAL_PACKAGE_RECORD_UNVERIFIABLE")

    return {
        "status": "MATCHED_EDITABLE_SOURCE_ONLY" if not failures else "HOLD_UNQUALIFIED",
        "qualified_for_release": False,
        "expected_distribution": "project-runner",
        "expected_import": "runner",
        "failures": sorted(set(failures)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-root", required=True)
    parser.add_argument("--expected-version", required=True)
    args = parser.parse_args(argv)
    receipt = inspect(args.expected_root, args.expected_version)
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["status"] == "MATCHED_EDITABLE_SOURCE_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
