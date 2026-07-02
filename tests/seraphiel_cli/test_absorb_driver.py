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


def _mkrepo(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(str(repo), "init", "-q", "-b", "main")
    _git(str(repo), "config", "user.email", "t@t")
    _git(str(repo), "config", "user.name", "t")
    (repo / "a.txt").write_text("hello\n")
    _git(str(repo), "add", "-A")
    _git(str(repo), "commit", "-q", "-m", "init")
    return str(repo)


def test_state_none_when_not_in_flight(tmp_path):
    repo = _mkrepo(tmp_path)
    assert driver.state(repo) is None


def test_state_roundtrip_and_clear(tmp_path):
    repo = _mkrepo(tmp_path)
    _git(repo, "config", "--local", "absorb.lastTag", "v2026.7.0")
    _git(repo, "config", "--local", "absorb.lastMerged", "deadbeef")
    _git(repo, "config", "--local", "absorb.oursHead", "cafebabe")
    _git(repo, "config", "--local", "absorb.verifyOk", "true")
    st = driver.state(repo)
    assert st == {"tag": "v2026.7.0", "merged": "deadbeef",
                  "ours_head": "cafebabe", "verify_ok": True,
                  "verify_summary": ""}
    driver.clear_state(repo)
    assert driver.state(repo) is None


def test_abort_clears_state_and_branch(tmp_path):
    repo = _mkrepo(tmp_path)
    _git(repo, "branch", "absorb/v2026.7.0")
    _git(repo, "config", "--local", "absorb.lastTag", "v2026.7.0")
    _git(repo, "config", "--local", "absorb.lastMerged", "deadbeef")
    driver.abort(repo)                      # tag resolved from state
    assert driver.state(repo) is None
    r = subprocess.run(["git", "-C", repo, "rev-parse", "-q", "--verify",
                        "refs/heads/absorb/v2026.7.0"], capture_output=True)
    assert r.returncode != 0


def test_abort_refuses_without_state_or_tag(tmp_path):
    repo = _mkrepo(tmp_path)
    with pytest.raises(driver.AbsorbRefused, match="no absorb in flight"):
        driver.abort(repo)


def test_absorb_refuses_when_head_divergence_drifted(tmp_path, monkeypatch):
    repo = _mkrepo(tmp_path)
    _git(repo, "remote", "add", "upstream", "https://example.invalid/x.git")
    (tmp_path / "r" / "UPSTREAM_BASE.md").write_text("| Upstream tag | `v2026.6.19` |\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base doc")
    _git(repo, "tag", "v2026.7.0")
    monkeypatch.setattr(driver, "gate", lambda r, b: (True, ""))
    monkeypatch.setattr(driver.rebrand_tree, "build_rebranded_tree",
                        lambda ref, attribution=True: "unused")
    with pytest.raises(driver.AbsorbRefused, match="divergence manifest drifted"):
        driver.absorb(repo, "v2026.7.0")
