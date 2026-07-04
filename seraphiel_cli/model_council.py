"""Seraphiel Model Council role configuration and routing helpers.

This module is the central place where the Crown + six-wing model layout is
defined. Runtime code should route by canonical role names, then resolve the
role to provider/model here, instead of scattering vendor model IDs through the
agent loop.
"""

from __future__ import annotations

import json
import logging
import os
from copy import deepcopy
from time import perf_counter
from typing import Any, Mapping

logger = logging.getLogger(__name__)

ORCHESTRATOR_ROLE = "orchestrator"
FALLBACK_ROLE = "fallback"
WING_ROLES: tuple[str, ...] = (
    "reasoning",
    "multimodal",
    "writing",
    "chinese_generalist",
    "long_context_agent",
    "code_reasoning",
)
MODEL_COUNCIL_ROLES: tuple[str, ...] = (ORCHESTRATOR_ROLE, *WING_ROLES, FALLBACK_ROLE)

_DEFAULT_ROLE_SLOTS: dict[str, dict[str, str]] = {
    ORCHESTRATOR_ROLE: {
        "provider": "openrouter",
        "model": "anthropic/claude-fable-5",
        "name": "Crown",
        "purpose": "Routes tasks, judges outputs, and coordinates multi-model workflows.",
    },
    "reasoning": {
        "provider": "openrouter",
        "model": "openai/gpt-5.5",
        "name": "Reasoning Wing",
        "purpose": "General reasoning, research, code planning, and deep analysis.",
    },
    "multimodal": {
        "provider": "openrouter",
        "model": "google/gemini-3-pro-preview",
        "name": "Multimodal Wing",
        "purpose": "Image, video, document, and long-context multimodal understanding.",
    },
    "writing": {
        "provider": "openrouter",
        "model": "anthropic/claude-opus-4.8",
        "name": "Writing Wing",
        "purpose": "Writing, editing, voice, narrative, judgment, and synthesis.",
    },
    "chinese_generalist": {
        "provider": "openrouter",
        "model": "qwen/qwen3-plus",
        "name": "Chinese Generalist Wing",
        "purpose": "Chinese-language reasoning, multilingual work, coding, and translation.",
    },
    "long_context_agent": {
        "provider": "openrouter",
        "model": "z-ai/glm-5.2",
        "name": "Long Context Wing",
        "purpose": "Long-horizon agent tasks, huge context, tool workflows, and sustained missions.",
    },
    "code_reasoning": {
        "provider": "openrouter",
        "model": "deepseek/deepseek-v4-pro",
        "name": "Code Reasoning Wing",
        "purpose": "Code, math, debugging, structured reasoning, and low-cost execution.",
    },
    FALLBACK_ROLE: {
        "provider": "openrouter",
        "model": "openai/gpt-5.5",
        "name": "Fallback",
        "purpose": "Fallback when the selected specialist model is unavailable.",
    },
}

_MODEL_ENV: dict[str, tuple[str, ...]] = {
    ORCHESTRATOR_ROLE: ("SERAPHIEL_ORCHESTRATOR_MODEL", "SERAPHIEL_CROWN_MODEL"),
    "reasoning": ("SERAPHIEL_REASONING_MODEL",),
    "multimodal": ("SERAPHIEL_MULTIMODAL_MODEL",),
    "writing": ("SERAPHIEL_WRITING_MODEL",),
    "chinese_generalist": ("SERAPHIEL_CHINESE_GENERALIST_MODEL",),
    "long_context_agent": ("SERAPHIEL_LONG_CONTEXT_AGENT_MODEL",),
    "code_reasoning": ("SERAPHIEL_CODE_REASONING_MODEL",),
    FALLBACK_ROLE: ("SERAPHIEL_FALLBACK_MODEL",),
}

_PROVIDER_ENV: dict[str, tuple[str, ...]] = {
    ORCHESTRATOR_ROLE: ("SERAPHIEL_ORCHESTRATOR_PROVIDER", "SERAPHIEL_CROWN_PROVIDER"),
    "reasoning": ("SERAPHIEL_REASONING_PROVIDER",),
    "multimodal": ("SERAPHIEL_MULTIMODAL_PROVIDER",),
    "writing": ("SERAPHIEL_WRITING_PROVIDER",),
    "chinese_generalist": ("SERAPHIEL_CHINESE_GENERALIST_PROVIDER",),
    "long_context_agent": ("SERAPHIEL_LONG_CONTEXT_AGENT_PROVIDER",),
    "code_reasoning": ("SERAPHIEL_CODE_REASONING_PROVIDER",),
    FALLBACK_ROLE: ("SERAPHIEL_FALLBACK_PROVIDER",),
}

_BOOL_ENV = {
    "enabled": "SERAPHIEL_MODEL_COUNCIL_ENABLED",
    "orchestrator_review_enabled": "SERAPHIEL_ORCHESTRATOR_REVIEW_ENABLED",
    "direct_route_simple_tasks": "SERAPHIEL_DIRECT_ROUTE_SIMPLE_TASKS",
    "debug": "SERAPHIEL_MODEL_ROUTER_DEBUG",
}

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}

