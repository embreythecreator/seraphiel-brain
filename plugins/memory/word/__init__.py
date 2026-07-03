"""Word memory plugin — MemoryProvider interface.

Long-term memory backed by Word, the angel's memory organ (headless Open
Notebook fork: Postgres+pgvector storage, Ward-authenticated REST API).

Layer mapping (WO-B2): session context stays Brain-local (``sync_turn`` is a
deliberate no-op) · persistent facts flow to Word — every built-in
MEMORY.md/USER.md write is mirrored into a dedicated notebook through a
durable write-behind queue, and the model gets explicit save/search/read
tools. Recall happens per turn via ``prefetch`` against Word's search API;
the MemoryManager sanitizes and fences all prefetch output centrally.

Word being down is never fatal: reads degrade to silence (with a 60s
re-probe backoff), writes wait in the local queue and replay when the organ
comes back.

Config (env vars, set up via `seraphiel memory setup`):
  WORD_BASE_URL      — Word API endpoint (default: http://127.0.0.1:5055)
  WORD_WARD_TOKEN    — Ward bearer token (falls back to OPEN_NOTEBOOK_WARD_TOKEN;
                       optional — a local authless Word needs none)
  WORD_NOTEBOOK      — memory notebook name (default: Seraphiel Memory)
  WORD_SEARCH_TYPE   — 'text' (default) or 'vector' (needs an embedding
                       model configured inside Word)
"""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.memory_provider import MemoryProvider
from tools.registry import tool_error

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://127.0.0.1:5055"
_DEFAULT_NOTEBOOK = "Seraphiel Memory"
_HEALTH_BACKOFF_SECONDS = 60.0
_PREFETCH_LIMIT = 6
_SNIPPET_CHARS = 400
_ASYNC_SHUTDOWN = object()


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

SEARCH_SCHEMA = {
    "name": "word_memory_search",
    "description": (
        "Search Word long-term memory. scope 'memory' (default) searches the "
        "dedicated memory notebook; scope 'all' searches every notebook, "
        "including ingested research sources."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to search for."},
            "scope": {
                "type": "string",
                "enum": ["memory", "all"],
                "description": "Search scope (default: memory).",
            },
        },
        "required": ["query"],
    },
}

SAVE_SCHEMA = {
    "name": "word_memory_save",
    "description": (
        "Persist a durable fact, preference, or decision to Word long-term "
        "memory. Survives across sessions; queued locally if Word is down."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short title for the memory."},
            "content": {"type": "string", "description": "The fact to remember."},
        },
        "required": ["title", "content"],
    },
}

READ_SCHEMA = {
    "name": "word_memory_read",
    "description": "Fetch one full note from Word by its id (e.g. a search or prefetch hit).",
    "parameters": {
        "type": "object",
        "properties": {
            "note_id": {"type": "string", "description": "Note id, e.g. 'note:abc123'."},
        },
        "required": ["note_id"],
    },
}


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

