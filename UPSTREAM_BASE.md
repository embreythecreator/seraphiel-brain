# Upstream base

This is a **white fork** of Hermes Agent (NousResearch/hermes-agent), imported as a
squashed snapshot — there is **no shared git history with upstream**, so `git merge`
does not work. Absorb upstream changes as a **diff port** (see below).

| | value |
|---|---|
| Current tree corresponds to | **Hermes v0.16.0** |
| Upstream tag | `v2026.6.5` |
| Upstream commit | `3c231eb39` |
| Our version (independent line) | `0.16.0` (pyproject.toml — source of truth) |

`upstream` remote is configured locally (`NousResearch/hermes-agent`), pushed nowhere,
invisible to public clones of this repo.

## Make our own update
Commit to `main`, bump the patch in `pyproject.toml` (`0.16.0` → `0.16.1`). Done.

## Absorb a Hermes update (diff port)
```sh
git fetch upstream --tags
# diff window = our current base .. the new upstream tag
git diff v2026.6.5..v2026.6.19 > /tmp/hermes.patch     # e.g. absorbing 0.17.0
git apply --3way /tmp/hermes.patch                      # or: git apply --reject
# resolve rebrand collisions in new/changed files (Hermes/hermes -> Seraphiel/seraphiel)
# bump pyproject version, update the table above to the new tag/commit, commit
```
Rebrand is manual (no script). The surface is small — the 8 rebrand commits after
`f2a5cd1` are the canonical reference for what naming to fix.

<!-- ponytail: pin file, not a tool. Re-fork + replay-rename only if upstream diffs
     ever get too big to port by hand. -->
