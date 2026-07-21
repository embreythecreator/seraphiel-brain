"""Session-scoped execution policy — the runtime boundary behind plan mode.

Postures are an axis, not a mode zoo: v1 ships ACT (default, everything
allowed) and PLAN (read-only exploration + save_plan). The policy lives in
SessionDB keyed by session_id because gateway/API surfaces build a fresh
AIAgent per request — state on the agent object would silently fail open.

Enforcement is a NON-halting deny: the tool executor synthesizes an error
result for the denied call and the turn continues (unlike guardrail blocks,
which halt the turn). See policy_deny_message().

State machine:

    OFF -> PLANNING -> READY(plan_id, revision, digest)
        -> EXECUTING(one armed turn) -> OFF
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class ExecutionPosture(str, Enum):
    ACT = "act"
    PLAN = "plan"
    # Future axes (observe, sandbox) extend this enum; never collapse to bool.


class PlanModeState(str, Enum):
    OFF = "off"
    PLANNING = "planning"
    READY = "ready"
    EXECUTING = "executing"


# Tools usable while planning. Mirrors the read-only set in
# agent/tool_dispatch_helpers._PARALLEL_SAFE_TOOLS (minus HA/vision, which
# have no planning value) plus todo/clarify bookkeeping and the plan-mode
# artifact tool. Everything absent is denied — default-deny, no exceptions
# for terminal/exec (shell cannot be classified safely; blocked outright).
PLAN_ALLOWED_TOOLS = frozenset({
    "read_file",
    "search_files",
    "session_search",
    "skill_view",
    "skills_list",
    "web_extract",
    "web_search",
    "todo",
    "clarify",
    "save_plan",
})


@dataclass(frozen=True)
class ExecutionPolicy:
    state: PlanModeState = PlanModeState.OFF
    task: str = ""
    plan_id: str = ""
    revision: int = 0
    digest: str = ""
    plan_path: str = ""
    armed: bool = False
    turn_id: str = ""
    updated_at: float = field(default_factory=time.time)

    @property
    def posture(self) -> ExecutionPosture:
        if self.state in (PlanModeState.PLANNING, PlanModeState.READY):
            return ExecutionPosture.PLAN
        return ExecutionPosture.ACT

    @property
    def short_id(self) -> str:
        return self.plan_id[:8]

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "task": self.task,
            "plan_id": self.plan_id,
            "revision": self.revision,
            "digest": self.digest,
            "plan_path": self.plan_path,
            "armed": self.armed,
            "turn_id": self.turn_id,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionPolicy":
        try:
            return cls(
                state=PlanModeState(str(data.get("state", "off"))),
                task=str(data.get("task", "")),
                plan_id=str(data.get("plan_id", "")),
                revision=int(data.get("revision", 0)),
                digest=str(data.get("digest", "")),
                plan_path=str(data.get("plan_path", "")),
                armed=bool(data.get("armed", False)),
                turn_id=str(data.get("turn_id", "")),
                updated_at=float(data.get("updated_at", 0.0)),
            )
        except (TypeError, ValueError):
            # Malformed persisted state defaults to ACT — plan mode is
            # opt-in; a broken row must not brick normal sessions.
            return cls()


def policy_deny_message(
    policy: Optional["ExecutionPolicy"], tool_name: str
) -> Optional[str]:
    """Return a deny message if this tool call violates the policy, else None.

    Name-only in v1. Any future arg-sensitive posture (path-scoped writes,
    exec classifiers) must be checked inside the tool-execution middleware,
    after argument transformations — not here.
    """
    if policy is None or policy.posture is ExecutionPosture.ACT:
        if tool_name == "save_plan":
            return (
                "save_plan is only available in plan mode. "
                "The operator enters it with /plan <task>."
            )
        return None
    if tool_name in PLAN_ALLOWED_TOOLS:
        return None
    hint = (
        f"/plan approve {policy.short_id}" if policy.short_id else "/plan approve"
    )
    return (
        f"Plan mode: the '{tool_name}' tool is locked. Continue with "
        "read-only tools, save your plan with save_plan(title, content), "
        f"and present it. The operator unlocks execution with {hint}."
    )


def compute_plan_digest(path: str) -> Optional[str]:
    """sha256 of a plan file, or None if unreadable."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


