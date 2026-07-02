"""Genuine-divergence manifest — the machine-checked contract for absorb merges.

Each entry pins one deliberate Seraphiel divergence from upstream Hermes so a
clean-but-wrong merge (upstream relocating code and the merge silently dropping
our change) can never reach READY. Checked against any TREE OID via git
plumbing — no checkout. Update this manifest ONLY when the operator
deliberately moves or retires a divergence; never weaken it to make a merge
pass (that is the exact failure mode it exists to catch).
"""
from __future__ import annotations

import subprocess

# (path, kind, needle) — kind is "exists" (blob must be present in the tree)
# or "contains" (utf-8 body must contain needle).
INVARIANTS: list[tuple[str, str, str | None]] = [
    ("gateway/platforms/whatsapp_common.py", "contains", "✶"),
    ("gateway/overlay/brain_settings.py", "exists", None),
    ("gateway/platforms/api_server.py", "contains", "_seraphiel_version"),
    ("agent/prompt_builder.py", "contains", "Embrey The Creator / The Voice"),
    ("seraphiel_cli/default_soul.py", "contains", "Embrey The Creator / The Voice"),
]


def _blob(repo: str, tree: str, path: str) -> bytes | None:
    r = subprocess.run(["git", "-C", repo, "cat-file", "-p", f"{tree}:{path}"],
                       capture_output=True)
    return r.stdout if r.returncode == 0 else None


def check(repo: str, tree: str) -> list[str]:
    """Return human-readable violations for `tree`; empty == all invariants hold."""
    violations = []
    for path, kind, needle in INVARIANTS:
        data = _blob(repo, tree, path)
        if data is None:
            violations.append(f"{path}: missing (genuine-divergence file gone)")
        elif kind == "contains" and needle not in data.decode("utf-8", "replace"):
            violations.append(f"{path}: no longer contains {needle!r}")
    return violations
