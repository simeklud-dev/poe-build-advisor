# PoE Build Advisor

AI bot nad **skutečným Path of Building enginem**: vložíš PoB export kód
(vybavení, strom, skilly) a dostaneš rozbor buildu spočtený reálným PoB
enginem (headless), ne odhadem LLM. Druhý, samostatný projekt vedle
[`poe-build-finder`](../poe-build-finder) (meta-vyhledávač buildů) -- viz
`AI_BUILD_ADVISOR_PLAN.md` v projektu "POE Build helper" pro plný kontext,
architekturu a fázový plán.

**Stav: fáze 2 hotová a plně ověřená end-to-end** (co-by-kdyby simulace +
chat s reálným `ANTHROPIC_API_KEY`) -- import buildu, reálné staty,
`try_item_change`/`try_node_toggle` s tool-use smyčkou přes Claude
(`/advisor/session/{id}/chat`), export upraveného buildu. Fáze 3 (trade
integrace) zatím není.

## Struktura repozitáře

```
poe-build-advisor/
├── vendor/PathOfBuilding/   # git submodul -> PathOfBuildingCommunity/PathOfBuilding (dev)
├── apps/
│   ├── api/                 # FastAPI backend
│   │   ├── app/
│   │   │   ├── pob/         # decode.py, bridge.py (Lua subprocess klient), session.py (fáze 2: perzistentní session)
│   │   │   ├── routers/     # advisor.py (viz "API endpointy" níže)
│   │   │   ├── advisor_llm.py    # fáze 1: volitelný jednorázový komentář od Claude
│   │   │   ├── advisor_tools.py  # fáze 2: nástroje pro Claude (tool-use) + compute_delta
│   │   │   └── advisor_chat.py   # fáze 2: tool-use smyčka (max 8 kroků)
│   │   └── lua/pob-bridge.lua  # JSON bridge nad HeadlessWrapper.lua (kopíruje se do vendor/.../src při buildu)
│   └── web/                 # Next.js frontend (/advisor -- rychlá analýza nebo chat session)
├── Dockerfile                # Python + LuaJIT, build kontext = kořen repa (ne apps/api!)
└── scripts/smoke-test-bridge.sh
```

### API endpointy

- `POST /advisor/analyze` -- fáze 1, bezstavové: `{code}` → `{meta, summary, commentary}`.
- `POST /advisor/session` -- fáze 2, založí session s perzistentním bridge
  subprocessem: `{code}` → `{session_id, meta, summary}`.
- `POST /advisor/session/{id}/chat` -- `{message}` → `{reply, summary}`;
  Claude v tool-use smyčce zkouší `try_item_change`/`try_node_toggle` a
  ověřuje si je na reálném enginu, než odpoví.
- `POST /advisor/session/{id}/export` -- `{}` → `{code}` (nový PoB export kód
  pro re-import do desktop appky).
- `DELETE /advisor/session/{id}` -- zavře session (bridge subprocess).

## Proč headless PoB engine, ne vlastní výpočet

PoE má extrémně komplexní damage/defense matematiku (konverze typů, increased
vs. more, EHP po typech zásahu...). Místo abychom to reimplementovali (a
riskovali, že se to rozejde s realitou), spouštíme přímo **PoB engine**
(Lua/LuaJIT) headless na serveru -- viz `src/HeadlessWrapper.lua` ve
vendorovaném submodulu. Čísla, která AI komentuje, jsou vždy skutečně
spočtená, nikdy odhadnutá.

## Lokální vývoj

### Předpoklady

- Docker Desktop -- backend potřebuje LuaJIT, který se skládá v
  multi-stage Dockerfile (mirror `vendor/PathOfBuilding/Dockerfile`); mimo
  Docker běžet nepůjde, pokud si LuaJIT nenainstaluješ ručně.
- Node 18+ (frontend).
- Git submodule: po `git clone` spusť `git submodule update --init --recursive`.

### Backend (Docker)

```bash
docker build -t poe-build-advisor-api .
docker run --rm -p 8000:8000 --env-file apps/api/.env poe-build-advisor-api
```

Zkontroluj [http://localhost:8000/health](http://localhost:8000/health).

Smoke test bridge skriptu (ověří, že PoB engine reálně počítá) proti
ukázkovému buildu z `vendor/PathOfBuilding/spec/TestBuilds/`:

```bash
docker run --rm poe-build-advisor-api sh /app/scripts/smoke-test-bridge.sh
```

### Frontend

```bash
cd apps/web
cp .env.local.example .env.local
npm install
npm run dev
```

Otevři [http://localhost:3000](http://localhost:3000) (backend musí běžet na
adrese z `NEXT_PUBLIC_API_URL`).

## Aktuálnost PoB enginu při nové lize

Viz `AI_BUILD_ADVISOR_PLAN.md`, sekce "Aktuálnost enginu při změnách ligy" --
zkráceně: `git submodule update --remote`, rebuild image, spustit
`scripts/smoke-test-bridge.sh`, teprve pak redeploy. Žádná herní data ani
výpočetní logika se neudržují ručně v tomto repu.

## Nasazení (Railway)

Na rozdíl od `poe-build-finder` (Root Directory = `apps/api`, Nixpacks) tenhle
backend **musí** stavět z kořene repa přes vlastní `Dockerfile`, protože
potřebuje jak `apps/api`, tak `vendor/PathOfBuilding`:

1. Backend service -- "New" → "GitHub Repo", Root Directory = kořen repa,
   Railway detekuje `Dockerfile` automaticky (nebo nastav ručně "Dockerfile
   Path" na `Dockerfile` v service settings). Env: `CORS_ORIGINS`,
   volitelně `ANTHROPIC_API_KEY`.
2. Frontend service -- Root Directory `apps/web`, env
   `NEXT_PUBLIC_API_URL` = URL backend služby.
3. Railway musí mít povolené git submoduly při checkoutu (ověř v service
   settings -- pokud ne, bude potřeba submodul vendorovat jinak, např. přes
   build-time `git submodule update --init` v Dockerfile).

## Poznámka

Tento web není přidružen ke Grinding Gear Games ani jimi podporován.
