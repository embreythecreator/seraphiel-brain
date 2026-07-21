"""Plan-mode execution policy: deny matrix, state machine, approval, save_plan."""

import json

import pytest

from agent.execution_policy import (
    ExecutionPolicy,
    ExecutionPolicyStore,
    ExecutionPosture,
    PlanModeState,
    compute_plan_digest,
    policy_deny_message,
)
from agent.plan_mode import handle_plan_command
from seraphiel_state import SessionDB

SID = "sess-plan-test"


@pytest.fixture
def db(tmp_path):
    return SessionDB(db_path=tmp_path / "state.db")


@pytest.fixture
def store(db):
    return ExecutionPolicyStore(db)


def _planning(store):
    return store.enter_planning(SID, "add dark mode")


def _ready(store, tmp_path, content="# The plan\n"):
    _planning(store)
    plan = tmp_path / "plan.md"
    plan.write_text(content)
    policy, err = store.record_revision(
        SID, path=str(plan), digest=compute_plan_digest(str(plan))
    )
    assert err is None
    return policy


# ── Deny matrix ──────────────────────────────────────────────────────

def test_act_posture_allows_everything_except_save_plan():
    assert policy_deny_message(None, "terminal") is None
    assert policy_deny_message(ExecutionPolicy(), "write_file") is None
    assert policy_deny_message(None, "save_plan") is not None


def test_plan_posture_denies_mutating_and_unknown_tools(store):
    policy = _planning(store)
    assert policy.posture is ExecutionPosture.PLAN
    for tool in ("terminal", "execute_code", "write_file", "patch",
                 "delegate_task", "browser_navigate", "memory",
                 "some_mcp_plugin_tool"):
        msg = policy_deny_message(policy, tool)
        assert msg is not None, f"{tool} should be denied in plan mode"
        assert tool in msg
    for tool in ("read_file", "search_files", "session_search",
                 "skill_view", "skills_list", "web_search", "todo",
                 "clarify", "save_plan"):
        assert policy_deny_message(policy, tool) is None, tool


# ── State machine ────────────────────────────────────────────────────

def test_state_survives_reload_from_fresh_store(db, store, tmp_path):
    _ready(store, tmp_path)
    # Fresh store over the same DB — the stateless-API scenario where a
    # brand-new agent is built per request.
    reloaded = ExecutionPolicyStore(db).load(SID)
    assert reloaded.state is PlanModeState.READY
    assert reloaded.revision == 1
    assert reloaded.posture is ExecutionPosture.PLAN


def test_record_revision_requires_plan_mode(store, tmp_path):
    plan = tmp_path / "p.md"
    plan.write_text("x")
    policy, err = store.record_revision(SID, path=str(plan), digest="d")
    assert policy is None and err is not None


def test_revision_bumps_with_same_plan_id(store, tmp_path):
    first = _ready(store, tmp_path)
    plan2 = tmp_path / "plan2.md"
    plan2.write_text("# rev 2\n")
    second, err = store.record_revision(
        SID, path=str(plan2), digest=compute_plan_digest(str(plan2))
    )
    assert err is None
    assert second.plan_id == first.plan_id
    assert second.revision == 2


# ── Approval ─────────────────────────────────────────────────────────

def test_approve_happy_path_then_one_use_consume(store, tmp_path):
    ready = _ready(store, tmp_path)
    approved, err = store.approve(SID, ready.short_id)
    assert err is None
    assert approved.state is PlanModeState.EXECUTING and approved.armed

    # Turn 1: consumes the arm; posture is ACT (tools unlocked).
    turn = store.load_for_turn(SID, "turn-1")
    assert turn.state is PlanModeState.EXECUTING
    assert not turn.armed
    assert turn.posture is ExecutionPosture.ACT

    # Turn 2: stale EXECUTING reconciles to OFF — approval is one-use.
    after = store.load_for_turn(SID, "turn-2")
    assert after.state is PlanModeState.OFF


def test_approve_rejects_wrong_id_missing_file_and_stale_digest(store, tmp_path):
    ready = _ready(store, tmp_path)

    _, err = store.approve(SID, "deadbeef")
    assert err is not None and ready.short_id in err

    plan = tmp_path / "plan.md"
    plan.write_text("# tampered after save\n")
    _, err = store.approve(SID, ready.short_id)
    assert err is not None and "digest" in err.lower()

    plan.unlink()
    _, err = store.approve(SID, ready.short_id)
    assert err is not None

    _, err = store.approve(SID, ready.short_id)  # still READY, not consumed
    assert err is not None


def test_approve_requires_ready_state(store):
    _, err = store.approve(SID, "abcd1234")
    assert err is not None
    _planning(store)
    _, err = store.approve(SID, "abcd1234")
    assert err is not None


def test_malformed_persisted_state_defaults_to_act(db, store):
    db.set_execution_policy(SID, {"state": "no-such-state", "armed": "x"})
    assert store.load(SID).posture is ExecutionPosture.ACT


# ── save_plan tool ───────────────────────────────────────────────────

def test_save_plan_writes_under_plans_dir_and_records_revision(
    monkeypatch, db, store, tmp_path
):
    import agent.runtime_cwd as runtime_cwd
    import tools.save_plan_tool as spt

    _planning(store)
    monkeypatch.setattr(runtime_cwd, "resolve_agent_cwd", lambda: tmp_path)
    # save_plan_tool lazily imports these from their modules
    import agent.execution_policy as ep
    monkeypatch.setattr(ep, "ExecutionPolicyStore", lambda db_arg=None: store)

    result = json.loads(spt.save_plan_tool("Dark Mode", "# plan body\n", SID))
    assert "error" not in result
    assert result["revision"] == 1
    assert str(tmp_path / ".seraphiel" / "plans") in result["path"]
    assert compute_plan_digest(result["path"]) == result["digest"]
    assert store.load(SID).state is PlanModeState.READY


