"""Post-merge verification battery for `seraphiel absorb`.

Materializes the merged tree in a throwaway git worktree (never the operator's
working tree), byte-compiles the changed .py files, and runs the targeted
hermetic test set with the merged code first on sys.path. The battery gates
`--commit` (see driver.commit); `--skip-verify` is the explicit human escape.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

# The hermetic set that ran green during the v2026.6.19 absorb, plus the absorb
# suite itself. Paths missing from the merged tree are skipped (synthetic test
# repos, upstream test moves) — the summary says how many actually ran.
TARGETED_TESTS = [
    "tests/seraphiel_cli/test_absorb_driver.py",
    "tests/seraphiel_cli/test_absorb_detect.py",
    "tests/seraphiel_cli/test_absorb_parity.py",
    "tests/seraphiel_cli/test_absorb_divergence.py",
    "tests/seraphiel_cli/test_absorb_verify.py",
    "tests/seraphiel_cli/test_banner.py",
    "tests/seraphiel_cli/test_build_info.py",
    "tests/seraphiel_cli/test_config.py",
    "tests/gateway/test_api_server.py",
    "tests/gateway/test_brain_settings_overlay.py",
    "tests/gateway/test_status.py",
]


def _git(repo, *args, check=True):
    return subprocess.run(["git", "-C", repo, *args],
                          capture_output=True, text=True, check=check)


def changed_py(repo: str, merged: str, head: str = "HEAD") -> list[str]:
    out = _git(repo, "diff", "--name-only", head, merged).stdout.splitlines()
    return [f for f in out if f.endswith(".py")]


def run(repo: str, merged: str, head: str = "HEAD") -> dict:
    """Run the battery against a merged TREE oid. Worktree is always removed."""
    commit = _git(repo, "commit-tree", merged, "-m",
                  "absorb-verify (throwaway)").stdout.strip()
    wt = os.path.join(tempfile.mkdtemp(prefix="absorb-verify-"), "tree")
    _git(repo, "worktree", "add", "-q", "--detach", wt, commit)
    try:
        py = [f for f in changed_py(repo, merged, head)
              if os.path.exists(os.path.join(wt, f))]
        compile_ok, compile_errors = True, ""
        if py:
            r = subprocess.run([sys.executable, "-m", "compileall", "-q", *py],
                               cwd=wt, capture_output=True, text=True)
            compile_ok = r.returncode == 0
            compile_errors = (r.stdout + r.stderr).strip()

        targets = [t for t in TARGETED_TESTS
                   if os.path.exists(os.path.join(wt, t))]
        tests_ok, tests_summary = True, "no targeted tests present in merged tree"
        if targets:
            env = dict(os.environ)
            env["PYTHONPATH"] = wt + os.pathsep + env.get("PYTHONPATH", "")
            r = subprocess.run([sys.executable, "-m", "pytest", "-q",
                                "-p", "no:cacheprovider", *targets],
                               cwd=wt, capture_output=True, text=True, env=env)
            tests_ok = r.returncode == 0
            lines = [l for l in r.stdout.strip().splitlines() if l.strip()]
            tests_summary = (f"{len(targets)} target files · "
                             + (lines[-1] if lines else f"exit {r.returncode}"))
        return {"compile_ok": compile_ok, "compile_errors": compile_errors,
                "tests_ok": tests_ok, "tests_summary": tests_summary,
                "ok": compile_ok and tests_ok}
    finally:
        _git(repo, "worktree", "remove", "--force", wt, check=False)
        _git(repo, "worktree", "prune", check=False)
