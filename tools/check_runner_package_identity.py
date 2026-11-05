"""Read-only, fail-closed identity probe for an *editable* Project Runner install.

This does not import `runner`, execute a worker, qualify a wheel, or attest
the OS/process. It only checks current interpreter metadata and import-finder
origin against a caller-supplied exact checkout root and expected version.
"""

from __future__ import annotations

import argparse
from importlib import metadata, util
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
from urllib.request import url2pathname


def _same_file(left: Path, right: Path) -> bool:
    try:
        # Do not accept a different lexical path merely because a symlink,
        # junction or alternate alias currently resolves to the same inode.
        if os.path.normcase(os.path.abspath(left)) != os.path.normcase(os.path.abspath(right)):
            return False
        return left.resolve(strict=True).samefile(right.resolve(strict=True))
    except Exception:
        return False


def _redirected(path: Path) -> bool:
    try:
        return any(
            part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction())
            for part in (path, *path.parents)
        )
    except Exception:
        return True


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
        # url2pathname performs the single permitted PEP 610 percent decode.
        # A prior unquote would turn %2570 into p in a *second* decode.
        return Path(url2pathname(parsed.path))
    except Exception:
        return None


def _portal_namespace_overlap(dist: object) -> bool | None:
    """True for collision, None for unverifiable RECORD, False for disjoint."""
    try:
        files = dist.files
        if not files:
            return None
        # Windows package/import paths are case insensitive.
        entries = [str(f).replace("\\", "/").casefold() for f in files]
        if any(
            not f or f.startswith("/") or re.match(r"^[a-z]:", f)
            or any(part in ("", ".", "..") for part in f.split("/"))
            for f in entries
        ):
            return None  # Noncanonical/escaping RECORD cannot prove disjointness.
        if any(f == "runner.py" or f.startswith("runner/") for f in entries):
            return True
        # Editable distribution RECORD tracks the .pth/finder, not necessarily
        # the source packages. Its apparent absence of runner files proves nil.
        raw = dist.read_text("direct_url.json")
        if raw:
            value = json.loads(raw)
            if type(value) is not dict or type(value.get("dir_info")) is not dict:
                return None
            if value["dir_info"].get("editable") is True:
                return None
        return False
    except Exception:
        return None


def inspect(
    expected_root: str | Path,
    expected_version: str,
    *,
    distribution_lookup=metadata.distribution,
    spec_lookup=util.find_spec,
    distributions_lookup=metadata.distributions,
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
    if any(_redirected(p) for p in (target, target / "runner",
                                   target / "runner" / "__init__.py")):
        failures.append("EXPECTED_CHECKOUT_REDIRECTED")
    if type(expected_version) is not str or not expected_version.strip():
        failures.append("INVALID_EXPECTED_VERSION")

    try:
        count = sum(
            type(d.metadata.get("Name")) is str
            and d.metadata.get("Name").lower().replace("_", "-").replace(".", "-")
                == "project-runner"
            for d in distributions_lookup()
        )
        if count != 1:
            failures.append("RUNNER_DISTRIBUTION_COUNT_UNVERIFIABLE")
    except Exception:
        failures.append("RUNNER_DISTRIBUTION_COUNT_UNVERIFIABLE")

    try:
        dist = distribution_lookup("project-runner")
    except metadata.PackageNotFoundError:
        failures.append("RUNNER_DISTRIBUTION_MISSING")
    except Exception:
        failures.append("RUNNER_DISTRIBUTION_UNREADABLE")
    else:
        try:
            name = dist.metadata.get("Name")
            if type(name) is not str or name.lower().replace("_", "-") != "project-runner":
                failures.append("RUNNER_DISTRIBUTION_NAME_MISMATCH")
            if dist.version != expected_version:
                failures.append("RUNNER_DISTRIBUTION_VERSION_MISMATCH")
            origin = _editable_source(dist)
            if origin is None:
                failures.append("RUNNER_EDITABLE_PROVENANCE_MISSING")
            elif _redirected(origin):
                failures.append("RUNNER_DISTRIBUTION_SOURCE_REDIRECTED")
            elif not _same_file(origin, target):
                failures.append("RUNNER_DISTRIBUTION_SOURCE_MISMATCH")
        except Exception:
            failures.append("RUNNER_DISTRIBUTION_UNREADABLE")

    try:
        found = spec_lookup("runner")
        file_path = getattr(found, "origin", None)
        if type(file_path) is not str or not _same_file(
            Path(file_path), target / "runner" / "__init__.py"
        ):
            failures.append("RUNNER_IMPORT_ORIGIN_MISMATCH")
        elif _redirected(Path(file_path)):
            failures.append("RUNNER_IMPORT_ORIGIN_REDIRECTED")
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