def test_save_plan_rejects_outside_plan_mode(monkeypatch, store, tmp_path):
    import agent.runtime_cwd as runtime_cwd
    import agent.execution_policy as ep
    import tools.save_plan_tool as spt

    monkeypatch.setattr(runtime_cwd, "resolve_agent_cwd", lambda: tmp_path)
    monkeypatch.setattr(ep, "ExecutionPolicyStore", lambda db_arg=None: store)
    result = json.loads(spt.save_plan_tool("t", "c", SID))
    assert "error" in result
    plans_dir = tmp_path / ".seraphiel" / "plans"
    assert not plans_dir.exists() or not list(plans_dir.iterdir())


def test_save_plan_validates_inputs(monkeypatch, tmp_path):
    import agent.runtime_cwd as runtime_cwd
    import tools.save_plan_tool as spt

    monkeypatch.setattr(runtime_cwd, "resolve_agent_cwd", lambda: tmp_path)
    assert "error" in json.loads(spt.save_plan_tool("", "content", SID))
    assert "error" in json.loads(spt.save_plan_tool("title", "", SID))
    big = "x" * (spt.MAX_PLAN_CONTENT_CHARS + 1)
    assert "error" in json.loads(spt.save_plan_tool("title", big, SID))


# ── /plan command core ───────────────────────────────────────────────

def test_plan_command_round_trip(db, store, tmp_path):
    # enter
    res = handle_plan_command("build a widget", SID, session_db=db)
    assert res.reply is None and "PLAN MODE ON" in res.rewritten_message
    assert store.load(SID).state is PlanModeState.PLANNING

    # double-enter rejected
    res = handle_plan_command("another task", SID, session_db=db)
    assert res.reply is not None and "already active" in res.reply

    # status
    res = handle_plan_command("status", SID, session_db=db)
    assert res.reply is not None and "planning" in res.reply

    # approve before any save
    res = handle_plan_command("approve abcd1234", SID, session_db=db)
    assert res.reply is not None

    # save a revision, then approve with the right id
    ready = _ready(ExecutionPolicyStore(db), tmp_path)
    res = handle_plan_command(f"approve {ready.short_id}", SID, session_db=db)
    assert res.reply is None
    assert "APPROVED" in res.rewritten_message

    # off (after reconciliation the mode is effectively over)
    store.finish(SID)
    res = handle_plan_command("off", SID, session_db=db)
    assert res.reply is not None and "not active" in res.reply


def test_plan_command_codex_runtime_fails_closed(db):
    res = handle_plan_command(
        "task", SID, runtime_is_codex=True, session_db=db
    )
    assert res.reply is not None and "codex_app_server" in res.reply


def test_plan_command_usage_and_off(db, store):
    assert handle_plan_command("", SID, session_db=db).reply is not None
    _planning(store)
    res = handle_plan_command("off", SID, session_db=db)
    assert res.reply is not None and "off" in res.reply.lower()
    assert store.load(SID).state is PlanModeState.OFF


def test_builtin_plan_command_registered():
    from seraphiel_cli.commands import COMMAND_REGISTRY
    names = {c.name for c in COMMAND_REGISTRY}
    assert "plan" in names


# ── Audit fixes: races, migration, load resilience ───────────────────

def test_double_approve_second_caller_rejected(store, tmp_path):
    """Two concurrent approves must not both arm execution (TOCTOU)."""
    import threading

    ready = _ready(store, tmp_path)
    results = []
    barrier = threading.Barrier(2)

    def _approve():
        barrier.wait()
        results.append(store.approve(SID, ready.short_id))

    threads = [threading.Thread(target=_approve) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    oks = [r for r in results if r[1] is None]
    errs = [r for r in results if r[1] is not None]
    assert len(oks) == 1 and len(errs) == 1
    assert "No plan is awaiting approval" in errs[0][1]


def test_migrate_carries_policy_across_session_rotation(store, tmp_path):
    ready = _ready(store, tmp_path)
    store.migrate(SID, "sess-rotated")
    assert store.load(SID).state is PlanModeState.OFF
    moved = store.load("sess-rotated")
    assert moved.state is PlanModeState.READY
    assert moved.plan_id == ready.plan_id
    assert moved.digest == ready.digest


def test_migrate_noops_when_off_or_same_id(store):
    store.migrate(SID, SID)
    store.migrate(SID, "sess-other")
    assert store.load("sess-other").state is PlanModeState.OFF


def test_load_retries_transient_db_errors(store, monkeypatch):
    """A locked DB must not silently unlock a planning session."""
    _planning(store)
    real = store._get_db().get_execution_policy
    calls = {"n": 0}

    def _flaky(session_id):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("database is locked")
        return real(session_id)

    monkeypatch.setattr(store._get_db(), "get_execution_policy", _flaky)
    assert store.load(SID).state is PlanModeState.PLANNING
    assert calls["n"] == 3


def test_plan_toolset_not_user_configurable():
    """/plan enters PLANNING unconditionally, so save_plan must never be
    strippable via the `seraphiel tools` checklist."""
    from seraphiel_cli.tools_config import CONFIGURABLE_TOOLSETS
    assert all(key != "plan" for key, _, _ in CONFIGURABLE_TOOLSETS)
