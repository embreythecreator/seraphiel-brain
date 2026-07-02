"""seraphiel absorb driver — ports absorb.sh to Python (stdlib + git only).

Orchestrates an absorb of an upstream Hermes tag into the rebranded fork:
read the current base from UPSTREAM_BASE.md, run the rebrand fidelity gate,
build BASE/THEIRS/OURS trees, 3-way merge onto `absorb/<tag>`, classify with
parity_report, and enforce every self-modifying-core guardrail. The merge is
dry-by-default: `absorb()` stops before committing; `commit()` finalizes only
when parity is READY; `abort()` is the one-step rollback. Nothing here ever
pushes or touches `main`.
"""
from __future__ import annotations

import re
import subprocess

from . import rebrand_tree, parity_report, divergence

# Only blobs allowed to retain an upstream token after the rebrand: legal
# carve-outs, the provenance/changelog docs, and the absorb harness itself
# (both its legacy script home and its packaged home).
ALLOWED_STRAY = ("achievements/LICENSE", "security-guidance/NOTICE",
                 "UPSTREAM_BASE.md", "CHANGELOG.md", "scripts/absorb/",
                 "seraphiel_cli/absorb/")
_PRERELEASE = re.compile(r"(rc|alpha|beta|pre)", re.I)


class AbsorbRefused(Exception):
    """A guardrail blocked the absorb (bad install, RC tag, drifted map, ...)."""


def _git(repo, *args, check=True):
    return subprocess.run(["git", "-C", repo, *args],
                          capture_output=True, text=True, check=check)


_STATE_KEYS = ("absorb.lastTag", "absorb.lastMerged", "absorb.oursHead",
               "absorb.verifyOk", "absorb.verifySummary")


def _cfg_get(repo: str, key: str) -> str | None:
    r = _git(repo, "config", "--local", "--get", key, check=False)
    return r.stdout.strip() or None


def _current_branch(repo: str) -> str:
    return _git(repo, "symbolic-ref", "--short", "-q", "HEAD", check=False).stdout.strip()


def clear_state(repo: str) -> None:
    """Drop every absorb.* stash — abort/commit both end the in-flight absorb."""
    for k in _STATE_KEYS:
        _git(repo, "config", "--local", "--unset-all", k, check=False)


def state(repo: str) -> dict | None:
    """The in-flight absorb, or None. Single source of truth for --continue/--verify/--status."""
    tag = _cfg_get(repo, "absorb.lastTag")
    if not tag:
        return None
    return {"tag": tag,
            "merged": _cfg_get(repo, "absorb.lastMerged"),
            "ours_head": _cfg_get(repo, "absorb.oursHead"),
            "verify_ok": _cfg_get(repo, "absorb.verifyOk") == "true",
            "verify_summary": _cfg_get(repo, "absorb.verifySummary") or ""}


def install_ok(repo: str) -> tuple[bool, str]:
    """Absorb only runs on a git/source checkout that has the `upstream` remote."""
    if _git(repo, "rev-parse", "--is-inside-work-tree", check=False).returncode != 0:
        return False, "absorb needs a git/source checkout (not a pip/docker install)."
    remotes = _git(repo, "remote").stdout.split()
    if "upstream" not in remotes:
        return False, "no `upstream` remote — add NousResearch/hermes-agent as `upstream`."
    return True, ""


def current_base(repo: str) -> str:
    """Read the recorded merge-base upstream tag from UPSTREAM_BASE.md."""
    text = (_git(repo, "show", "HEAD:UPSTREAM_BASE.md", check=False).stdout
            or open(f"{repo}/UPSTREAM_BASE.md").read())
    m = re.search(r"Upstream tag\s*\|\s*`?([vV][0-9.]+)`?", text)
    if not m:
        raise AbsorbRefused("could not read the current base tag from UPSTREAM_BASE.md")
    return m.group(1)


def gate(repo: str, base_ref: str) -> tuple[bool, str]:
    """Fidelity gate: T(base) must reproduce HEAD with 0 stray tokens outside carve-outs."""
    tree = rebrand_tree.build_rebranded_tree(base_ref, attribution=False)
    stray = _git(repo, "grep", "-ilI", "-e", "hermes", "-e", "nousresearch", tree,
                 check=False).stdout.splitlines()
    stray = [s.split(":", 1)[1] for s in stray if ":" in s
             and not any(a in s for a in ALLOWED_STRAY)]
    return (not stray), ("\n".join(stray) if stray else "")