class ExecutionPolicyStore:
    """Load/save + state transitions over SessionDB.

    Every method is failure-tolerant on load (defaults to OFF/ACT) but
    enforcement is unconditional once a PLAN-posture policy loads.
    """

    def __init__(self, session_db=None):
        self._db = session_db

    def _get_db(self):
        if self._db is None:
            from seraphiel_state import SessionDB
            self._db = SessionDB()
        return self._db

    def load(self, session_id: str) -> ExecutionPolicy:
        if not session_id:
            return ExecutionPolicy()
        try:
            data = self._get_db().get_execution_policy(session_id)
        except Exception:
            logger.exception("execution policy load failed; defaulting to ACT")
            return ExecutionPolicy()
        if not data:
            return ExecutionPolicy()
        return ExecutionPolicy.from_dict(data)

    def save(self, session_id: str, policy: ExecutionPolicy) -> None:
        policy = replace(policy, updated_at=time.time())
        self._get_db().set_execution_policy(session_id, policy.to_dict())

    def load_for_turn(self, session_id: str, turn_id: str = "") -> ExecutionPolicy:
        """Turn-start load with one-use consume and crash reconciliation.

        EXECUTING + armed  -> consume: this turn runs unlocked (ACT posture),
                              armed flips off so it cannot be reused.
        EXECUTING + unarmed -> stale (approved turn already ran, or crashed
                              mid-execution): reset to OFF.
        """
        policy = self.load(session_id)
        if policy.state is not PlanModeState.EXECUTING:
            return policy
        if policy.armed:
            consumed = replace(policy, armed=False, turn_id=turn_id or "")
            try:
                self.save(session_id, consumed)
            except Exception:
                logger.exception("execution policy consume failed")
            return consumed
        self.finish(session_id)
        return ExecutionPolicy()

    def enter_planning(self, session_id: str, task: str) -> ExecutionPolicy:
        policy = ExecutionPolicy(state=PlanModeState.PLANNING, task=task.strip())
        self.save(session_id, policy)
        return policy

    def record_revision(
        self, session_id: str, *, path: str, digest: str
    ) -> Tuple[Optional[ExecutionPolicy], Optional[str]]:
        """Register a saved plan revision. PLANNING/READY -> READY."""
        policy = self.load(session_id)
        if policy.state not in (PlanModeState.PLANNING, PlanModeState.READY):
            return None, "save_plan requires plan mode (/plan <task>)."
        policy = replace(
            policy,
            state=PlanModeState.READY,
            plan_id=policy.plan_id or uuid.uuid4().hex,
            revision=policy.revision + 1,
            digest=digest,
            plan_path=path,
        )
        self.save(session_id, policy)
        return policy, None

    def approve(
        self, session_id: str, short_id: str
    ) -> Tuple[Optional[ExecutionPolicy], Optional[str]]:
        """READY -> EXECUTING(armed). Validates short-id and plan digest."""
        policy = self.load(session_id)
        if policy.state is not PlanModeState.READY:
            return None, (
                f"No plan is awaiting approval (state: {policy.state.value})."
            )
        if not short_id or short_id != policy.short_id:
            return None, (
                f"Unknown plan id '{short_id}'. The current plan is "
                f"{policy.short_id} (rev {policy.revision})."
            )
        actual = compute_plan_digest(policy.plan_path)
        if actual is None:
            return None, f"Plan file missing or unreadable: {policy.plan_path}"
        if actual != policy.digest:
            return None, (
                "Plan file changed on disk since it was saved (digest "
                "mismatch). Ask for a fresh revision, then approve that."
            )
        policy = replace(policy, state=PlanModeState.EXECUTING, armed=True)
        self.save(session_id, policy)
        return policy, None

    def finish(self, session_id: str) -> None:
        try:
            self._get_db().clear_execution_policy(session_id)
        except Exception:
            logger.exception("execution policy clear failed")
