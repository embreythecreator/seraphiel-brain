"""Regression tests for _apply_profile_override SERAPHIEL_HOME guard (issue #22502).

When SERAPHIEL_HOME is set to the seraphiel root (e.g. systemd hardcodes
SERAPHIEL_HOME=/root/.seraphiel), _apply_profile_override must still read
active_profile and update SERAPHIEL_HOME to the profile directory.

When SERAPHIEL_HOME is already a profile directory (.../profiles/<name>),
_apply_profile_override must trust it and return without re-reading
active_profile (child-process inheritance contract).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path



def _run_apply_profile_override(
    tmp_path, monkeypatch, *, seraphiel_home: str | None, active_profile: str | None,
    argv: list[str] | None = None,
):
    """Run _apply_profile_override in isolation.

    Returns the value of os.environ["SERAPHIEL_HOME"] after the call,
    or None if unset.
    """
    seraphiel_root = tmp_path / ".seraphiel"
    seraphiel_root.mkdir(parents=True, exist_ok=True)

    if active_profile is not None:
        (seraphiel_root / "active_profile").write_text(active_profile)

    if active_profile and active_profile != "default":
        (seraphiel_root / "profiles" / active_profile).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    if seraphiel_home is not None:
        monkeypatch.setenv("SERAPHIEL_HOME", seraphiel_home)
    else:
        monkeypatch.delenv("SERAPHIEL_HOME", raising=False)

    monkeypatch.setattr(sys, "argv", argv or ["seraphiel", "gateway", "start"])

    from seraphiel_cli.main import _apply_profile_override
    _apply_profile_override()

    return os.environ.get("SERAPHIEL_HOME")


class TestApplyProfileOverrideSeraphielHomeGuard:
    """Regression guard for issue #22502.

    Verifies that SERAPHIEL_HOME pointing to the seraphiel root does NOT suppress
    the active_profile check, while SERAPHIEL_HOME already pointing to a
    profile directory IS trusted as-is.
    """

    def test_seraphiel_home_at_root_with_active_profile_is_redirected(
        self, tmp_path, monkeypatch
    ):
        """SERAPHIEL_HOME=/root/.seraphiel + active_profile=coder must redirect
        SERAPHIEL_HOME to .../profiles/coder.

        Bug scenario from #22502: systemd sets SERAPHIEL_HOME to the seraphiel root
        and the user switches to a profile via `seraphiel profile use`.
        Before the fix, the guard returned early and active_profile was ignored.
        """
        seraphiel_root = tmp_path / ".seraphiel"
        seraphiel_root.mkdir(parents=True, exist_ok=True)

        result = _run_apply_profile_override(
            tmp_path,
            monkeypatch,
            seraphiel_home=str(seraphiel_root),
            active_profile="coder",
        )

        assert result is not None, "SERAPHIEL_HOME must be set after profile redirect"
        assert "profiles" in result, (
            f"Expected SERAPHIEL_HOME to point into profiles/ dir, got: {result!r}"
        )
        assert result.endswith("coder"), (
            f"Expected SERAPHIEL_HOME to end with 'coder', got: {result!r}"
        )

    def test_seraphiel_home_already_profile_dir_is_trusted(self, tmp_path, monkeypatch):
        """SERAPHIEL_HOME=.../profiles/coder must not be overridden even when
        active_profile says something different.

        Preserves the child-process inheritance contract: a subprocess spawned
        with SERAPHIEL_HOME already set to a specific profile must stay in that
        profile.
        """
        seraphiel_root = tmp_path / ".seraphiel"
        profile_dir = seraphiel_root / "profiles" / "coder"
        profile_dir.mkdir(parents=True, exist_ok=True)

        (seraphiel_root / "active_profile").write_text("other")

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("SERAPHIEL_HOME", str(profile_dir))
        monkeypatch.setattr(sys, "argv", ["seraphiel", "gateway", "start"])

        from seraphiel_cli.main import _apply_profile_override
        _apply_profile_override()

        assert os.environ.get("SERAPHIEL_HOME") == str(profile_dir), (
            "SERAPHIEL_HOME must remain unchanged when already pointing to a profile dir"
        )

    def test_seraphiel_home_unset_reads_active_profile(self, tmp_path, monkeypatch):
        """Classic case: SERAPHIEL_HOME unset + active_profile=coder must set
        SERAPHIEL_HOME to the profile directory (existing behaviour must not regress).
        """
        result = _run_apply_profile_override(
            tmp_path,
            monkeypatch,
            seraphiel_home=None,
            active_profile="coder",
        )

        assert result is not None
        assert "coder" in result

    def test_seraphiel_home_unset_default_profile_no_redirect(self, tmp_path, monkeypatch):
        """active_profile=default must not redirect SERAPHIEL_HOME."""
        seraphiel_root = tmp_path / ".seraphiel"
        seraphiel_root.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.delenv("SERAPHIEL_HOME", raising=False)
        monkeypatch.setattr(sys, "argv", ["seraphiel", "gateway", "start"])
        (seraphiel_root / "active_profile").write_text("default")

        from seraphiel_cli.main import _apply_profile_override
        _apply_profile_override()

        assert os.environ.get("SERAPHIEL_HOME") is None
