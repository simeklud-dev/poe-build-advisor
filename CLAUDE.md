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

## Stav (2026-07-21)

Fáze 1-3 hotové a živě ověřené end-to-end **na uživatelově reálném buildu**
na nasazené appce (ne jen na testovacím) -- viz `AI_BUILD_ADVISOR_PLAN.md`
sekce "Poznámky ke stavu" pro detaily.

Projekt teď žije v `C:\Claude\Lab\01_PROJEKTY\poe-build-advisor` (migrace z
OneDrive dokončená, OneDrive kopie zůstává jako needržovaná záloha).

**Nasazeno na Railway a funkční**, projekt `insightful-dedication`: backend
(`poe-build-advisor-production.up.railway.app`) + frontend
(`unique-presence-production-b5e6.up.railway.app`), `CORS_ORIGINS` a
`NEXT_PUBLIC_API_URL` nastavené mezi sebou. `GEMINI_API_KEY` je
nastavený a funkční. Cesta k tomu měla jednu netriviální překážku:
Railwayho build snapshot nekopíruje obsah git submodulu, takže `Dockerfile`
teď klonuje pinned commit `vendor/PathOfBuilding` přímo v build stage
(`pobsrc`), nezávisle na hostitelově podpoře submodulů -- viz README
"Nasazení (Railway)".

**Náklady a spolehlivost tool-use chatu (fáze 2), viz README "Náklady a
spolehlivost":** živé testování odhalilo a opravilo řetězec problémů --
`get_build_summary` posílal celý ~630klíčový dump (~18 600 tokenů) při
každém volání (fix: `curate_summary()`, ~30 statů), `compute_delta` u
`try_item_change`/`try_node_toggle` protahoval vnořené PoB interní tabulky
(fix: jen skalární hodnoty), chyběly nástroje `list_skills` a
`list_passive_tree` (AI neměla ŽÁDNÝ způsob, jak vidět gemy/strom -- ne
halucinace, reálná díra), a tool-use smyčka mohla vyčerpat všech
`MAX_TOOL_ITERATIONS` bez odpovědi (fix: poslední kolo nedostane nástroje,
takže MUSÍ odpovědět textem, plus vlastní vyšší `max_output_tokens`).
Přidán i efektivnější system prompt (méně zbytečných kol).

**2026-07-21: migrace z Anthropic Claude na Google Gemini free tier** --
čistě výměna LLM poskytovatele, žádná změna chování/funkcionality. Důvod:
Claude API stálo při běžném testování reálné peníze, Gemini free tier je
zdarma (klíč z aistudio.google.com, nesouvisí se spotřebitelským
předplatným Google AI Plus/Pro). Zachováno 1:1: tool-use smyčka, curated
summary, capped delta, poslední kolo bez nástrojů + vyšší
`max_output_tokens` na něm. Vypuštěný (ne přeložený): prompt caching --
Anthropic-specifická optimalizace nákladů, kterou zdarma Gemini tier
nepotřebuje. Model: `gemini-flash-lite-latest` (Googlem udržovaný
auto-update alias). Cesta k němu měla dvě další živě odhalené překážky:
`gemini-2.5-flash` (původní volba) je vyřazený pro nové API klíče (404);
`gemini-flash-latest` (druhá volba) funguje, ale aktuálně ukazuje na
`gemini-3.6-flash`, jehož zdarma denní kvóta je jen 20 requestů/den --
jeden chat tah (až `MAX_TOOL_ITERATIONS=10` kol, každé 1 Gemini call) to
sám dokáže vyčerpat, což se živě stalo (uživatel dostal "Failed to fetch"
po ~5 min čekání, backend padal s nezachyceným `429 RESOURCE_EXHAUSTED`).
Oprava má dvě části: (1) `-lite` varianta má citelně vyšší volnou kvótu
(ověřeno živě, ostatní modely vč. `gemini-2.0-flash` byly ve stejnou
chvíli taky vyčerpané), (2) `run_chat_turn()` teď `google.genai.errors.APIError`
zachytává a při 429 vrací srozumitelnou českou zprávu + vrátí
`chat_history` do stavu před tahem (žádný napůl hotový tah v historii),
místo nezachyceného pádu na holé "Internal Server Error". Živě ověřeno
end-to-end (Docker + reálný PoB engine + skutečné trade API) -- viz
`AI_BUILD_ADVISOR_PLAN.md` (projekt "POE Build helper") pro plný plán a
ověřené API tvary.

