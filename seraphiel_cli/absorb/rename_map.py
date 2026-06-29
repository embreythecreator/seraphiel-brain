"""Transform T: the Hermes/Nous -> Seraphiel/Embrey rebrand, as a reproducible
function.

Single source of truth for the rename-aware absorb harness. The fork rebrands two
token families, with different carve-outs:

  HERMES family  (product):  Hermes Agent -> Seraphiel Brain, Hermes -> Seraphiel,
                 hermes -> seraphiel, hermes-agent -> seraphiel-brain.
                 Applied everywhere EXCEPT achievements/LICENSE, which keeps its
                 upstream "Hermes Achievements contributors" copyright line.

  NOUS family    (vendor/brand/org):  Nous Research -> Seraphiel,
                 NousResearch -> embreythecreator, nousresearch.com ->
                 embreythecreator.com. Applied everywhere EXCEPT legal files
                 (LICENSE / NOTICE / COPYING), which keep upstream attribution
                 (mirroring how the top-level LICENSE keeps "Nous Research").
                 NOTE: the "Nous Portal" inference *provider* and its
                 nous_account / nous_subscription / NOUS_* identifiers are real
                 external service names and are deliberately NOT rebranded — the
                 rules only match the brand/org/domain forms, never bare "Nous".

  ATTRIBUTION    self-credit: "created by Seraphiel"/"created by Hermes" ->
                 "created by Embrey The Creator" (operator requirement, enforced
                 on every absorb).

PATH swap reuses the HERMES path tokens (case-aware); 643/643 hermes paths were
renamed and 0 kept, so the path swap is total and needs no path carve-outs. (No
"nous" path component is rebranded — nous_account.py etc. stay.)

Deliberately NOT in T (scoped Seraphiel design changes = genuine divergence the
3-way merge preserves, NOT mechanical rebrand): the brand glyph swap (selective)
and the boot banner / figlet wordmark. The transform-fidelity gate proves these
plus the security-guidance NOTICE per-file hand-edits are the only residuals.
"""

from __future__ import annotations

import posixpath

# --- HERMES family: product rename (longest match first) ---
HERMES_RULES: list[tuple[str, str]] = [
    # The product's "agent" suffix becomes "brain" (Seraphiel Brain), so the
    # compound forms must be matched before the bare token.
    ("Hermes Agent", "Seraphiel Brain"),   # display wordmark
    ("hermes_agent", "seraphiel_brain"),   # python package / identifiers
    ("hermes-agent", "seraphiel-brain"),   # pip / nix / npm / slug
    ("HERMES", "SERAPHIEL"),
    ("Hermes", "Seraphiel"),
    ("hermes", "seraphiel"),
]
# NOTE: the capitalised hyphen form "Hermes-Agent" (HTTP User-Agent product token)
# and the lowercased HuggingFace model-id prefix are hand-edited inconsistently in
# the fork (-> "Seraphiel Brain" vs "seraphiel-Agent"); not rule-derivable, so they
# are left as genuine divergence for the merge rather than special-cased here.

# --- NOUS family: vendor/brand/org rename (longest/most-specific first) ---
# Order matters: do the domain and CamelCase org before the spaced brand so each
# is consumed by its most specific rule.
NOUS_RULES: list[tuple[str, str]] = [
    ("nousresearch.com", "embreythecreator.com"),
    ("NousResearch", "embreythecreator"),
    ("Nous Research", "Seraphiel"),
    ("nousresearch", "embreythecreator"),   # any leftover lowercase handle
]

# --- Attribution: enforce operator self-credit (applied after the families) ---
ATTRIBUTION_RULES: list[tuple[str, str]] = [
    ("created by Seraphiel", "created by Embrey The Creator / The Voice"),
    ("created by Hermes", "created by Embrey The Creator / The Voice"),
]

# --- Path rules: case-aware HERMES path tokens, total swap ---
# Same agent->brain slug rule as content (nix/, homebrew, skill dirs, egg-info).
PATH_RULES: list[tuple[str, str]] = [
    ("hermes_agent", "seraphiel_brain"),
    ("hermes-agent", "seraphiel-brain"),
    ("HERMES", "SERAPHIEL"),
    ("Hermes", "Seraphiel"),
    ("hermes", "seraphiel"),
]

# Legal files keep upstream attribution -> NOUS family is skipped in them.
_LEGAL_BASENAMES = ("LICENSE", "LICENSE.txt", "LICENSE.md", "NOTICE",
                    "NOTICE.txt", "NOTICE.md", "COPYING")

# Files our line authors itself / that reference upstream by name on purpose.
# They never originate from the upstream tree, so T never processes them during an
# absorb; the hard skip just makes a self-sweep idempotent.
SELF_AUTHORED_CARVEOUTS: tuple[str, ...] = (
    "UPSTREAM_BASE.md",
)


def swap_path(path: str) -> str:
    """Apply the case-aware path rebrand to a single tree path."""
    for find, repl in PATH_RULES:
        path = path.replace(find, repl)
    return path


def _is_legal_file(seraphiel_path: str) -> bool:
    return posixpath.basename(seraphiel_path) in _LEGAL_BASENAMES


def _is_hermes_carveout(seraphiel_path: str) -> bool:
    # achievements/LICENSE keeps "Hermes Achievements contributors"
    return seraphiel_path.endswith("achievements/LICENSE")


def is_self_authored(seraphiel_path: str) -> bool:
    return any(seraphiel_path == s or seraphiel_path.endswith("/" + s)
               for s in SELF_AUTHORED_CARVEOUTS)


def swap_text(text: str, seraphiel_path: str, attribution: bool = True) -> str:
    """Apply the rebrand families + attribution to a text blob body.

    Carve-outs are per token-family and keyed on the (already path-swapped) path:
      - HERMES family skipped for achievements/LICENSE
      - NOUS family skipped for legal files (LICENSE/NOTICE/COPYING)

    `attribution=False` runs pure rename only (used by the fidelity gate, which
    measures rename faithfulness against a HEAD that predates the attribution fix).
    """
    if not _is_hermes_carveout(seraphiel_path):
        for find, repl in HERMES_RULES:
            text = text.replace(find, repl)
    if not _is_legal_file(seraphiel_path):
        for find, repl in NOUS_RULES:
            text = text.replace(find, repl)
    if attribution:
        for find, repl in ATTRIBUTION_RULES:
            text = text.replace(find, repl)
    return text


def looks_binary(data: bytes) -> bool:
    """Cheap binary sniff: a NUL byte in the first 8KiB marks a binary blob."""
    return b"\x00" in data[:8192]
