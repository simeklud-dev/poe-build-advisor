"""Session management pro co-by-kdyby simulaci (fáze 2).

Na rozdíl od fáze 1 (`PobBridge` jako per-request context manager v
`/advisor/analyze`), tady bridge subprocess zůstává naživu napříč více HTTP
požadavky téhož chatu -- jinak by `try_item_change`/`try_node_toggle` nemohly
stavět jedna na druhé (AI zkusí item, podívá se na deltu, zkusí jiný...).

In-memory store (`SESSIONS`) -- sedí na jeden proces/instanci backendu; při
restartu serveru se session ztratí, uživatel musí znovu vložit PoB kód. Pro
hobby projekt s jedním uživatelem je to přiměřené; kdyby to bylo potřeba
přežít restart, řešilo by se to perzistencí XML stavu (`export_xml`), ne
bridge subprocessem samotným.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.config import settings
from app.pob.bridge import PobBridge


@dataclass
class PobSession:
    id: str
    bridge: PobBridge
    meta: dict[str, Any]
    lock: threading.Lock = field(default_factory=threading.Lock)
    chat_history: list[dict[str, Any]] = field(default_factory=list)
    last_used: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.last_used = time.time()


class SessionNotFoundError(KeyError):
    pass


class PobSessionStore:
    def __init__(self, max_sessions: int = 20, idle_timeout_seconds: float = 1800.0):
        self._sessions: dict[str, PobSession] = {}
        self._store_lock = threading.Lock()
        self.max_sessions = max_sessions
        self.idle_timeout_seconds = idle_timeout_seconds

    def create(self, xml: str, name: str | None = None) -> PobSession:
        self._evict_idle()
        bridge = PobBridge(settings.lua_executable, settings.pob_src_dir, settings.pob_bridge_timeout_seconds)
        bridge.start()
        try:
            meta = bridge.call("import_xml", {"xml": xml, "name": name or "session"})
        except Exception:
            bridge.stop()
            raise

        session = PobSession(id=str(uuid.uuid4()), bridge=bridge, meta=meta)
        with self._store_lock:
            if len(self._sessions) >= self.max_sessions:
                self._evict_oldest_locked()
            self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> PobSession:
        with self._store_lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        session.touch()
        return session

    def close(self, session_id: str) -> None:
        with self._store_lock:
            session = self._sessions.pop(session_id, None)
        if session is not None:
            session.bridge.stop()

    def _evict_idle(self) -> None:
        cutoff = time.time() - self.idle_timeout_seconds
        with self._store_lock:
            stale = [sid for sid, s in self._sessions.items() if s.last_used < cutoff]
            for sid in stale:
                session = self._sessions.pop(sid)
                session.bridge.stop()

    def _evict_oldest_locked(self) -> None:
        """Caller must hold self._store_lock."""
        if not self._sessions:
            return
        oldest_id = min(self._sessions, key=lambda sid: self._sessions[sid].last_used)
        session = self._sessions.pop(oldest_id)
        session.bridge.stop()


# Jeden proces = jeden store; v souladu s tím, že tenhle backend počítá s
# jedním uvicorn workerem (viz Procfile) -- víc workerů by mělo každý svůj
# store a session by "zmizela", kdyby request skončil u jiného workeru.
SESSIONS = PobSessionStore()
