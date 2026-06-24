# Langfuse Observability Plugin

This plugin ships bundled with Seraphiel but is **opt-in** — it only loads when
you explicitly enable it.

## Enable

Pick one:

```bash
# Interactive: walks you through credentials + SDK install + enable
seraphiel tools  # → Langfuse Observability

# Manual
pip install langfuse
seraphiel plugins enable observability/langfuse
```

## Required credentials

Set these in `~/.seraphiel/.env` (or via `seraphiel tools`):

```bash
SERAPHIEL_LANGFUSE_PUBLIC_KEY=pk-lf-...
SERAPHIEL_LANGFUSE_SECRET_KEY=sk-lf-...
SERAPHIEL_LANGFUSE_BASE_URL=https://cloud.langfuse.com   # or your self-hosted URL
```

Without the SDK or credentials the hooks no-op silently — the plugin fails
open.

## Verify

```bash
seraphiel plugins list                 # observability/langfuse should show "enabled"
seraphiel chat -q "hello"              # then check Langfuse for a "Seraphiel turn" trace
```

## Optional tuning

```bash
SERAPHIEL_LANGFUSE_ENV=production       # environment tag
SERAPHIEL_LANGFUSE_RELEASE=v1.0.0       # release tag
SERAPHIEL_LANGFUSE_SAMPLE_RATE=0.5      # sample 50% of traces
SERAPHIEL_LANGFUSE_MAX_CHARS=12000      # max chars per field (default: 12000)
SERAPHIEL_LANGFUSE_DEBUG=true           # verbose plugin logging
```

## Disable

```bash
seraphiel plugins disable observability/langfuse
```
