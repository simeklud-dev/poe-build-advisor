# PoE Build Advisor

AI bot nad **skutečným Path of Building enginem**: vložíš PoB export kód
(vybavení, strom, skilly) a dostaneš rozbor buildu spočtený reálným PoB
enginem (headless), ne odhadem LLM. Druhý, samostatný projekt vedle
[`poe-build-finder`](../poe-build-finder) (meta-vyhledávač buildů) -- viz
`AI_BUILD_ADVISOR_PLAN.md` v projektu "POE Build helper" pro plný kontext,
architekturu a fázový plán.

**Stav: fáze 1 (grounding bez simulace)** -- import buildu + reálné staty +
volitelný jednorázový komentář od Claude. Žádná co-by-kdyby simulace ani
trade integrace zatím (fáze 2-3).

## Struktura repozitáře

```
poe-build-advisor/
├── vendor/PathOfBuilding/   # git submodul -> PathOfBuildingCommunity/PathOfBuilding (dev)
├── apps/
│   ├── api/                 # FastAPI backend
│   │   ├── app/
│   │   │   ├── pob/         # decode.py (base64+zlib <-> XML), bridge.py (Lua subprocess klient)
│   │   │   ├── routers/     # advisor.py (POST /advisor/analyze)
│   │   │   └── advisor_llm.py  # volitelný Claude komentář
│   │   └── lua/pob-bridge.lua  # JSON bridge nad HeadlessWrapper.lua (kopíruje se do vendor/.../src při buildu)
│   └── web/                 # Next.js frontend (/advisor)
├── Dockerfile                # Python + LuaJIT, build kontext = kořen repa (ne apps/api!)
└── scripts/smoke-test-bridge.sh
```

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
