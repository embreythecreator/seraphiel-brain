#!/usr/bin/env bash
# Rename-aware upstream absorb driver for the Seraphiel Brain white fork.
#
# Folds an upstream Hermes tag into our rebranded tree via a 3-way merge whose
# both sides share the seraphiel namespace, so conflicts collapse to our genuine
# divergence instead of thousands of spurious path/token clashes.
#
#   absorb.sh --gate [--base <ref>]                 # prove T reproduces HEAD
#   absorb.sh <target-tag> [--base <ref>] [--head <ref>]   # build the merge
#
# Strategy (see rename_map.py / the absorb plan):
#   BASE   = T(fork-base)        rebranded, trimmed 6.5   -> merge base
#   THEIRS = T(<target-tag>)     rebranded, FULL upstream -> theirs (full parity)
#   OURS   = HEAD                rebranded + genuine feats -> ours
# Result is committed onto a fresh absorb/<tag> branch with HEAD as parent, so
# history continuity is preserved.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(git -C "$HERE" rev-parse --show-toplevel)"
cd "$REPO"
REBRAND="python3 $HERE/rebrand_tree.py"

# Merge base = the PREVIOUSLY ABSORBED upstream tag. Update this each absorb.
# (Originally f2a5cd1, the squashed import of v2026.6.5; the v2026.6.19 absorb
#  un-trimmed to full parity, so the base is now the upstream tag itself.)
BASE_REF="v2026.6.19"
HEAD_REF="HEAD"
MODE=""
TARGET=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --gate) MODE="gate"; shift ;;
    --base) BASE_REF="$2"; shift 2 ;;
    --head) HEAD_REF="$2"; shift 2 ;;
    -*) echo "unknown flag: $1" >&2; exit 2 ;;
    *) TARGET="$1"; shift ;;
  esac
done

# Legal carve-outs are the ONLY blobs allowed to retain an upstream token.
ALLOWED_STRAY_RE='(achievements/LICENSE|security-guidance/NOTICE|UPSTREAM_BASE\.md|CHANGELOG\.md|scripts/absorb/)'

gate() {
  echo ">> Transform-fidelity gate: T($BASE_REF, no-attribution) vs $HEAD_REF"
  local tree
  tree="$($REBRAND "$BASE_REF" --tree-only --no-attribution)"
  echo "   rebranded base tree: $tree"

  local stray
  stray="$(git grep -ilI -e hermes -e nousresearch "$tree" 2>/dev/null \
            | sed "s#^$tree:##" | grep -vE "$ALLOWED_STRAY_RE" || true)"
  if [[ -n "$stray" ]]; then
    echo "   !! STRAY upstream tokens outside carve-outs:" >&2
    echo "$stray" | sed 's/^/      /' >&2
    return 1
  fi
  echo "   OK: no stray hermes/nousresearch tokens outside the legal carve-outs"

  local n
  n="$(git diff --name-only "$tree" "$HEAD_REF" | wc -l | tr -d ' ')"
  echo "   residual files differing from HEAD: $n  (expected: genuine divergence only —"
  echo "   glyph swap, brand banner, Brain Settings overlay, versioned model name,"
  echo "   dependabot removal, hand-edited User-Agent/model-id tokens, our own docs)"
  echo "   review with: git diff <tree> $HEAD_REF -- <file>"
  return 0
}

absorb() {
  [[ -n "$TARGET" ]] || { echo "usage: absorb.sh <target-tag>" >&2; exit 2; }
  echo ">> Absorbing $TARGET into $HEAD_REF (base $BASE_REF)"
  case "$TARGET" in
    *rc*|*RC*|*alpha*|*beta*|*pre*)
      echo "   refusing pre-release/RC tag (policy)"; exit 2 ;;
  esac
  git rev-parse -q --verify "refs/tags/$TARGET" >/dev/null 2>&1 \
    || git fetch -q upstream "tag" "$TARGET"

  echo "   building rebranded trees (this takes a moment)..."
  # BASE is built WITHOUT the attribution rule so it matches HEAD (which predates
  # the attribution fix); THEIRS carries it, so the fix flows in from the upstream
  # side and wins the 3-way instead of looking like an "ours" revert.
  local base_tree theirs_tree ours_tree base_c theirs_c ours_c
  base_tree="$($REBRAND "$BASE_REF"  --tree-only --no-attribution)"
  theirs_tree="$($REBRAND "$TARGET"  --tree-only)"
  ours_tree="$(git rev-parse "$HEAD_REF^{tree}")"
  base_c="$(git commit-tree "$base_tree"   -m "T($BASE_REF)")"
  theirs_c="$(git commit-tree "$theirs_tree" -p "$base_c" -m "T($TARGET)")"
  ours_c="$(git commit-tree "$ours_tree"     -p "$base_c" -m "ours ($HEAD_REF)")"
  echo "   BASE=$base_c  THEIRS=$theirs_c  OURS=$ours_c"

  echo "   3-way merge-tree (merge-base = rebranded fork base)..."
  local out merged conflicts rc=0
  out="$(git merge-tree --write-tree --merge-base="$base_c" "$ours_c" "$theirs_c")" || rc=$?
  merged="$(echo "$out" | head -1)"
  conflicts="$(echo "$out" | tail -n +2)"

  local branch="absorb/$TARGET"
  git rev-parse -q --verify "refs/heads/$branch" >/dev/null 2>&1 \
    && { echo "   branch $branch exists; resolve or delete it first" >&2; exit 1; }
  git branch "$branch" "$HEAD_REF"

  if [[ $rc -eq 0 ]]; then
    echo "   CLEAN merge — no conflicts."
    local commit
    commit="$(git commit-tree "$merged" -p "$HEAD_REF" -m "absorb: hermes-agent $BASE_REF -> $TARGET (full parity)")"
    git update-ref "refs/heads/$branch" "$commit"
    echo "   committed $commit onto $branch"
  else
    echo "   CONFLICTS — merged tree (with markers) = $merged"
    echo "$conflicts" | sed 's/^/      conflict: /'
    echo "$merged" > "$HERE/.last-merged-tree"
    echo "$base_c $ours_c $theirs_c" > "$HERE/.last-merge-refs"
    echo "   To resolve in a worktree on $branch:"
    echo "     git checkout $branch && git read-tree $merged && git checkout-index -af"
    echo "   (conflicted blobs carry <<<<<<< markers; resolve, git add, then"
    echo "    git commit-tree <new-tree> -p $HEAD_REF)"
  fi

  echo "   parity report:"
  python3 "$HERE/parity_report.py" "$merged" "$theirs_tree" "$HEAD_REF" || true
}

case "${MODE:-absorb}" in
  gate) gate ;;
  *) absorb ;;
esac
