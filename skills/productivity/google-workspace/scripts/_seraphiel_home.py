"""Resolve SERAPHIEL_HOME for standalone skill scripts.

Skill scripts may run outside the Seraphiel process (e.g. system Python,
nix env, CI) where ``seraphiel_constants`` is not importable.  This module
provides the same ``get_seraphiel_home()`` and ``display_seraphiel_home()``
contracts as ``seraphiel_constants`` without requiring it on ``sys.path``.

When ``seraphiel_constants`` IS available it is used directly so that any
future enhancements (profile resolution, Docker detection, etc.) are
picked up automatically.  The fallback path replicates the core logic
from ``seraphiel_constants.py`` using only the stdlib.

All scripts under ``google-workspace/scripts/`` should import from here
instead of duplicating the ``SERAPHIEL_HOME = Path(os.getenv(...))`` pattern.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from seraphiel_constants import display_seraphiel_home as display_seraphiel_home
    from seraphiel_constants import get_seraphiel_home as get_seraphiel_home
except (ModuleNotFoundError, ImportError):

    def get_seraphiel_home() -> Path:
        """Return the Seraphiel home directory (default: ~/.seraphiel).

        Mirrors ``seraphiel_constants.get_seraphiel_home()``."""
        val = os.environ.get("SERAPHIEL_HOME", "").strip()
        return Path(val) if val else Path.home() / ".seraphiel"

    def display_seraphiel_home() -> str:
        """Return a user-friendly ``~/``-shortened display string.

        Mirrors ``seraphiel_constants.display_seraphiel_home()``."""
        home = get_seraphiel_home()
        try:
            return "~/" + str(home.relative_to(Path.home()))
        except ValueError:
            return str(home)
