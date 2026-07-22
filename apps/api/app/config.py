from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Lokálně (celý monorepo pohromadě) je config.py na apps/api/app/config.py, takže
# kořen repa je o 3 úrovně výš -- stejný vzor jako v poe-build-finder/apps/api/app/config.py.
# Na hostingu (Railway), kde je tenhle backend nasazený z Dockerfile s build kontextem
# v kořeni repa (potřebuje vendor/PathOfBuilding, ne jen apps/api), žádný .env soubor
# nenačítáme a spoléháme čistě na proměnné prostředí z UI hostingu / Dockerfile ENV.
_here = Path(__file__).resolve()
_repo_root = _here.parents[3] if len(_here.parents) > 3 else None
REPO_ROOT_ENV_FILE = (_repo_root / ".env") if _repo_root else None
_default_pob_src_dir = str(_repo_root / "vendor" / "PathOfBuilding" / "src") if _repo_root else "vendor/PathOfBuilding/src"


class Settings(BaseSettings):
    cors_origins: str = "http://localhost:3000"

    # Headless Path of Building engine -- viz AI_BUILD_ADVISOR_PLAN.md
    # (projekt "POE Build helper"). LuaJIT interpret + cesta ke
    # zavendorovanému `vendor/PathOfBuilding/src` (git submodul).
    lua_executable: str = "luajit"
    pob_src_dir: str = _default_pob_src_dir
    pob_bridge_timeout_seconds: float = 30.0

    # AI komentář/chat nad staty spočtenými bridge (app/advisor_llm.py,
    # app/advisor_chat.py) -- Google Gemini free tier (zdarma API klíč z
    # aistudio.google.com, žádné Anthropic tokeny). Bez klíče endpointy
    # fungují dál, jen bez AI komentáře/chatu.
    gemini_api_key: str = ""
    # gemini-2.5-flash je vyřazený pro nové API klíče (404 na živém testu).
    # gemini-flash-latest fungoval, ale živě se ukázalo, že aktuálně ukazuje
    # na gemini-3.6-flash, jehož denní zdarma kvóta je jen 20 requestů/den --
    # jeden chat tah (až MAX_TOOL_ITERATIONS kol) to sám umí vyčerpat.
    # gemini-flash-lite-latest (taky Googlem udržovaný auto-update alias, ne
    # pevná verze) měl při stejném živém testu volnou kvótu a tool-calling
    # funguje spolehlivě stejně -- viz AI_BUILD_ADVISOR_PLAN.md.
    gemini_model: str = "gemini-flash-lite-latest"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT_ENV_FILE) if REPO_ROOT_ENV_FILE else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
