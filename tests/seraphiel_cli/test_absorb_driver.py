import subprocess
import pytest
from seraphiel_cli.absorb import driver


def _git(repo, *a):
    subprocess.run(["git", "-C", repo, *a], check=True, capture_output=True)


def test_install_ok_requires_upstream_remote(tmp_path):
    repo = tmp_path / "r"; repo.mkdir()
    _git(str(repo), "init", "-q")
    ok, msg = driver.install_ok(str(repo))
    assert ok is False and "upstream" in msg.lower()


def test_absorb_refuses_prerelease_tag(tmp_path):
    repo = tmp_path / "r"; repo.mkdir()
    _git(str(repo), "init", "-q")
    _git(str(repo), "remote", "add", "upstream", "https://example.invalid/x.git")
    with pytest.raises(driver.AbsorbRefused, match="pre-release"):
        driver.absorb(str(repo), "v2026.7.0-rc1")


import os
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_fidelity_gate_passes_on_current_tree():
    """T(base) must still reproduce HEAD modulo genuine divergence — 0 stray tokens."""
    ok, detail = driver.gate(REPO, driver.current_base(REPO))
    assert ok, f"rebrand map drifted; stray tokens:\n{detail}"


def test_cli_absorb_gate_runs(capsys):
    from seraphiel_cli import main as m
    ns = type("A", (), {"command": "absorb", "tag": None, "base": None,
                        "check": False, "gate": True, "commit": False, "abort": False})()
    rc = m.cmd_absorb(ns)
    assert rc in (0, 1)
    assert "gate" in capsys.readouterr().out.lower()
