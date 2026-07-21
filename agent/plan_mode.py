"""Plan-mode shared core: /plan command handling + conversation-event text.

One module drives every surface (gateway platforms, CLI REPL, API server) so
the command grammar and state transitions cannot drift apart. All plan-mode
text is injected as ordinary conversation content — the system prompt and
tool schemas never change with mode, keeping the prompt-cache prefix stable.

Runtime enforcement lives in agent/execution_policy.py + the tool executor;
this module is only the operator-facing control surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from agent.execution_policy import (
    ExecutionPolicy,
    ExecutionPolicyStore,
    PlanModeState,
)

PLAN_USAGE = (
    "Usage: /plan <task> — enter plan mode\n"
    "       /plan status — show plan-mode state\n"
    "       /plan approve <id> — approve the saved plan and execute\n"
    "       /plan off — leave plan mode without executing"
)

# Operational contract injected when entering plan mode. Deliberately short:
# the full plan-authoring craft lives in the `plan` skill, which the model
# can read with skill_view (allowed in plan mode) — injecting 300+ lines
# every cycle would bloat the transcript for no enforcement benefit.
PLAN_MODE_INSTRUCTIONS = """[PLAN MODE ON]
You are in plan mode. Mutating tools (terminal, write_file, patch, browser,
delegation, etc.) are LOCKED at the runtime — calls will be denied. Do not
fight the denials; plan.

Your job this cycle:
1. Explore the task with read-only tools (read_file, search_files,
   session_search, web_search, skills_list/skill_view).
2. Write a concrete, actionable markdown plan. For the authoring craft
   (bite-sized tasks, exact paths, complete code, verification steps),
   consult the `plan` skill via skill_view if needed.
3. Save it with save_plan(title, content) — the ONLY write available.
   It returns a short id.
4. Present the plan and tell the operator: approve with
   /plan approve <short-id>, request changes with a normal message, or
   abandon with /plan off.

Revisions: feedback keeps plan mode on; save an updated plan with
save_plan again (new revision, same id)."""


def build_plan_invocation(task: str) -> str:
    task = (task or "").strip()
    if task:
        return f"{PLAN_MODE_INSTRUCTIONS}\n\nThe task to plan:\n{task}"
    return (
        f"{PLAN_MODE_INSTRUCTIONS}\n\nNo explicit task was given — infer "
        "the task to plan from the current conversation context."
    )


def build_plan_reminder(policy: ExecutionPolicy) -> str:
    """One-line prefix for ordinary messages while PLANNING/READY."""
    if policy.state is PlanModeState.READY:
        detail = f"plan {policy.short_id} rev {policy.revision} awaiting approval"
    else:
        detail = "no plan saved yet"
    return (
        f"[Plan mode active — {detail}. Mutating tools are locked; revise "
        "with save_plan; the operator approves with "
        f"/plan approve {policy.short_id or '<id>'} or exits with /plan off.]"
    )


def build_execute_instruction(policy: ExecutionPolicy) -> str:
    return (
        f"[Plan {policy.short_id} rev {policy.revision} APPROVED — tools are "
        f"unlocked for this turn. Execute the plan at {policy.plan_path} "
        "now, following it step by step.]"
    )


def format_plan_status(policy: ExecutionPolicy) -> str:
    if policy.state is PlanModeState.OFF:
        return "Plan mode: off."
    lines = [f"Plan mode: {policy.state.value}"]
    if policy.task:
        lines.append(f"Task: {policy.task}")
    if policy.plan_id:
        lines.append(
            f"Plan: {policy.short_id} rev {policy.revision} — {policy.plan_path}"
        )
        if policy.state is PlanModeState.READY:
            lines.append(f"Approve with /plan approve {policy.short_id}")
    return "\n".join(lines)


@dataclass(frozen=True)
class PlanCommandResult:
    """Either a direct reply (no agent run) or a rewritten agent message."""
    reply: Optional[str] = None
    rewritten_message: Optional[str] = None


def handle_plan_command(
    args: str,
    session_id: str,
    *,
    runtime_is_codex: bool = False,
    session_db=None,
) -> PlanCommandResult:
    store = ExecutionPolicyStore(session_db)
    args = (args or "").strip()
    lowered = args.lower()

    if lowered == "status":
        return PlanCommandResult(reply=format_plan_status(store.load(session_id)))

    if lowered in ("off", "exit", "cancel"):
        policy = store.load(session_id)
        if policy.state is PlanModeState.OFF:
            return PlanCommandResult(reply="Plan mode is not active.")
        store.finish(session_id)
        return PlanCommandResult(reply="Plan mode off — back to normal execution.")

    if lowered.startswith("approve"):
        short_id = args[len("approve"):].strip()
        if not short_id:
            policy = store.load(session_id)
            hint = (
                f" The current plan is {policy.short_id}."
                if policy.short_id else ""
            )
            return PlanCommandResult(
                reply=f"Usage: /plan approve <id>.{hint}"
            )
        policy, err = store.approve(session_id, short_id)
        if err is not None:
            return PlanCommandResult(reply=err)
        return PlanCommandResult(
            rewritten_message=build_execute_instruction(policy)
        )

    if not args:
        return PlanCommandResult(reply=PLAN_USAGE)

    # /plan <task> — enter planning.
    if runtime_is_codex:
        return PlanCommandResult(
            reply=(
                "Plan mode cannot be enforced under the codex_app_server "
                "runtime (tools run inside Codex, bypassing the tool "
                "executor). Switch runtime before planning."
            )
        )
    policy = store.load(session_id)
    if policy.state in (PlanModeState.PLANNING, PlanModeState.READY):
        return PlanCommandResult(
            reply=(
                f"Plan mode is already active ({format_plan_status(policy)}). "
                "Send feedback as a normal message, or /plan off first."
            )
        )
    store.enter_planning(session_id, args)
    return PlanCommandResult(rewritten_message=build_plan_invocation(args))
