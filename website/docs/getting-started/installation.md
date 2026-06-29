---
sidebar_position: 2
title: "Installation"
description: "Install Seraphiel Brain on Linux, macOS, WSL2, native Windows, or Android via Termux"
---

# Installation

Get Seraphiel Brain up and running in under two minutes!

## Quick Install
### With the Seraphiel Desktop installer on macOS or Windows (recommended)
To easily install the command-line and desktop applications, [download the Seraphiel Desktop installer](https://seraphiel-brain.embreythecreator.com/) from our website and run it.

### Without Seraphiel Desktop:
For a command-line only install without Seraphiel Desktop, run:

#### Linux / macOS / WSL2 / Android (Termux)
```bash
curl -fsSL https://seraphiel-brain.embreythecreator.com/install.sh | bash
```

#### Windows (native)

Run in powershell:
```powershell
iex (irm https://seraphiel-brain.embreythecreator.com/install.ps1) 
```

If you want to install & run Seraphiel Desktop after a command-line only install, simply run
```bash
seraphiel desktop
```

### What the Installer Does

The installer handles everything automatically — all dependencies (Python, Node.js, ripgrep, ffmpeg), the repo clone, virtual environment, global `seraphiel` command setup, and LLM provider configuration. By the end, you're ready to chat.

#### Install Layout

Where the installer puts things depends on whether you're installing as a normal user or as root:

| Installer | Code lives at | `seraphiel` binary | Data directory |
|---|---|---|---|
| pip install | Python site-packages | `~/.local/bin/seraphiel` (console_scripts) | `~/.seraphiel/` |
| Per-user (git installer) | `~/.seraphiel/seraphiel-brain/` | `~/.local/bin/seraphiel` (symlink) | `~/.seraphiel/` |
| Root-mode (`sudo curl … \| sudo bash`) | `/usr/local/lib/seraphiel-brain/` | `/usr/local/bin/seraphiel` | `/root/.seraphiel/` (or `$SERAPHIEL_HOME`) |

The root-mode **FHS layout** (`/usr/local/lib/…`, `/usr/local/bin/seraphiel`) matches where other system-wide developer tools land on Linux. It's useful for shared-machine deployments where one system install should serve every user. Per-user config (auth, skills, sessions) still lives under each user's `~/.seraphiel/` or explicit `SERAPHIEL_HOME`.

### After Installation

Reload your shell and start chatting:

```bash
source ~/.bashrc   # or: source ~/.zshrc
seraphiel             # Start chatting!
```

To reconfigure individual settings later, use the dedicated commands:

```bash
seraphiel model          # Choose your LLM provider and model
seraphiel tools          # Configure which tools are enabled
seraphiel gateway setup  # Set up messaging platforms
seraphiel config set     # Set individual config values
seraphiel setup          # Or run the full setup wizard to configure everything at once
```

:::tip Fastest path: Nous Portal
One subscription covers 300+ models plus the [Tool Gateway](/user-guide/features/tool-gateway) (web search, image generation, TTS, cloud browser). Skip the per-tool key juggling:

```bash
seraphiel setup --portal
```

That logs you in, sets Nous as your provider, and turns on the Tool Gateway in one command.
:::

---

## Prerequisites

**Installer:** On non-Windows platforms, the only prerequisite is **Git**. The installer automatically handles everything else:

- **uv** (fast Python package manager)
- **Python 3.11** (via uv, no sudo needed)
- **Node.js v22** (for browser automation and WhatsApp bridge)
- **ripgrep** (fast file search)
- **ffmpeg** (audio format conversion for TTS)

:::info
You do **not** need to install Python, Node.js, ripgrep, or ffmpeg manually. The installer detects what's missing and installs it for you. Just make sure `git` is available (`git --version`).
:::

:::tip Nix users
If you use Nix (on NixOS, macOS, or Linux), there's a dedicated setup path with a Nix flake, declarative NixOS module, and optional container mode. See the **[Nix & NixOS Setup](./nix-setup.md)** guide.
:::

---

## Manual / Developer Installation

If you want to clone the repo and install from source — for contributing, running from a specific branch, or having full control over the virtual environment — see the [Development Setup](../developer-guide/contributing.md#development-setup) section in the Contributing guide.

---

## Non-Sudo / System Service User Installs

Running Seraphiel as a dedicated unprivileged user (e.g. a `seraphiel` systemd service account, or any user without `sudo` access) is supported. The only thing on the install path that genuinely needs root is Playwright's `--with-deps` step, which `apt`-installs shared libraries (`libnss3`, `libxkbcommon`, etc.) used by Chromium. The installer detects whether sudo is available and gracefully degrades when it isn't — it will install the Chromium binary into the service user's own Playwright cache and print the exact command an administrator needs to run separately.

**Recommended split (Debian/Ubuntu):**

1. **One time, as an admin user with sudo**, install the system libraries Chromium needs:
   ```bash
   sudo npx playwright install-deps chromium
   ```
   (You can run this from anywhere — `npx` will fetch Playwright on the fly.)

2. **As the unprivileged service user**, run the regular installer. It will detect the missing sudo, skip `--with-deps`, and install Chromium into the user's local Playwright cache:
   ```bash
   curl -fsSL https://seraphiel-brain.embreythecreator.com/install.sh | bash
   ```

   If you want to skip the Playwright step entirely — for example because you're running headless and don't need browser automation — pass `--skip-browser`:
   ```bash
   curl -fsSL https://seraphiel-brain.embreythecreator.com/install.sh | bash -s -- --skip-browser
   ```

3. **Make `seraphiel` available to the service user's shells.** The installer writes the launcher to `~/.local/bin/seraphiel`. System service accounts often have a minimal PATH that doesn't include `~/.local/bin`. Either add it to the user's environment, or symlink the launcher into a system location:
   ```bash
   # Option A — add to the service user's profile
   echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc

   # Option B — symlink system-wide (run as an admin)
   sudo ln -s /home/seraphiel/.seraphiel/seraphiel-brain/venv/bin/seraphiel /usr/local/bin/seraphiel
   ```

4. **Verify:** `seraphiel doctor` should now run cleanly. If you get `ModuleNotFoundError: No module named 'dotenv'`, you're invoking the repo source `seraphiel` file (`~/.seraphiel/seraphiel-brain/seraphiel`) with system Python instead of the venv launcher (`~/.seraphiel/seraphiel-brain/venv/bin/seraphiel`) — fix step 3.

The same pattern works on Arch (the installer uses pacman with the same sudo-detection logic), Fedora/RHEL, and openSUSE — those distros don't support `--with-deps` at all, so an administrator always installs the system libraries separately. The relevant `dnf`/`zypper` commands are printed by the installer.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `seraphiel: command not found` | Reload your shell (`source ~/.bashrc`) or check PATH |
| `API key not set` | Run `seraphiel model` to configure your provider, or `seraphiel config set OPENROUTER_API_KEY your_key` |
| Missing config after update | Run `seraphiel config check` then `seraphiel config migrate` |

For more diagnostics, run `seraphiel doctor` — it will tell you exactly what's missing and how to fix it.

## Install method auto-detection

Seraphiel auto-detects whether it was installed via `pip`, the git installer, Homebrew, or NixOS, and `seraphiel update` prints the matching update command for that path. There's no env var to set — the detection is based on the install layout (Python site-packages, `~/.seraphiel/seraphiel-brain/`, Homebrew prefix, or Nix store path). `seraphiel doctor` also surfaces the detected method under its environment summary.