class _Client:
    """Thin Ward-authenticated client for the Word REST API."""

    def __init__(self, base_url: str, token: str, notebook_name: str):
        self.base_url = re.sub(r"/+$", "", base_url)
        self.token = token.replace("Bearer ", "").strip()
        self.notebook_name = notebook_name
        self._notebook_id: Optional[str] = None
        self._notebook_lock = threading.Lock()

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def request(self, method: str, path: str, *, json_body=None, timeout: float = 5.0) -> Any:
        import requests
        resp = requests.request(
            method.upper(), f"{self.base_url}{path}",
            json=json_body if method.upper() not in {"GET", "DELETE"} else None,
            headers=self._headers(),
            timeout=timeout,
        )
        try:
            payload = resp.json()
        except Exception:
            payload = resp.text
        if not resp.ok:
            msg = payload.get("detail") if isinstance(payload, dict) else payload
            raise RuntimeError(f"Word {method} {path} failed ({resp.status_code}): {msg}")
        return payload

    def health(self) -> bool:
        try:
            return self.request("GET", "/health", timeout=3.0).get("status") == "healthy"
        except Exception:
            return False

    def ensure_notebook(self) -> str:
        """Find-or-create the memory notebook; cached after first success."""
        with self._notebook_lock:
            if self._notebook_id:
                return self._notebook_id
            for nb in self.request("GET", "/api/notebooks"):
                if nb.get("name") == self.notebook_name:
                    self._notebook_id = nb["id"]
                    return self._notebook_id
            created = self.request("POST", "/api/notebooks", json_body={
                "name": self.notebook_name,
                "description": "Seraphiel Brain long-term memory (agent-distilled).",
            })
            self._notebook_id = created["id"]
            return self._notebook_id

    def search(self, query: str, *, search_type: str = "text", limit: int = _PREFETCH_LIMIT) -> list:
        payload = self.request("POST", "/api/search", json_body={
            "query": query,
            "type": search_type,
            "limit": limit,
            "search_sources": True,
            "search_notes": True,
        }, timeout=6.0)
        return list(payload.get("results") or [])

    def get_note(self, note_id: str) -> dict:
        from urllib.parse import quote
        return self.request("GET", f"/api/notes/{quote(str(note_id), safe=':')}")

    def create_note(self, title: str, content: str) -> dict:
        return self.request("POST", "/api/notes", json_body={
            "title": title,
            "content": content,
            "note_type": "ai",
            "notebook_id": self.ensure_notebook(),
        }, timeout=8.0)


# ---------------------------------------------------------------------------
# Durable write-behind queue
# ---------------------------------------------------------------------------

