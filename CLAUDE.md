# PoE Build Advisor

AI bot nad reálným Path of Building enginem. Kompletní kontext, architektura
a fázový plán: `AI_BUILD_ADVISOR_PLAN.md` v sesterském projektu
"POE Build helper" (`../POE Build helper/AI_BUILD_ADVISOR_PLAN.md`) -- **vždy
si ho přečti před prací na nové části projektu**.

## Základní fakta o projektu

- **Model:** hobby projekt, nekomerční, druhý Railway projekt vedle
  `poe-build-finder` (ne rozšíření toho projektu).
- **Vývoj:** samostatně přes Claude Code, bez externího vývojáře.
- **Jádro:** vendorovaný `vendor/PathOfBuilding` (git submodul, větev `dev`)
  spouštěný headless přes `apps/api/lua/pob-bridge.lua` -- AI nikdy nevymýšlí
  čísla, jen komentuje/navrhuje nad tím, co spočítal skutečný PoB engine.

## Tech stack

- Backend: FastAPI (Python 3.12) + subprocess bridge do LuaJIT
- Frontend: Next.js (App Router), React 19
- Žádná databáze -- session (fáze 2) je in-memory (`app/pob/session.py`,
  `SESSIONS`), sedí na jeden proces/uvicorn worker; restart serveru = ztráta
  rozjetých chatů. Fáze 1 (`/advisor/analyze`) zůstává úplně bezstavová.

## Stav (2026-07-20)

Fáze 1-3 hotové a živě ověřené end-to-end (Docker + prohlížeč + reálný
`ANTHROPIC_API_KEY` chat + reálné PoE trade API) -- viz
`AI_BUILD_ADVISOR_PLAN.md` sekce "Poznámky ke stavu" pro detaily.

Projekt teď žije v `C:\Claude\Lab\01_PROJEKTY\poe-build-advisor` (migrace z
OneDrive dokončená, OneDrive kopie zůstává jako needržovaná záloha).

**Nasazeno na Railway**, projekt `insightful-dedication`: backend
(`poe-build-advisor-production.up.railway.app`) + frontend
(`unique-presence-production-b5e6.up.railway.app`), `CORS_ORIGINS` a
`NEXT_PUBLIC_API_URL` nastavené mezi sebou, `/advisor/analyze` ověřeno živě
z prohlížeče proti reálnému buildu. Cesta k tomu měla jednu netriviální
překážku: Railwayho build snapshot nekopíruje obsah git submodulu, takže
`Dockerfile` teď klonuje pinned commit `vendor/PathOfBuilding` přímo v
build stage (`pobsrc`), nezávisle na hostitelově podpoře submodulů -- viz
README "Nasazení (Railway)". `ANTHROPIC_API_KEY` na backendu **zatím není
nastavený** -- uživatel ho musí doplnit sám ve Variables (nikdy ho nezadávej
za něj).

## Klíčová pravidla

- **Nikdy nefetchovat pobb.in/pastebin odkazy automaticky** -- jejich
  `robots.txt` to pro potřebné endpointy zakazuje (stejné rozhodnutí jako v
  `poe-build-finder`). Uživatel vždy vkládá text kódu, ne odkaz --
  `apps/api/app/routers/advisor.py::AnalyzeRequest.reject_links` to hlídá.
- **Komprese kódu (base64+zlib) se řeší v Pythonu** (`app/pob/decode.py`),
  nikdy v Lua bridge -- `Deflate`/`Inflate` jsou v headless PoB
  (`HeadlessWrapper.lua`) jen prázdné TODO stuby, skutečná komprese je v
  kompilované runtime knihovně, kterou headless prostředí nemá.
  Do/z `pob-bridge.lua` chodí vždy jen čisté XML.
- **Bridge dumpuje celé PoB output tabulky** (`sanitize()` v
  `pob-bridge.lua`), nehardkóduje konkrétní jména statů -- necitlivé na
  přejmenování polí mezi ligami.
- **Trade API (fáze 3, hotovo):** `app/trade/` volá veřejné, nepřihlášené
  trade API -- PoB nepoužívá `POESESSID` (to byl chybný předpoklad
  původního plánu), jen volitelný OAuth Bearer token, který request bez
  něj stejně propustí (jen přísnější IP rate limit). Rate limity se čtou
  živě z `X-Rate-Limit-*` hlaviček (`app/trade/rate_limiter.py`, port
  `TradeQueryRateLimiter.lua`), stat ID živě z `/api/trade/data/stats` --
  nikde nic natvrdo. Implementováno jen prosté "and" min/max filtrování,
  ne PoB vlastní vážený DPS/Life search (`TradeQueryGenerator.lua`, 1300+
  řádků) -- vědomé zúžení rozsahu pro MVP.
- **Aktuálnost enginu:** `git submodule update --remote` + smoke test
  (`scripts/smoke-test-bridge.sh`) před každým redeploy po nové lize -- viz
  plán, sekce "Aktuálnost enginu při změnách ligy".

## Poznámka k údržbě

Pokud se v průběhu vývoje změní zadání nebo padne nové rozhodnutí,
aktualizuj `AI_BUILD_ADVISOR_PLAN.md` (v "POE Build helper"), ať zůstane
platným zdrojem pravdy pro projekt -- stejná konvence jako `SPEC.md` u
`poe-build-finder`.
