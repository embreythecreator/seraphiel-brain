# Upstream base

This is a **white fork** of Hermes Agent (NousResearch/hermes-agent), imported as a
squashed snapshot — there is **no shared git history with upstream**, so `git merge`
does not work directly. Upstream is absorbed with the **rename-aware harness** in
`scripts/absorb/`, which rebrands an upstream tag into our namespace and 3-way merges
it onto our tree.

| | value |
|---|---|
| Current tree corresponds to | **Hermes v0.17.0** |
| Upstream tag | `v2026.6.19` |
| Upstream commit | `2bd1977d8` |
| Our version (independent line) | `0.17.0` (pyproject.toml — source of truth) |

`upstream` remote is configured locally (`NousResearch/hermes-agent`), pushed nowhere,
invisible to public clones of this repo.

## Make our own update
Commit to `main`, bump the patch in `pyproject.toml` (`0.17.0` → `0.17.1`). Done.

## Absorb a Hermes update (rename-aware harness)
The transform (Hermes→Seraphiel, Nous Research→Seraphiel/Embrey, plus carve-outs) is
codified in `scripts/absorb/rename_map.py` — no more hand-porting.

```sh
# 1. prove the transform still reproduces HEAD (pure-rename fidelity check)
scripts/absorb/absorb.sh --gate                 # uses --base below; expect "no stray tokens"

# 2. build the full-parity 3-way merge onto a fresh absorb/<tag> branch
scripts/absorb/absorb.sh v2026.7.0 --base v2026.6.19

# 3. if it reports conflicts, materialise + resolve them:
git checkout absorb/v2026.7.0
git read-tree --reset -u <merged-tree>          # printed by the driver
#   ...edit files carrying ^<<<<<<< markers (only where OUR genuine changes —
#      glyph ✶, Brain Settings overlay, versioned model name — overlap upstream),
#      re-applying our change in any code upstream relocated...
git add -A && git commit-tree $(git write-tree) -p HEAD -m "absorb: ... v2026.6.19 -> v2026.7.0"

# 4. parity_report.py must end STATUS: READY (no markers, no stray tokens)
# 5. bump pyproject + update this table to the new tag/commit, update CHANGELOG.md
```

**Base ref bookkeeping:** `--base` is the *previously absorbed* upstream tag (the merge
base for the 3-way). It is `v2026.6.19` as of this absorb; update it (and the default in
`absorb.sh`) every time you absorb. The original fork base was `f2a5cd1` (squashed import
of `v2026.6.5`); the v2026.6.5→v2026.6.19 absorb un-trimmed the import to full parity, so
future absorbs diff cleanly against the full upstream tree.

## How the harness works (so the next maintainer trusts it)
- `rename_map.py` — the transform T: HERMES + NOUS token families with per-family
  carve-outs (legal files keep upstream attribution; the achievements LICENSE keeps its
  "Hermes Achievements" line; the "Nous Portal" inference *provider* is never rebranded),
  plus the `created by … → Embrey The Creator` attribution rule and the path swap.
- `rebrand_tree.py` — applies T to any git ref via plumbing, emitting a rebranded tree.
- `absorb.sh` — builds BASE=T(base,no-attr), THEIRS=T(tag), OURS=HEAD and 3-way merges so
  conflicts collapse to genuine divergence; `--gate` runs the fidelity check.
- `parity_report.py` — classifies the merged tree (re-added / divergence / conflicts /
  stray tokens) and gates the commit.
- **Genuine divergence** deliberately NOT in T (re-applied by hand during conflict
  resolution if upstream moves it): the selective brand glyph swap (⚕→✶), the boot
  banner/figlet wordmark, the Brain Settings overlay, and the versioned model name.

<!-- ponytail: the harness replaced the by-hand diff port once the upstream diff grew to
     ~1,700 files. If a future upstream restructures the rename surface wholesale,
     re-derive rename_map.py from the rebrand commits rather than patching token-by-token. -->
