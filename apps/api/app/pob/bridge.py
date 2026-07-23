"""Python klient pro `apps/api/lua/pob-bridge.lua`.

Spouští headless Path of Building (LuaJIT) jako subprocess a mluví s ním přes
řádkový JSON protokol na stdin/stdout -- viz komentář v pob-bridge.lua pro
přesný tvar zpráv. Jedna instance `PobBridge` = jeden subprocess = jeden
načtený build; není thread-safe, volající si drží jeden bridge na
request/session.

Fáze 1 (viz AI_BUILD_ADVISOR_PLAN.md) používá bridge jen jednorázově na
request (`import_xml` + `get_summary`, pak proces zavřít). Fáze 2 (co-by-kdyby
simulace) bude držet stejný subprocess otevřený napříč více voláními v rámci
jedné chat session, aby změny (`try_item_change` apod.) zůstaly mezi voláními
zachované -- proto je rozhraní navržené jako context manager s perzistentním
procesem, ne jako "jedno volání = jeden proces" pomocník.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any


class PobBridgeError(RuntimeError):
    """Bridge proces vrátil ok=false, nebo se choval neočekávaně (crash, EOF, timeout)."""


class PobBridge:
    def __init__(self, lua_executable: str, pob_src_dir: str | Path, timeout: float = 30.0):
        self._lua_executable = lua_executable
        self._pob_src_dir = Path(pob_src_dir)
        self._timeout = timeout
        self._process: subprocess.Popen[str] | None = None

    def start(self) -> "PobBridge":
        # HeadlessWrapper.lua stubs GetScriptPath() to "" (there's no real
        # install dir in headless mode) -- harmless for most of PoB, but
        # Modules/DataLegionLookUpTableHelper.lua's Timeless Jewel loader
        # concatenates it straight into a path (GetScriptPath() .. "/Data/
        # TimelessJewelData/..."), so an empty scriptPath silently produces a
        # filesystem-root path instead of one relative to PoB's actual src
        # dir, and every file lookup there fails. pob-bridge.lua overrides
        # GetScriptPath() to read this env var back -- set explicitly here
        # (not just relying on it already being in os.environ) so this works
        # the same regardless of how POB_SRC_DIR reached this process.
        env = {**os.environ, "POB_SRC_DIR": str(self._pob_src_dir.resolve())}
        self._process = subprocess.Popen(
            [self._lua_executable, "pob-bridge.lua"],
            cwd=self._pob_src_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )
        return self

    def stop(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        try:
            if process.stdin:
                process.stdin.close()
            process.wait(timeout=self._timeout)
        except subprocess.TimeoutExpired:
            process.kill()

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def __enter__(self) -> "PobBridge":
        return self.start()

    def __exit__(self, *exc_info: object) -> None:
        self.stop()

    def call(self, cmd: str, args: dict[str, Any] | None = None) -> Any:
        process = self._process
        if process is None or process.stdin is None or process.stdout is None:
            raise PobBridgeError("bridge process is not running (use PobBridge as a context manager)")

        process.stdin.write(json.dumps({"cmd": cmd, "args": args or {}}) + "\n")
        process.stdin.flush()

        line = process.stdout.readline()
        if not line:
            stderr = process.stderr.read() if process.stderr else ""
            raise PobBridgeError(f"bridge process closed unexpectedly (cmd={cmd}). stderr tail: {stderr[-2000:]}")

        try:
            response = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PobBridgeError(f"bridge returned non-JSON output for cmd={cmd}: {line[:500]!r}") from exc

        if not response.get("ok"):
            raise PobBridgeError(f"{cmd} failed: {response.get('error')}")
        return response.get("result")
