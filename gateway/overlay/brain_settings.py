"""seraphiel-brain overlay: Ward-authenticated HTTP settings route (SG1).

The Brain's settings (its ``config.yaml``) are file-based and only mutable via the
Brain's ``config set`` CLI. The Face's admin panel needs to read/write them over
HTTP, so this overlay exposes three routes on the gateway's existing aiohttp API
server (the one already bound to 127.0.0.1:8642 in API-server mode):

    GET   /v1/brain/settings/schema   -> domain/dangerous descriptor + source commit
    GET   /v1/brain/settings          -> current config, secrets redacted
    PATCH /v1/brain/settings          -> validated partial write (atomic, via config set)

Every route reuses the adapter's ``_check_auth`` (Bearer == API_SERVER_KEY = the
Ward token) so this adds no new trust boundary. It is mounted by a single hook in
``api_server.py``'s ``connect()`` and never edits any vendored upstream file in
place, so monthly re-absorption sees zero conflicts.

Wire keys (model/terminal/...) are preserved verbatim; the Face rebrands display
labels only. Secrets live in ``.env`` (set_config_value routes *_API_KEY/_TOKEN
there), so config.yaml rarely holds raw secrets -- but GET redacts by key-name
anyway as defense in depth.
"""
from __future__ import annotations

import re
import subprocess
from typing import Any, Dict

try:
    from aiohttp import web
except Exception:  # pragma: no cover - aiohttp is always present in the gateway
    web = None  # type: ignore

from seraphiel_cli.config import (
    get_config_path,
    get_project_root,
    load_config,
    set_config_value,
)

# Dotted keys whose mutation can disable a safety check or run arbitrary code.
# Writing ANY of these requires the elevation header (Seal tier, defense in depth).
# The Face proxy enforces the same set; this is the server-side half.
DANGEROUS_FIELDS = {
    "approvals.mode",          # turning the approval gate off
    "code_execution.enabled",  # arbitrary code execution
    "terminal.backend",        # swapping the shell backend (e.g. -> local host)
    "updates.auto_apply",      # silent self-update
    "security.redact_secrets", # disabling secret redaction
}
# ponytail: exact-key match + the two prefixes below. Widen if a new safety
# toggle lands; the Face projection's `dangerous` flags must stay in sync.
DANGEROUS_PREFIXES = ("code_execution.", "approvals.")

# Elevation token the Face attaches only when the admin session holds the
# elevated Seal capability. Absent -> dangerous writes are refused 403.
ELEVATION_HEADER = "X-Brain-Allow-Dangerous"

_SECRET_RE = re.compile(
    r"(api[_-]?key|secret|token|password|passwd|credential|private[_-]?key)", re.I
)


def _is_dangerous(dotted_key: str) -> bool:
    return dotted_key in DANGEROUS_FIELDS or dotted_key.startswith(DANGEROUS_PREFIXES)


def _redact(obj: Any) -> Any:
    """Mask values whose key name looks secret-ish. Recurses dicts/lists."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if _SECRET_RE.search(str(k)) and v not in (None, "", {}, []):
                out[k] = "***REDACTED***"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


def _flatten(d: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    """Flatten a nested patch into dotted leaf keys (scalar leaves only)."""
    out: Dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.update(_flatten(v, key))
        else:
            out[key] = v
    return out


def _scalar_str(value: Any) -> str:
    """set_config_value expects a string; render scalars the way the CLI would."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def _source_commit() -> str:
    try:
        root = get_project_root()
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=3,
        ).stdout.strip()
        return out or "unknown"
    except Exception:
        return "unknown"


def _schema_descriptor() -> Dict[str, Any]:
    """Top-level domains parsed from cli-config.yaml.example + dangerous flags."""
    domains = []
    try:
        example = get_project_root() / "cli-config.yaml.example"
        for line in example.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^([a-z][a-z0-9_]*):", line)
            if m:
                domains.append(m.group(1))
    except Exception:
        domains = sorted(load_config().keys())
    return {
        "source": "cli-config.yaml.example",
        "source_commit": _source_commit(),
        "config_path": str(get_config_path()),
        "domains": domains,
        "dangerous": sorted(DANGEROUS_FIELDS),
    }


def register_brain_settings_routes(app, adapter) -> None:
    """Mount the three settings routes on the gateway's aiohttp app.

    `adapter` is the ApiServerAdapter instance; we reuse its `_check_auth`
    (the Ward/Bearer gate) so these routes share the API server's trust model.
    """
    if web is None:
        return

    async def _schema(request):
        if (err := adapter._check_auth(request)) is not None:
            return err
        return web.json_response(_schema_descriptor())

    async def _get(request):
        if (err := adapter._check_auth(request)) is not None:
            return err
        return web.json_response({"config": _redact(load_config())})

    async def _patch(request):
        if (err := adapter._check_auth(request)) is not None:
            return err
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON body"}, status=400)
        if not isinstance(body, dict):
            return web.json_response({"error": "body must be an object"}, status=400)

        patch = body.get("patch", body)  # accept {"patch": {...}} or a bare object
        if not isinstance(patch, dict) or not patch:
            return web.json_response({"error": "empty patch"}, status=400)

        flat = _flatten(patch)
        elevated = request.headers.get(ELEVATION_HEADER, "").strip() in ("1", "true", "yes")
        blocked = [k for k in flat if _is_dangerous(k) and not elevated]
        if blocked:
            return web.json_response(
                {
                    "error": "elevation_required",
                    "message": "These fields require Seal elevation and were not written.",
                    "fields": sorted(blocked),
                },
                status=403,
            )

        applied, failed = [], {}
        for key, value in flat.items():
            try:
                set_config_value(key, value if isinstance(value, str) else _scalar_str(value))
                applied.append(key)
            except SystemExit:
                failed[key] = "rejected (managed or invalid)"
            except Exception as exc:  # surface, don't swallow
                failed[key] = str(exc)
        status = 200 if not failed else 207
        return web.json_response({"applied": applied, "failed": failed}, status=status)

    app.router.add_get("/v1/brain/settings/schema", _schema)
    app.router.add_get("/v1/brain/settings", _get)
    app.router.add_patch("/v1/brain/settings", _patch)
