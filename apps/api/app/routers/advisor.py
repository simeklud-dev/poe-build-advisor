from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from app.advisor_chat import AdvisorChatError, run_chat_turn, run_free_chat_turn
from app.advisor_llm import summarize_build
from app.advisor_tools import dispatch_tool
from app.config import settings
from app.free_chat_session import FREE_CHAT_SESSIONS, FreeChatSessionNotFoundError
from app.pob.bridge import PobBridge, PobBridgeError
from app.pob.decode import decode_pob_code
from app.pob.session import SESSIONS, SessionNotFoundError

router = APIRouter(prefix="/advisor", tags=["advisor"])


def _validate_pob_code(v: str) -> str:
    # Stejné pravidlo jako v poe-build-finder/apps/api/app/pob/decode.py:
    # nikdy nefetchujeme pobb.in/pastebin/... odkazy (jejich robots.txt to
    # zakazuje pro potřebné endpointy) -- uživatel musí vložit přímo
    # export kód (Export Build -> Generate code), ne odkaz na něj.
    stripped = v.strip()
    if not stripped:
        raise ValueError("Chybí PoB export kód.")
    if stripped.startswith("http://") or stripped.startswith("https://"):
        raise ValueError(
            "Vlož přímo PoB export kód (Export Build -> Generate code), "
            "ne odkaz na pobb.in/pastebin -- ty se z právních důvodů "
            "(robots.txt) nestahují automaticky."
        )
    return stripped


class AnalyzeRequest(BaseModel):
    code: str

    @field_validator("code")
    @classmethod
    def reject_links(cls, v: str) -> str:
        return _validate_pob_code(v)


class SessionCreateRequest(BaseModel):
    code: str

    @field_validator("code")
    @classmethod
    def reject_links(cls, v: str) -> str:
        return _validate_pob_code(v)


class ChatRequest(BaseModel):
    message: str


class FreeChatRequest(BaseModel):
    message: str


@router.post("/analyze")
def analyze(payload: AnalyzeRequest) -> dict:
    """Fáze 1: jednorázová bezstavová analýza (bez tool-use smyčky, bez session)."""
    try:
        xml = decode_pob_code(payload.code)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Neplatný PoB export kód: {exc}") from exc

    try:
        with PobBridge(settings.lua_executable, settings.pob_src_dir, settings.pob_bridge_timeout_seconds) as bridge:
            meta = bridge.call("import_xml", {"xml": xml})
            summary = bridge.call("get_summary")
    except PobBridgeError as exc:
        raise HTTPException(status_code=502, detail=f"Path of Building engine selhal: {exc}") from exc

    commentary = summarize_build(summary)

    return {"meta": meta, "summary": summary, "commentary": commentary}


@router.post("/session")
def create_session(payload: SessionCreateRequest) -> dict:
    """Fáze 2: založí session s perzistentním bridge subprocessem pro chat + co-by-kdyby simulace."""
    try:
        xml = decode_pob_code(payload.code)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Neplatný PoB export kód: {exc}") from exc

    try:
        session = SESSIONS.create(xml)
    except PobBridgeError as exc:
        raise HTTPException(status_code=502, detail=f"Path of Building engine selhal: {exc}") from exc

    summary = dispatch_tool(session, "get_build_summary", {})
    return {"session_id": session.id, "meta": session.meta, "summary": summary}


@router.post("/session/{session_id}/chat")
def chat(session_id: str, payload: ChatRequest) -> dict:
    try:
        session = SESSIONS.get(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session nenalezena nebo vypršela -- začni znovu vložením PoB kódu.")

    with session.lock:
        try:
            reply = run_chat_turn(session, payload.message)
        except AdvisorChatError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except PobBridgeError as exc:
            raise HTTPException(status_code=502, detail=f"Path of Building engine selhal: {exc}") from exc
        summary = dispatch_tool(session, "get_build_summary", {})

    return {"reply": reply, "summary": summary}


@router.post("/session/{session_id}/export")
def export_session(session_id: str) -> dict:
    try:
        session = SESSIONS.get(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session nenalezena nebo vypršela.")

    with session.lock:
        result = dispatch_tool(session, "export_build", {})
    return result


@router.delete("/session/{session_id}")
def close_session(session_id: str) -> dict:
    SESSIONS.close(session_id)
    return {"status": "closed"}


@router.post("/freechat")
def create_free_chat() -> dict:
    """Brainstorm chat bez nahraného buildu -- viz app/free_chat_session.py.
    Žádný bridge subprocess, takže na rozdíl od /session je tohle okamžité."""
    session = FREE_CHAT_SESSIONS.create()
    return {"session_id": session.id}


@router.post("/freechat/{session_id}/chat")
def free_chat(session_id: str, payload: FreeChatRequest) -> dict:
    try:
        session = FREE_CHAT_SESSIONS.get(session_id)
    except FreeChatSessionNotFoundError:
        raise HTTPException(status_code=404, detail="Chat session nenalezena nebo vypršela -- začni znovu.")

    with session.lock:
        try:
            reply = run_free_chat_turn(session.chat_history, payload.message)
        except AdvisorChatError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {"reply": reply}


@router.delete("/freechat/{session_id}")
def close_free_chat(session_id: str) -> dict:
    FREE_CHAT_SESSIONS.close(session_id)
    return {"status": "closed"}
