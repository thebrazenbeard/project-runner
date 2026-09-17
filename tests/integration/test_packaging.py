from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def test_editable_install_succeeds_without_network_build_isolation():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-e",
            str(ROOT),
            "--no-deps",
            "--no-build-isolation",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