class _WriteQueue:
    """SQLite-backed async note writer. Survives crashes and Word downtime —
    pending rows replay on startup and retry with backoff until Word accepts
    them."""

    def __init__(self, client: _Client, db_path: Path):
        self._client = client
        self._db_path = db_path
        self._q: queue.Queue = queue.Queue()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()
        self._thread = threading.Thread(target=self._loop, name="word-writer", daemon=True)
        self._thread.start()
        for row_id, title, content in self._pending_rows():
            self._q.put((row_id, title, content))

    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self._db_path), timeout=30)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.execute("""CREATE TABLE IF NOT EXISTS pending (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT, content TEXT,
            created_at TEXT, last_error TEXT
        )""")
        conn.commit()

    def _pending_rows(self) -> list:
        conn = self._get_conn()
        return conn.execute(
            "SELECT id, title, content FROM pending ORDER BY id ASC LIMIT 200"
        ).fetchall()

    def pending_count(self) -> int:
        conn = self._get_conn()
        return int(conn.execute("SELECT COUNT(*) FROM pending").fetchone()[0])

    def enqueue(self, title: str, content: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        cur = conn.execute(
            "INSERT INTO pending (title, content, created_at) VALUES (?,?,?)",
            (title, content, now),
        )
        row_id = cur.lastrowid
        conn.commit()
        self._q.put((row_id, title, content))

    def _flush_row(self, row_id: int, title: str, content: str) -> None:
        try:
            self._client.create_note(title, content)
            conn = self._get_conn()
            conn.execute("DELETE FROM pending WHERE id = ?", (row_id,))
            conn.commit()
        except Exception as exc:
            logger.warning("Word note write failed (will retry): %s", exc)
            conn = self._get_conn()
            conn.execute("UPDATE pending SET last_error = ? WHERE id = ?", (str(exc), row_id))
            conn.commit()
            time.sleep(2)
            self._q.put((row_id, title, content))

    def _loop(self) -> None:
        while True:
            try:
                item = self._q.get(timeout=5)
                if item is _ASYNC_SHUTDOWN:
                    break
                self._flush_row(*item)
            except queue.Empty:
                continue
            except Exception as exc:
                logger.error("Word writer error: %s", exc)

    def shutdown(self) -> None:
        self._q.put(_ASYNC_SHUTDOWN)
        self._thread.join(timeout=10)


# ---------------------------------------------------------------------------
# Overlay formatter
# ---------------------------------------------------------------------------

def _compact(s: str, limit: int = _SNIPPET_CHARS) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()[:limit]


def _build_overlay(items: List[Dict[str, Any]]) -> str:
    """Format hydrated search hits for prompt injection. Each item carries its
    Word provenance id so the model can follow up with word_memory_read."""
    lines = []
    for it in items:
        title = _compact(it.get("title") or "", 80) or "(untitled)"
        snippet = _compact(it.get("snippet") or "")
        if not snippet:
            continue
        lines.append(f"- {title} · {snippet} (id: {it.get('id', '?')})")
    if not lines:
        return ""
    return "[Word Long-Term Memory]\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Main plugin class
# ---------------------------------------------------------------------------

class WordMemoryProvider(MemoryProvider):
    """Word organ memory — durable queue, notebook-scoped recall, Ward auth."""

    def __init__(self):
        self._client: Optional[_Client] = None
        self._queue: Optional[_WriteQueue] = None
        self._session_id = ""
        self._search_type = "text"
        self._healthy = False
        self._last_failure = 0.0
        self._lock = threading.Lock()

    # ── Core identity ──────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "word"

    def is_available(self) -> bool:
        # Local-first organ: defaults work for a co-located Word; downtime is
        # handled at call time, not config time.
        return True

    def get_config_schema(self) -> List[Dict[str, Any]]:
        return [
            {"key": "base_url", "description": "Word API endpoint", "default": _DEFAULT_BASE_URL, "env_var": "WORD_BASE_URL"},
            {"key": "token", "description": "Ward bearer token (blank for a local authless Word)", "secret": True, "env_var": "WORD_WARD_TOKEN"},
            {"key": "notebook", "description": "Memory notebook name", "default": _DEFAULT_NOTEBOOK, "env_var": "WORD_NOTEBOOK"},
            {"key": "search_type", "description": "Recall search mode", "default": "text", "choices": ["text", "vector"], "env_var": "WORD_SEARCH_TYPE"},
        ]

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def initialize(self, session_id: str, **kwargs) -> None:
        base_url = os.environ.get("WORD_BASE_URL", _DEFAULT_BASE_URL)
        token = (os.environ.get("WORD_WARD_TOKEN")
                 or os.environ.get("OPEN_NOTEBOOK_WARD_TOKEN") or "")
        notebook = os.environ.get("WORD_NOTEBOOK", _DEFAULT_NOTEBOOK)
        self._search_type = os.environ.get("WORD_SEARCH_TYPE", "text")
        if self._search_type not in {"text", "vector"}:
            self._search_type = "text"

        self._client = _Client(base_url, token, notebook)
        self._session_id = session_id

        from seraphiel_constants import get_seraphiel_home
        self._queue = _WriteQueue(self._client, get_seraphiel_home() / "word_queue.db")

        self._healthy = self._client.health()
        if self._healthy:
            try:
                self._client.ensure_notebook()
            except Exception as exc:
                logger.warning("Word notebook setup failed (non-fatal): %s", exc)
        else:
            self._last_failure = time.time()
            logger.warning(
                "Word organ unreachable at %s — recall degrades to silence, "
                "writes will queue locally.", base_url,
            )

    def _usable(self) -> bool:
        """Health gate with backoff: after a failure, skip Word calls for
        _HEALTH_BACKOFF_SECONDS, then re-probe."""
        if not self._client:
            return False
        with self._lock:
            if self._healthy:
                return True
            if time.time() - self._last_failure < _HEALTH_BACKOFF_SECONDS:
                return False
        healthy = self._client.health()
        with self._lock:
            self._healthy = healthy
            if not healthy:
                self._last_failure = time.time()
        return healthy

    def _mark_failed(self) -> None:
        with self._lock:
            self._healthy = False
            self._last_failure = time.time()

    def system_prompt_block(self) -> str:
        notebook = self._client.notebook_name if self._client else _DEFAULT_NOTEBOOK
        return (
            "# Word Long-Term Memory\n"
            f"Active. Durable facts live in the '{notebook}' notebook of the Word organ "
            "and persist across sessions.\n"
            "Use word_memory_save to persist facts/preferences/decisions, "
            "word_memory_search to recall (scope 'all' reaches ingested research too), "
            "word_memory_read to fetch a full note by id."
        )

    # ── Recall ─────────────────────────────────────────────────────────────

    def _hydrate(self, hit: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Turn a search hit (id + relevance) into title/snippet/id/notebook."""
        item_id = str(hit.get("id") or hit.get("item_id") or "")
        if not item_id:
            return None
        title = hit.get("title") or ""
        content = hit.get("content") or hit.get("matches") or ""
        notebook_id = None
        if item_id.startswith("note:"):
            try:
                note = self._client.get_note(item_id)
                title = note.get("title") or title
                content = note.get("content") or content
                notebook_id = note.get("notebook_id")
            except Exception as exc:
                logger.debug("Word note hydrate failed for %s: %s", item_id, exc)
        if isinstance(content, list):
            content = " … ".join(str(c) for c in content)
        return {
            "id": item_id,
            "title": str(title),
            "snippet": _compact(content),
            "notebook_id": notebook_id,
            "relevance": hit.get("relevance"),
        }

    def _search_hydrated(self, query: str, *, limit: int = _PREFETCH_LIMIT) -> List[Dict[str, Any]]:
        hits = self._client.search(query, search_type=self._search_type, limit=limit)
        out = []
        for hit in hits:
            item = self._hydrate(hit)
            if item and item["snippet"]:
                out.append(item)
        return out

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        if not query or not self._usable():
            return ""
        try:
            return _build_overlay(self._search_hydrated(query))
        except Exception as exc:
            logger.debug("Word prefetch failed (non-fatal): %s", exc)
            self._mark_failed()
            return ""

    # ── Turn sync ──────────────────────────────────────────────────────────

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "") -> None:
        """Deliberate no-op: session context stays Brain-local (WO-B2 layer
        mapping). Durable facts reach Word via on_memory_write and the
        word_memory_save tool."""

    # ── Tools ──────────────────────────────────────────────────────────────

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [SEARCH_SCHEMA, SAVE_SCHEMA, READ_SCHEMA]

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs) -> str:
        if not self._client:
            return tool_error("Word memory not initialized")
        try:
            return json.dumps(self._dispatch(tool_name, args))
        except Exception as exc:
            self._mark_failed()
            return tool_error(str(exc))

    def _dispatch(self, tool_name: str, args: dict) -> Any:
        if tool_name == "word_memory_search":
            query = args.get("query", "")
            if not query:
                return {"error": "query is required"}
            scope = args.get("scope", "memory")
            items = self._search_hydrated(query, limit=20 if scope == "memory" else 8)
            if scope == "memory":
                memory_nb = self._client.ensure_notebook()
                items = [i for i in items
                         if i.get("notebook_id") in (memory_nb, None)][:8]
            for i in items:
                i.pop("notebook_id", None)
            return {"results": items, "scope": scope}

        if tool_name == "word_memory_save":
            title = _compact(args.get("title", ""), 120)
            content = args.get("content", "")
            if not title or not content:
                return {"error": "title and content are required"}
            self._queue.enqueue(title, content)
            return {"status": "queued", "title": title,
                    "note": "Write is durable — it lands in Word now or replays when the organ is back."}

        if tool_name == "word_memory_read":
            note_id = args.get("note_id", "")
            if not note_id:
                return {"error": "note_id is required"}
            note = self._client.get_note(note_id)
            return {"id": note.get("id"), "title": note.get("title"),
                    "content": note.get("content")}

        return {"error": f"Unknown tool: {tool_name}"}

    # ── Optional hooks ─────────────────────────────────────────────────────

    def on_memory_write(
        self,
        action: str,
        target: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Mirror built-in memory writes (MEMORY.md/USER.md adds) into Word."""
        if action != "add" or not content or not self._queue:
            return
        title = f"[{target}] {_compact(content, 60)}"
        provenance = f"\n\n— mirrored from built-in {target} memory"
        if metadata and metadata.get("session_id"):
            provenance += f" (session {metadata['session_id']})"
        self._queue.enqueue(title, content + provenance)

    def shutdown(self) -> None:
        if self._queue:
            self._queue.shutdown()


def register(ctx) -> None:
    """Register Word as a memory provider plugin."""
    ctx.register_memory_provider(WordMemoryProvider())