**2026-07-22: Timeless Jewel (Lethal Pride, Glorious Vanity, ...) rozbíjel
celý import buildu** -- uživatel nahlásil, že AI hlásí naprosto smyšlené
staty (Life 1620 místo 4065, špatná třída/ascendancy). Nebyl to bug v Gemini
ani v naší Python vrstvě -- nezávisle dekódovaný export přes `decode_pob_code`
ukazoval správně `Templar`/`Hierophant`, ale identický XML poslaný přes celý
pipeline (i syrový Lua bridge, obejito přes Python) vracel `Scion`/`None`.
Kořenová příčina: `GetScriptPath()` je v headless módu (`HeadlessWrapper.lua`)
natvrdo `""`, což je neškodné skoro všude, ale
`Modules/DataLegionLookUpTableHelper.lua`'s Timeless Jewel loader z toho
skládá cestu (`GetScriptPath() .. "/Data/TimelessJewelData/..."`) -- s
prázdným `scriptPath` z toho vznikne cesta od kořene souborového systému
místo od PoB `src/` adresáře, `io.open` nikdy nenajde soubor, a PoB tiše
spadne na výchozí/prázdný build MÍSTO chyby. Oprava má dvě části: (1)
`app/pob/bridge.py` teď explicitně nastavuje `POB_SRC_DIR` do prostředí
subprocessu a `pob-bridge.lua` tím přepisuje `GetScriptPath()` na reálnou
absolutní cestu; (2) i se správnou cestou by `.zip` dekomprese stejně
spadla na stejnou zeď jako sdílené kódy (`Inflate()` je taky jen prázdný
stub), takže `scripts/decompress_timeless_jewel_data.py` teď při Docker
buildu předpřipraví `.bin` verze (PoB engine sám preferuje `.bin` před
`.zip`, když existuje a je aktuální -- stačilo mu ho dát). Živě ověřeno na
uživatelově reálném buildu (Templar/Hierophant se socketed Lethal Pride) --
po opravě rezisty/ES/spell suppression sedí do puntíku s desktop PoB, drobné
zbytkové rozdíly v Life/Armour/Block jsou normální odchylka z Configuration
tabu (předpoklady o aktivních buffech), ne bug.

**Známý drobný nedostatek (TODO, uživatel vědomě odložil na později):**
`search_trade_items` nevrací hotový klikatelný `trade_url`, jen `query_id`
-- AI proto trade linky občas nepřesně domýšlí. Viz README "Trade
integrace".

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
- **`HeadlessWrapper.lua` stubuje víc věcí naprázdno, než jen kompresi** --
  `GetScriptPath()` vrací natvrdo `""`. Neškodné skoro všude, ale Timeless
  Jewel loader (`DataLegionLookUpTableHelper.lua`) z toho skládá cestu k
  `Data/TimelessJewelData/*.zip|.bin` a s prázdným `scriptPath` nikdy nenajde
  soubor -- PoB pak TICHE naimportuje prázdný/výchozí build místo chyby (viz
  "Stav" výše). `pob-bridge.lua` teď `GetScriptPath()` přepisuje na reálnou
  cestu (`POB_SRC_DIR` z prostředí, nastaveno v `app/pob/bridge.py`) a
  `scripts/decompress_timeless_jewel_data.py` při Docker buildu předpřipraví
  `.bin` verze jewel dat (obchází stejně prázdný `Inflate()` stub). Obecná
  lekce: když PoB engine vrátí nesmyslné/výchozí staty místo chyby, podezřívej
  nejdřív tichý fallback z nějakého dalšího stubovaného headless API, ne
  parsing bug v `decode.py` nebo Gemini.
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
- **Nová AI tool = nový bridge handler, ne pokus o odvození ze `get_summary`**:
  `get_summary`/`get_breakdown` pokrývají jen calc výstup, ne skilly
  (`build.skillsTab.socketGroupList`) ani strom (`build.spec.allocNodes`) --
  na obojí byl potřeba samostatný handler (`list_skills`,
  `list_passive_tree`). Když uživatel řekne "AI nevidí X", nejdřív zkontroluj,
  jestli pro X vůbec existuje nástroj, než to řešíš jako parsing/prompt bug.
- **Payload každého nového nástroje měř, než ho nasadíš** -- `get_build_summary`
  i `compute_delta` vypadaly nevinně, ale oba dokázaly poslat desítky až
  stovky KB do jednoho tool_result (viz README "Náklady a spolehlivost").
  Vždy zkontroluj velikost výstupu na reálném (ne jen testovacím) buildu.

## Poznámka k údržbě

Pokud se v průběhu vývoje změní zadání nebo padne nové rozhodnutí,
aktualizuj `AI_BUILD_ADVISOR_PLAN.md` (v "POE Build helper"), ať zůstane
platným zdrojem pravdy pro projekt -- stejná konvence jako `SPEC.md` u
`poe-build-finder`.