_ROUTING_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "multimodal",
        "Task mentions image, screenshot, video, visual analysis, PDF layout, or diagrams.",
        (
            "image",
            "images",
            "screenshot",
            "screenshots",
            "video",
            "visual",
            "vision",
            "diagram",
            "pdf layout",
            "layout in this pdf",
            "ocr",
        ),
    ),
    (
        "code_reasoning",
        "Task mentions code, bugs, terminal work, repositories, APIs, databases, or refactors.",
        (
            "code",
            "coding",
            "bug",
            "debug",
            "debugging",
            "terminal",
            "repo",
            "repository",
            "refactor",
            "api",
            "database",
            "typescript",
            "javascript",
            "python",
            "pytest",
            "stack trace",
        ),
    ),
    (
        "long_context_agent",
        "Task implies a long document, huge context, memory-heavy analysis, or multi-step mission.",
        (
            "long document",
            "huge context",
            "memory-heavy",
            "multi-step project",
            "multi step project",
            "sustained mission",
            "200-page",
            "200 page",
            "entire book",
            "large corpus",
        ),
    ),
    (
        "chinese_generalist",
        "Task mentions Chinese, China-specific context, or bilingual Chinese/English work.",
        ("chinese", "mandarin", "china-specific", "china specific", "bilingual chinese", "zh-cn"),
    ),
    (
        "writing",
        "Task asks for prose, story, tone, voice, character, rewrite, or polish.",
        (
            "story",
            "prose",
            "lyrics",
            "tone",
            "voice",
            "character",
            "rewrite",
            "polish",
            "cinematic scene",
            "narrative",
        ),
    ),
    (
        "reasoning",
        "Task asks for deep analysis, research, planning, architecture, or comparison.",
        ("analysis", "research", "planning", "architecture", "comparison", "compare", "strategy", "design"),
    ),
)


def _env_first(environ: Mapping[str, str], names: tuple[str, ...]) -> str:
    for name in names:
        value = str(environ.get(name) or "").strip()
        if value:
            return value
    return ""


def _env_bool(environ: Mapping[str, str], name: str, default: bool) -> bool:
    value = str(environ.get(name) or "").strip().lower()
    return _coerce_bool_value(value, default)


