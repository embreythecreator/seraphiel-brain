---
name: absorb-upstream
description: "Use when the operator asks Seraphiel to absorb / pull in / rebase onto a new upstream Hermes release into its own core base. Drives `seraphiel absorb`, resolves conflicts preserving our genuine divergence, runs tests, and STOPS for human approval before committing. Maintainer / git-install only."
version: 1.0.0
author: Embrey The Creator
license: MIT
platforms: [linux, macos, windows]
metadata:
  seraphiel:
    tags: [absorb, upstream, hermes, maintainer, rebrand, merge, self-update]
    related_skills: [systematic-debugging, requesting-code-review, test-driven-development]
---

# Absorbing an upstream release into Seraphiel's core

You are updating your OWN core base. This is a maintainer operation on a git/source
checkout with an `upstream` remote. If `seraphiel absorb --check` reports a non-git or
no-upstream install, STOP and tell the operator this only works on the source repo
(pip/docker installs get core updates via `seraphiel update`, which is a different thing —
it pulls the latest *published* release, it does not absorb upstream).

## Loop

1. `seraphiel absorb --check` — if a newer tag exists, confirm with the operator before proceeding.
2. `seraphiel absorb <tag>` — produces branch `absorb/<tag>` + a parity summary. Dry by default;
   it never touches `main` and never commits on its own.
3. If the fidelity GATE fails: STOP. The rebrand map (`seraphiel_cli/absorb/rename_map.py`) has
   drifted; this needs a human — do not guess.
4. For each conflict file: read the base/ours/theirs versions. Distinguish OUR genuine divergence
   from the UPSTREAM change. Resolve by taking upstream's structure and RE-APPLYING our change where
   upstream relocated it (the canonical example: the v2026.6.19 WhatsApp reply prefix moved into
   `gateway/platforms/whatsapp_common.py` — upstream's new `WhatsAppBehaviorMixin` was taken and our
   `✶` glyph re-applied to `DEFAULT_REPLY_PREFIX`).
5. Preserve these genuine-divergence items — never revert them to upstream:
   - brand glyph `✶` (not `⚕`)
   - the Brain Settings overlay (`gateway/overlay/brain_settings.py`)
   - the versioned model name (`gateway/platforms/api_server.py`)
   - the attribution "created by Embrey The Creator"
6. Run the touched-core tests in isolation, e.g.
   `.venv/bin/python -m pytest tests/seraphiel_cli/test_absorb_driver.py -o addopts=""`
   (and the wider absorb suite: `test_absorb_parity.py`, `test_absorb_detect.py`).
7. PRESENT the resolved branch + parity summary to the operator and WAIT for approval.
8. On approval: `seraphiel absorb <tag> --commit`. NEVER `git push` unless explicitly told.

## Hard stops

- Gate failure, or any conflict needing core-semantic judgment beyond mechanical re-application → STOP, hand to the operator.
- Parity not READY (conflict markers / stray hermes tokens remain) → `--commit` will refuse; do not force.
- Never auto-push, never absorb a pre-release/RC tag.
- One-step rollback if anything looks wrong: `seraphiel absorb <tag> --abort`.
