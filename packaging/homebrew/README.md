Homebrew packaging notes for Seraphiel Brain.

Use `packaging/homebrew/seraphiel-brain.rb` as a tap or `homebrew-core` starting point.

Key choices:
- Stable builds should target the semver-named sdist asset attached to each GitHub release, not the CalVer tag tarball.
- `faster-whisper` now lives in the `voice` extra, which keeps wheel-only transitive dependencies out of the base Homebrew formula.
- The wrapper exports `SERAPHIEL_BUNDLED_SKILLS`, `SERAPHIEL_OPTIONAL_SKILLS`, and `SERAPHIEL_MANAGED=homebrew` so packaged installs keep runtime assets and defer upgrades to Homebrew.

Typical update flow:
1. Bump the formula `url`, `version`, and `sha256`.
2. Refresh Python resources with `brew update-python-resources --print-only seraphiel-brain`.
3. Keep `ignore_packages: %w[certifi cryptography pydantic]`.
4. Verify `brew audit --new --strict seraphiel-brain` and `brew test seraphiel-brain`.
