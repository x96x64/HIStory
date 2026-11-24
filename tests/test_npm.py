"""The npm wrapper starts the Python package and reports the same version."""

import shutil
import subprocess
from pathlib import Path

import pytest

from hist import __version__

ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def test_wrapper_prints_version():
    subprocess.run(["node", str(ROOT / "npm" / "scripts" / "prepack.js")], check=True)
    result = subprocess.run(
        ["node", str(ROOT / "npm" / "bin" / "hist.js"), "--version"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"hist {__version__}"


def test_wrapper_forwards_exit_code():
    result = subprocess.run(
        ["node", str(ROOT / "npm" / "bin" / "hist.js"), "--no-such-option"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 2


def test_wrapper_reports_missing_python(monkeypatch):
    monkeypatch.setenv("HIST_PYTHON", "no-such-python-binary")
    result = subprocess.run(
        ["node", str(ROOT / "npm" / "bin" / "hist.js"), "--version"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 2
    assert "HIST_PYTHON" in result.stderr


def test_versions_agree():
    result = subprocess.run(
        [shutil.which("python3") or "python3", str(ROOT / "scripts" / "check_versions.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
