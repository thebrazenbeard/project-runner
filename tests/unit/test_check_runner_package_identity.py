"""Host-free provenance tests. No runner/portal package imports or installations."""

from __future__ import annotations

import importlib.util
from importlib import metadata
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout


TOOL = Path(__file__).resolve().parents[2] / "tools" / "check_runner_package_identity.py"
spec = importlib.util.spec_from_file_location("package_origin_guard_under_test", TOOL)
assert spec is not None and spec.loader is not None
guard = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = guard
spec.loader.exec_module(guard)


class FakeDist:
    def __init__(self, *, name="project-runner", version="0.1.0", source=None,
                 editable=True, files=(), source_url=None):
        self.version = version
        self.metadata = {"Name": name}
        self._source = source
        self._source_url = source_url
        self._editable = editable
        self.files = files

    def read_text(self, filename):
        assert filename == "direct_url.json"
        if self._source is None and self._source_url is None:
            return None
        return json.dumps({
            "url": self._source_url or self._source.as_uri(),
            "dir_info": {"editable": self._editable},
        })


class PackageOriginTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.runner = root / "project-runner"
        self.portal = root / "portal"
        for folder in (self.runner, self.portal):
            pkg = folder / "runner"
            pkg.mkdir(parents=True)
            (pkg / "__init__.py").write_text("# synthetic package, not imported\n")

    def probe(self, dist_source, import_source, *, version="0.1.0",
              editable=True, portal_dist=None, source_url=None,
              runner_duplicates=1):
        runner_dist = FakeDist(source=dist_source, version=version,
                               editable=editable, source_url=source_url)

        def distributions(name):
            if name == "project-runner":
                return runner_dist
            if name == "portal-coordinator" and portal_dist is not None:
                return portal_dist
            raise metadata.PackageNotFoundError(name)

        def find_spec(name):
            self.assertEqual(name, "runner")
            return SimpleNamespace(origin=str(import_source / "runner" / "__init__.py"))

        return guard.inspect(self.runner, "0.1.0", distribution_lookup=distributions,
                             spec_lookup=find_spec,
                             distributions_lookup=lambda: [runner_dist] * runner_duplicates)

    def test_standalone_runner_editable_install_can_be_identified(self):
        result = self.probe(self.runner, self.runner)
        self.assertEqual(result["status"], "MATCHED_EDITABLE_SOURCE_ONLY")
        self.assertFalse(result["qualified_for_release"])
        self.assertEqual(result["failures"], [])

    def test_portal_3_14_collision_fails_on_both_provenance_fields(self):
        result = self.probe(self.portal, self.portal)
        self.assertEqual(result["status"], "HOLD_UNQUALIFIED")
        self.assertEqual(set(result["failures"]), {
            "RUNNER_DISTRIBUTION_SOURCE_MISMATCH", "RUNNER_IMPORT_ORIGIN_MISMATCH"
        })

    def test_metadata_correct_but_import_shadowed_by_portal_is_denied(self):
        result = self.probe(self.runner, self.portal)
        self.assertIn("RUNNER_IMPORT_ORIGIN_MISMATCH", result["failures"])

    def test_version_mismatch_fails_even_with_correct_source(self):
        result = self.probe(self.runner, self.runner, version="0.2.0")
        self.assertIn("RUNNER_DISTRIBUTION_VERSION_MISMATCH", result["failures"])

    def test_wheel_without_editable_binding_remains_unknown(self):
        result = self.probe(None, self.runner)
        self.assertIn("RUNNER_EDITABLE_PROVENANCE_MISSING", result["failures"])

    def test_noneditable_source_is_rejected(self):
        result = self.probe(self.runner, self.runner, editable=False)
        self.assertIn("RUNNER_EDITABLE_PROVENANCE_MISSING", result["failures"])

    def test_portal_distribution_must_not_package_runner(self):
        portal = FakeDist(name="portal-coordinator",
                          files=["portal/__init__.py", "runner/__init__.py"])
        result = self.probe(self.runner, self.runner, portal_dist=portal)
        self.assertIn("PORTAL_OWNS_RUNNER_NAMESPACE", result["failures"])

    def test_portal_distribution_with_disjoint_record_is_acceptable(self):
        portal = FakeDist(name="portal-coordinator",
                          files=["portal/__init__.py", "portal/_runner/__init__.py"])
        result = self.probe(self.runner, self.runner, portal_dist=portal)
        self.assertEqual(result["status"], "MATCHED_EDITABLE_SOURCE_ONLY")

    def test_portal_record_unavailable_is_not_assumed_disjoint(self):
        portal = FakeDist(name="portal-coordinator", files=None)
        result = self.probe(self.runner, self.runner, portal_dist=portal)
        self.assertIn("PORTAL_PACKAGE_RECORD_UNVERIFIABLE", result["failures"])

    def test_empty_portal_editable_record_is_not_evidence_of_disjointness(self):
        portal = FakeDist(name="portal-coordinator", files=[])
        result = self.probe(self.runner, self.runner, portal_dist=portal)
        self.assertIn("PORTAL_PACKAGE_RECORD_UNVERIFIABLE", result["failures"])

    def test_foreign_top_level_runner_py_is_a_namespace_collision(self):
        portal = FakeDist(name="portal-coordinator", files=["portal/__init__.py", "runner.py"])
        result = self.probe(self.runner, self.runner, portal_dist=portal)
        self.assertIn("PORTAL_OWNS_RUNNER_NAMESPACE", result["failures"])

    def test_windows_casefolded_runner_namespace_is_collision(self):
        portal = FakeDist(name="portal-coordinator",
                          files=["portal/__init__.py", "Runner/__init__.py"])
        result = self.probe(self.runner, self.runner, portal_dist=portal)
        self.assertIn("PORTAL_OWNS_RUNNER_NAMESPACE", result["failures"])

    def test_portal_editable_record_does_not_attest_source_ownership(self):
        portal = FakeDist(name="portal-coordinator", source=self.portal,
                          files=["__editable__.portal_coordinator.pth",
                                 "portal_coordinator-0.2.dist-info/METADATA"])
        result = self.probe(self.runner, self.runner, portal_dist=portal)
        self.assertIn("PORTAL_PACKAGE_RECORD_UNVERIFIABLE", result["failures"])

    def test_portal_legacy_import_hooks_are_unverifiable_without_direct_url(self):
        for hook in ("__editable__.portal_coordinator.pth",
                     "legacy-portal.egg-link",
                     "__editable___portal_coordinator_finder.py",
                     "sitecustomize.py", "usercustomize.py"):
            with self.subTest(hook=hook):
                portal = FakeDist(name="portal-coordinator",
                                  files=[hook, "portal_coordinator-0.2.dist-info/METADATA"])
                result = self.probe(self.runner, self.runner, portal_dist=portal)
                self.assertIn("PORTAL_PACKAGE_RECORD_UNVERIFIABLE", result["failures"])

    def test_noncanonical_portal_record_paths_do_not_prove_disjointness(self):
        for unusual in ("./runner/__init__.py", "../runner/__init__.py",
                        "/runner/__init__.py", "C:/runner/__init__.py",
                        "portal//__init__.py"):
            with self.subTest(unusual=unusual):
                portal = FakeDist(name="portal-coordinator",
                                  files=["portal/__init__.py", unusual])
                result = self.probe(self.runner, self.runner, portal_dist=portal)
                self.assertIn("PORTAL_PACKAGE_RECORD_UNVERIFIABLE", result["failures"])

    def test_double_encoded_source_url_does_not_get_second_decode(self):
        encoded = self.runner.as_uri().replace("project-runner", "%2570roject-runner")
        result = self.probe(self.runner, self.runner, source_url=encoded)
        self.assertIn("RUNNER_DISTRIBUTION_SOURCE_MISMATCH", result["failures"])

    def test_duplicate_runner_metadata_is_unqualified(self):
        result = self.probe(self.runner, self.runner, runner_duplicates=2)
        self.assertIn("RUNNER_DISTRIBUTION_COUNT_UNVERIFIABLE", result["failures"])

    def test_runner_metadata_getter_error_yields_hold_envelope(self):
        class BadDist(FakeDist):
            @property
            def metadata(self):
                raise RuntimeError("synthetic metadata error")
            @metadata.setter
            def metadata(self, _):
                pass
        bad = BadDist(source=self.runner)
        result = guard.inspect(self.runner, "0.1.0",
                               distribution_lookup=lambda _: bad,
                               spec_lookup=lambda _: SimpleNamespace(
                                   origin=str(self.runner / "runner" / "__init__.py")),
                               distributions_lookup=lambda: [bad])
        self.assertEqual(result["status"], "HOLD_UNQUALIFIED")
        self.assertIn("RUNNER_DISTRIBUTION_UNREADABLE", result["failures"])
        self.assertNotIn("synthetic metadata error", json.dumps(result))

    def test_symlinked_runner_package_is_not_considered_custodied(self):
        redirected = self.runner / "runner"
        (redirected / "__init__.py").unlink()
        redirected.rmdir()
        try:
            redirected.symlink_to(self.portal / "runner", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable")
        result = self.probe(self.runner, self.portal)
        self.assertIn("EXPECTED_CHECKOUT_REDIRECTED", result["failures"])
        self.assertEqual(result["status"], "HOLD_UNQUALIFIED")

    def test_missing_runner_dist_and_finder_fail_closed(self):
        def absent(_):
            raise metadata.PackageNotFoundError()
        result = guard.inspect(self.runner, "0.1.0",
                               distribution_lookup=absent,
                               spec_lookup=lambda _: None,
                               distributions_lookup=lambda: [])
        self.assertEqual(result["status"], "HOLD_UNQUALIFIED")
        self.assertIn("RUNNER_DISTRIBUTION_MISSING", result["failures"])
        self.assertIn("RUNNER_IMPORT_ORIGIN_MISMATCH", result["failures"])

    def test_cli_emits_no_checkout_path_in_receipt(self):
        with patch.object(guard, "inspect", return_value={
            "status": "HOLD_UNQUALIFIED", "qualified_for_release": False,
            "failures": ["RUNNER_IMPORT_ORIGIN_MISMATCH"],
        }):
            output = io.StringIO()
            with redirect_stdout(output):
                result = guard.main(["--expected-root", str(self.runner),
                                     "--expected-version", "0.1.0"])
        self.assertEqual(result, 2)
        self.assertNotIn(str(self.runner), output.getvalue())
        self.assertIn("HOLD_UNQUALIFIED", output.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
