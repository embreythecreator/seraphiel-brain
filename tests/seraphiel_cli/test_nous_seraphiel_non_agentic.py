"""Tests for the Nous-seraphiel-3/4 non-agentic warning detector.

Prior to this check, the warning fired on any model whose name contained
``"seraphiel"`` anywhere (case-insensitive). That false-positived on unrelated
local Modelfiles such as ``seraphiel-brain:qwen3-14b-ctx16k`` — a tool-capable
Qwen3 wrapper that happens to live under the "seraphiel" tag namespace.

``is_nous_seraphiel_non_agentic`` should only match the actual Seraphiel
seraphiel-3 / Seraphiel-4 chat family.
"""

from __future__ import annotations

import pytest

from seraphiel_cli.model_switch import (
    _SERAPHIEL_MODEL_WARNING,
    _check_seraphiel_model_warning,
    is_nous_seraphiel_non_agentic,
)


@pytest.mark.parametrize(
    "model_name",
    [
        "embreythecreator/seraphiel-3-Llama-3.1-70B",
        "embreythecreator/seraphiel-3-Llama-3.1-405B",
        "seraphiel-3",
        "seraphiel-3",
        "seraphiel-4",
        "seraphiel-4-405b",
        "seraphiel_4_70b",
        "openrouter/seraphiel3:70b",
        "openrouter/embreythecreator/seraphiel-4-405b",
        "embreythecreator/seraphiel3",
        "seraphiel-3.1",
    ],
)
def test_matches_real_nous_seraphiel_chat_models(model_name: str) -> None:
    assert is_nous_seraphiel_non_agentic(model_name), (
        f"expected {model_name!r} to be flagged as Nous Seraphiel 3/4"
    )
    assert _check_seraphiel_model_warning(model_name) == _SERAPHIEL_MODEL_WARNING


@pytest.mark.parametrize(
    "model_name",
    [
        # Kyle's local Modelfile — qwen3:14b under a custom tag
        "seraphiel-brain:qwen3-14b-ctx16k",
        "seraphiel-brain:qwen3-14b-ctx32k",
        "seraphiel-honcho:qwen3-8b-ctx8k",
        # Plain unrelated models
        "qwen3:14b",
        "qwen3-coder:30b",
        "qwen2.5:14b",
        "claude-opus-4-6",
        "anthropic/claude-sonnet-4.5",
        "gpt-5",
        "openai/gpt-4o",
        "google/gemini-2.5-flash",
        "deepseek-chat",
        # Non-chat Seraphiel models we don't warn about
        "seraphiel-llm-2",
        "seraphiel2-pro",
        "nous-seraphiel-2-mistral",
        # Edge cases
        "",
        "seraphiel",  # bare "seraphiel" isn't the 3/4 family
        "seraphiel-brain",
        "brain-seraphiel-3-impostor",  # "3" not preceded by /: boundary
    ],
)
def test_does_not_match_unrelated_models(model_name: str) -> None:
    assert not is_nous_seraphiel_non_agentic(model_name), (
        f"expected {model_name!r} NOT to be flagged as Nous Seraphiel 3/4"
    )
    assert _check_seraphiel_model_warning(model_name) == ""


def test_none_like_inputs_are_safe() -> None:
    assert is_nous_seraphiel_non_agentic("") is False
    # Defensive: the helper shouldn't crash on None-ish falsy input either.
    assert _check_seraphiel_model_warning("") == ""