def _coerce_bool_value(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    value = str(value or "").strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    return default


def _clean_role_slot(role: str, raw: Any) -> dict[str, str]:
    base = deepcopy(_DEFAULT_ROLE_SLOTS[role])
    if isinstance(raw, dict):
        for key in ("provider", "model", "name", "purpose"):
            value = str(raw.get(key) or "").strip()
            if value:
                base[key] = value
    base["role"] = role
    return base


def default_model_council_config() -> dict[str, Any]:
    """Return the built-in Crown + six-wing council config."""
    return {
        "enabled": True,
        "orchestrator_review_enabled": True,
        "direct_route_simple_tasks": True,
        "debug": False,
        "roles": {role: _clean_role_slot(role, {}) for role in MODEL_COUNCIL_ROLES},
    }


def resolve_model_council_config(
    raw: Any = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Merge built-in defaults, config.yaml overrides, and env overrides."""
    env = os.environ if environ is None else environ
    raw_cfg = raw if isinstance(raw, dict) else {}
    cfg = default_model_council_config()

    for key in ("enabled", "orchestrator_review_enabled", "direct_route_simple_tasks", "debug"):
        if key in raw_cfg:
            cfg[key] = _coerce_bool_value(raw_cfg.get(key), bool(cfg[key]))
        env_name = _BOOL_ENV[key]
        cfg[key] = _env_bool(env, env_name, bool(cfg[key]))

    raw_roles = raw_cfg.get("roles") if isinstance(raw_cfg.get("roles"), dict) else {}
    roles: dict[str, dict[str, str]] = {}
    for role in MODEL_COUNCIL_ROLES:
        slot = _clean_role_slot(role, raw_roles.get(role) if isinstance(raw_roles, dict) else {})
        provider = _env_first(env, _PROVIDER_ENV.get(role, ()))
        model = _env_first(env, _MODEL_ENV.get(role, ()))
        if provider:
            slot["provider"] = provider
        if model:
            slot["model"] = model
        roles[role] = slot
    cfg["roles"] = roles
    return cfg


def model_council_moa_preset(
    raw: Any = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return a MoA preset where six wings advise and the Crown acts."""
    cfg = resolve_model_council_config(raw, environ=environ)
    roles = cfg["roles"]
    refs = [
        {
            "provider": roles[role]["provider"],
            "model": roles[role]["model"],
            "role": role,
            "wing": roles[role].get("name", role),
            "purpose": roles[role].get("purpose", ""),
        }
        for role in WING_ROLES
    ]
    crown = roles[ORCHESTRATOR_ROLE]
    return {
        "reference_models": refs,
        "aggregator": {
            "provider": crown["provider"],
            "model": crown["model"],
            "role": ORCHESTRATOR_ROLE,
            "name": crown.get("name", "Crown"),
            "purpose": crown.get("purpose", ""),
        },
        "reference_temperature": 0.6,
        "aggregator_temperature": 0.4,
        "max_tokens": 4096,
        "enabled": bool(cfg.get("enabled", True)),
    }


def resolve_model_role(
    role: str,
    raw: Any = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Resolve one canonical role to its configured provider/model slot."""
    clean_role = str(role or "").strip()
    cfg = resolve_model_council_config(raw, environ=environ)
    if clean_role not in cfg["roles"]:
        raise KeyError(clean_role)
    return deepcopy(cfg["roles"][clean_role])


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _matches(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def route_model_role(
    task: str,
    raw: Any = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Select the best wing role for a task using role-level heuristics."""
    start = perf_counter()
    cfg = resolve_model_council_config(raw, environ=environ)
    if not cfg.get("enabled", True):
        decision = {
            "enabled": False,
            "selectedRole": "",
            "selectedProvider": "",
            "selectedModel": "",
            "reason": "Model council is disabled.",
            "fallbackUsed": False,
            "latencyMs": int((perf_counter() - start) * 1000),
        }
        log_model_council_decision(decision, debug=bool(cfg.get("debug")))
        return decision

    text = str(task or "").lower()
    if _contains_cjk(str(task or "")):
        role = "chinese_generalist"
        reason = "Task contains CJK characters."
    else:
        role = "reasoning"
        reason = "Defaulted to the reasoning wing."
        for candidate, candidate_reason, keywords in _ROUTING_RULES:
            if _matches(text, keywords):
                role = candidate
                reason = candidate_reason
                break

    slot = cfg["roles"][role]
    decision = {
        "enabled": True,
        "selectedRole": role,
        "selectedProvider": slot["provider"],
        "selectedModel": slot["model"],
        "reason": reason,
        "fallbackUsed": False,
        "latencyMs": int((perf_counter() - start) * 1000),
    }
    log_model_council_decision(decision, debug=bool(cfg.get("debug")))
    return decision


def fallback_chain_for_role(
    role: str,
    raw: Any = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> list[dict[str, str]]:
    """Return selected specialist -> fallback -> Crown, de-duplicated."""
    cfg = resolve_model_council_config(raw, environ=environ)
    roles = cfg["roles"]
    chain_roles = [str(role or "").strip(), FALLBACK_ROLE, ORCHESTRATOR_ROLE]
    chain: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for chain_role in chain_roles:
        slot = roles.get(chain_role)
        if not slot:
            continue
        key = (slot.get("provider", ""), slot.get("model", ""))
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        chain.append(deepcopy(slot))
    return chain


def validate_model_council_config(raw: Any = None) -> list[str]:
    """Return human-readable config errors for missing role provider/model IDs."""
    cfg = resolve_model_council_config(raw)
    issues: list[str] = []
    for role in MODEL_COUNCIL_ROLES:
        slot = cfg["roles"].get(role) or {}
        if not str(slot.get("provider") or "").strip():
            issues.append(f"model_council.roles.{role}.provider is required")
        if not str(slot.get("model") or "").strip():
            issues.append(f"model_council.roles.{role}.model is required")
    return issues


def log_model_council_decision(
    decision: Mapping[str, Any],
    *,
    task_id: str | None = None,
    token_usage: Mapping[str, Any] | None = None,
    debug: bool = False,
    log: logging.Logger | None = None,
) -> None:
    """Log a routing decision without user content."""
    payload = {
        "taskId": task_id or "",
        "selectedRole": decision.get("selectedRole", ""),
        "selectedProvider": decision.get("selectedProvider", ""),
        "selectedModel": decision.get("selectedModel", ""),
        "reason": decision.get("reason", "") if debug else "",
        "fallbackUsed": bool(decision.get("fallbackUsed", False)),
        "latencyMs": int(decision.get("latencyMs", 0) or 0),
        "tokenUsage": dict(token_usage or {}),
    }
    target = log or logger
    target.info("model_council.route %s", json.dumps(payload, sort_keys=True))


def env_var_names_for_role(role: str) -> tuple[str, ...]:
    """Expose env var names for docs/tests without duplicating constants."""
    return _MODEL_ENV.get(str(role or "").strip(), ())


def provider_env_var_names_for_role(role: str) -> tuple[str, ...]:
    """Expose provider env var names for docs/tests without duplicating constants."""
    return _PROVIDER_ENV.get(str(role or "").strip(), ())


def routing_keywords_for_role(role: str) -> tuple[str, ...]:
    """Return the keyword set used by the simple router for a wing role."""
    for candidate, _reason, keywords in _ROUTING_RULES:
        if candidate == role:
            return keywords
    return ()
