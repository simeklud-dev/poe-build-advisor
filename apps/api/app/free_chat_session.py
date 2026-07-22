"""In-memory store for build-less 'brainstorm' chat sessions.

Unlike `app/pob/session.py::PobSession`, these have no PoB bridge subprocess
-- there's no build loaded, so nothing to compute against. Used by
`advisor_chat.py::run_free_chat_turn` for "suggest me a build for skill X"
style conversations before the user has an export code to analyze.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FreeChatSession:
    id: str
    lock: threading.Lock = field(default_factory=threading.Lock)
    chat_history: list[dict[str, Any]] = field(default_factory=list)
    last_used: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.last_used = time.time()


class FreeChatSessionNotFoundError(KeyError):
    pass


class FreeChatSessionStore:
    def __init__(self, max_sessions: int = 100, idle_timeout_seconds: float = 1800.0):
        self._sessions: dict[str, FreeChatSession] = {}
        self._store_lock = threading.Lock()
        self.max_sessions = max_sessions
        self.idle_timeout_seconds = idle_timeout_seconds

    def create(self) -> FreeChatSession:
        self._evict_idle()
        session = FreeChatSession(id=str(uuid.uuid4()))
        with self._store_lock:
            if len(self._sessions) >= self.max_sessions:
                oldest_id = min(self._sessions, key=lambda sid: self._sessions[sid].last_used)
                self._sessions.pop(oldest_id)
            self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> FreeChatSession:
        with self._store_lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise FreeChatSessionNotFoundError(session_id)
        session.touch()
        return session

    def close(self, session_id: str) -> None:
        with self._store_lock:
            self._sessions.pop(session_id, None)

    def _evict_idle(self) -> None:
        cutoff = time.time() - self.idle_timeout_seconds
        with self._store_lock:
            stale = [sid for sid, s in self._sessions.items() if s.last_used < cutoff]
            for sid in stale:
                self._sessions.pop(sid)


# No subprocess to bound this on (unlike PobSessionStore), so a higher cap is fine.
FREE_CHAT_SESSIONS = FreeChatSessionStore()
