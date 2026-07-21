# Plan Mode — runtime-enforced design

**Date:** 2026-07-21
**Status:** Approved design, pre-implementation
**Origin:** Operator request + Codex second-look; builds on existing prompt-only `skills/software-development/plan` skill.

## Goal

Make plan mode real instead of advisory: a session-scoped mode where the Brain
can explore read-only and write a plan, but every mutating tool is hard-blocked
at the tool executor until the operator approves. Approval unlocks tools and
the Brain executes the plan in the same session (one-shot: mode auto-exits on
approve).

## Commands

| Command | Effect |
|---|---|
| `/plan <task>` | Enter plan mode, task text becomes the planning request |
| `/plan status` | Report current mode (on/off, active task) |
| `/plan off` | Exit plan mode without approving (back to normal) |
| Approve (Face card button / CLI `approve`) | Clear mode, instruct Brain to execute the presented plan |

## Architecture

- **State:** `plan_mode: bool` (+ optional task string) on the agent session
  state. Session-scoped, never persisted; dies with the session.
- **Prompt-cache-safe:** system prompt and tool schemas are NOT changed by the
  mode. Entering/leaving plan mode is represented as an ordinary conversation
  event (a system-style turn injected into the message list, e.g.
  "Plan mode ON — plan-writing instructions follow…"), so the cached prompt
  prefix stays byte-identical.
- **Plan-writing instructions:** the existing
  `skills/software-development/plan` skill text is reused verbatim as the
  content of the plan-mode conversation event. The skill stays as-is; the
  runtime boundary is added underneath it.
- **Enforcement seam:** `ToolCallGuardrailController.before_call` in
  `agent/tool_guardrails.py`, which every dispatch path already calls
  (`agent/tool_executor.py:447` concurrent, `:1047` sequential). A plan-mode
  check runs before the existing guardrail logic and returns a blocking
  `ToolGuardrailDecision`; the model receives the synthetic result via the
  existing `toolguard_synthetic_result` path ("Plan mode: this tool is locked.
  Finish exploring read-only and present your plan.").

## Tool policy in plan mode

- **Allowed:** read/search/list tools (derived from the existing read-only
  classification used by `_PARALLEL_SAFE_TOOLS` / dispatch helpers).
- **`write_file`:** allowed ONLY when the resolved target path is inside the
  active workspace's `.seraphiel/plans/`. Anywhere else → blocked.
- **`exec` / terminal:** restricted to a small allowlist of demonstrably
  read-only command prefixes (`ls`, `cat`, `head`, `tail`, `grep`, `rg`,
  `find`, `git log`, `git show`, `git diff`, `git status`, `wc`). Anything
  else — including pipes/redirects into files — blocked.
  `# ponytail:` prefix allowlist, not a shell parser; upgrade path is a real
  read-only shell classifier if planning keeps needing more.
- **Blocked outright:** `patch`, delegation/subagents, browser interaction,
  messaging/channels, cron mutation, memory mutation, and any other
  side-effecting tool. Default-deny: a tool not on the allow side is blocked.

## Approval flow

1. Operator sends `/plan <task>` (Face canvas slash command or Brain CLI).
2. Brain explores read-only, writes the plan markdown to `.seraphiel/plans/`,
   and presents it in the reply.
3. Face renders an Approve / Revise card (space-action block machinery from
   WO-A1); CLI accepts a plain `approve` message.
4. **Approve** → action-result turn (`plan_approved`), flag clears, Brain
   executes the plan immediately with full tools. Mode is one-shot.
5. **Revise / any other feedback** → mode stays on, Brain re-plans.
6. `/plan off` at any point abandons without executing.

## Surfaces

- **Brain CLI (`cli.py`):** `/plan …` commands + `approve`; mode shown in the
  prompt/status area.
- **Face canvas:** `/plan` slash command; plan arrives with Approve/Revise
  card; active mode indicated in the composer.
- **Gateway/API:** mode readable in session state so TUI/gateway clients can
  display it; mode changes flow through the normal message path (no new
  endpoint).

## Error handling

- Model attempts a blocked tool → synthetic guardrail result, turn continues.
- Session crash mid-plan → flag lost with session; plan file (if written)
  survives in `.seraphiel/plans/`.
- `write_file` path check uses the resolved absolute path (no `..` escapes).

## Testing

One test module (mirrors existing guardrail tests):
- plan mode on: mutating tool blocked with synthetic result; read tool passes.
- `write_file` inside `.seraphiel/plans/` passes; outside blocked; `..`
  traversal blocked.
- `exec` allowlisted prefix passes; non-allowlisted and redirect forms blocked.
- approval clears flag → previously blocked tool passes.
- `/plan` / `/plan status` / `/plan off` round-trip.

Face side verified live in browser as usual.

## Out of scope (v1)

- Persisting plan mode across sessions.
- Shell-command classification beyond the prefix allowlist.
- Multi-plan queues or plan versioning.