def absorb(repo: str, tag: str, base_ref: str | None = None) -> dict:
    """Build the 3-way absorb merge onto `absorb/<tag>`. Dry: stops before committing."""
    if _PRERELEASE.search(tag):
        raise AbsorbRefused(f"refusing pre-release/RC tag {tag}")
    ok, msg = install_ok(repo)
    if not ok:
        raise AbsorbRefused(msg)
    st = state(repo)
    if st and st["tag"] != tag:
        raise AbsorbRefused(f"absorb {st['tag']} already in flight — "
                            f"--commit or --abort it before starting {tag}")
    base_ref = base_ref or current_base(repo)
    if _git(repo, "rev-parse", "-q", "--verify", f"refs/tags/{tag}", check=False).returncode != 0:
        _git(repo, "fetch", "-q", "upstream", "tag", tag)
    passed, detail = gate(repo, base_ref)
    if not passed:
        raise AbsorbRefused(f"fidelity gate failed (rebrand map drifted):\n{detail}")
    drift = divergence.check(repo, "HEAD")
    if drift:
        raise AbsorbRefused(
            "divergence manifest drifted on HEAD — update "
            "seraphiel_cli/absorb/divergence.py first:\n" + "\n".join(drift))

    base_tree = rebrand_tree.build_rebranded_tree(base_ref, attribution=False)
    theirs_tree = rebrand_tree.build_rebranded_tree(tag, attribution=True)
    ours_tree = _git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    base_c = _git(repo, "commit-tree", base_tree, "-m", f"T({base_ref})").stdout.strip()
    theirs_c = _git(repo, "commit-tree", theirs_tree, "-p", base_c, "-m", f"T({tag})").stdout.strip()
    ours_c = _git(repo, "commit-tree", ours_tree, "-p", base_c, "-m", "ours").stdout.strip()

    mt = _git(repo, "merge-tree", "--write-tree", f"--merge-base={base_c}", ours_c, theirs_c,
              check=False)
    merged = mt.stdout.splitlines()[0]
    branch = f"absorb/{tag}"
    if _git(repo, "rev-parse", "-q", "--verify", f"refs/heads/{branch}", check=False).returncode == 0:
        raise AbsorbRefused(f"branch {branch} already exists; --abort it first")
    _git(repo, "branch", branch, "HEAD")
    rep = parity_report.report(merged, theirs_tree, "HEAD", repo=repo)
    # stash refs so commit()/abort() can finish the job
    _git(repo, "config", "--local", "absorb.lastTag", tag)
    _git(repo, "config", "--local", "absorb.lastMerged", merged)
    _git(repo, "config", "--local", "absorb.oursHead",
         _git(repo, "rev-parse", "HEAD").stdout.strip())
    return {"branch": branch, "merged_tree": merged, "parity": rep, "ready": rep["ready"]}


def commit(repo: str, tag: str) -> str:
    """Finalize the stashed absorb merge — refuses unless parity is READY."""
    merged = _git(repo, "config", "--local", "--get", "absorb.lastMerged").stdout.strip()
    rep = parity_report.report(merged,
                               rebrand_tree.build_rebranded_tree(tag, attribution=True), "HEAD", repo=repo)
    if not rep["ready"]:
        raise AbsorbRefused("parity not READY (conflict markers or stray tokens remain)")
    commit_oid = _git(repo, "commit-tree", merged, "-p", "HEAD",
                      "-m", f"absorb: {tag} (full parity)").stdout.strip()
    _git(repo, "update-ref", f"refs/heads/absorb/{tag}", commit_oid)
    return commit_oid


def abort(repo: str, tag: str | None = None) -> None:
    """One-step rollback: delete the absorb branch, clear all stashed state."""
    st = state(repo)
    tag = tag or (st["tag"] if st else None)
    if not tag:
        raise AbsorbRefused("no absorb in flight and no tag given — nothing to abort")
    branch = f"absorb/{tag}"
    if _current_branch(repo) == branch:
        # step off the branch before deleting it; fall back to detached ours-head
        if _git(repo, "checkout", "-q", "-f", "main", check=False).returncode != 0:
            _git(repo, "checkout", "-q", "-f",
                 (st or {}).get("ours_head") or "HEAD")
    if _current_branch(repo) == branch:
        raise AbsorbRefused(f"could not step off {branch} — "
                            f"check out another branch, then re-run --abort")
    _git(repo, "branch", "-D", branch, check=False)
    _git(repo, "worktree", "prune", check=False)
    clear_state(repo)
