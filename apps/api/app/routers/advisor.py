from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from app.advisor_llm import summarize_build
from app.config import settings
from app.pob.bridge import PobBridge, PobBridgeError
from app.pob.decode import decode_pob_code

router = APIRouter(prefix="/advisor", tags=["advisor"])


class AnalyzeRequest(BaseModel):
    code: str

    @field_validator("code")
    @classmethod
    def reject_links(cls, v: str) -> str:
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


@router.post("/analyze")
def analyze(payload: AnalyzeRequest) -> dict:
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
