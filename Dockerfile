# Backend image: Python (FastAPI) + LuaJIT (Path of Building headless engine).
#
# Build context MUST be the repo root (not apps/api!) -- this image needs both
# apps/api and vendor/PathOfBuilding. On Railway: set the backend service's
# Root Directory to the repo root and point it at this Dockerfile explicitly,
# unlike the apps/api-rooted Nixpacks setup in the sibling poe-build-finder
# project (see README.md, "Nasazeni (Railway)").
#
# LuaJIT build stages mirror vendor/PathOfBuilding/Dockerfile (Alpine + lua5.1
# + luarocks + luajit + luautf8) -- see AI_BUILD_ADVISOR_PLAN.md (in the
# sibling "POE Build helper" project) for why we run PoB's own engine instead
# of reimplementing its damage/defence calculations.

# Railway's build snapshot does not check out git submodule contents (the
# COPY vendor/PathOfBuilding/... steps below used to fail with "not found"
# because vendor/PathOfBuilding was an empty dir in the uploaded context even
# though it builds fine locally where the submodule is checked out). Fetch
# the exact pinned submodule commit directly instead of depending on the
# build context -- works the same locally and on any CI/host regardless of
# submodule checkout support. Keep this commit in sync with
# `git -C vendor/PathOfBuilding rev-parse HEAD`.
FROM alpine:3.18 AS pobsrc
RUN apk add --no-cache git
RUN git clone https://github.com/PathOfBuildingCommunity/PathOfBuilding.git /opt/pob \
	&& cd /opt/pob && git checkout 03ae46279c6570facabc5fb65ec5d171edc339fd

FROM alpine:3.18 AS luabuild
RUN apk add --no-cache cmake readline-dev build-base tar git wget unzip curl openssl

WORKDIR /opt
RUN wget https://www.lua.org/ftp/lua-5.1.5.tar.gz && tar -xf lua-5.1.5.tar.gz \
	&& cd lua-5.1.5 && make linux && make install

RUN wget https://luarocks.org/releases/luarocks-3.7.0.tar.gz && tar -xf luarocks-3.7.0.tar.gz \
	&& cd luarocks-3.7.0 && ./configure && make && make install

RUN git clone https://github.com/LuaJIT/LuaJIT \
	&& cd LuaJIT && git checkout 871db2c84ecefd70a850e03a6c340214a81739f0 && make && make install

# luautf8 is a compiled rock (Common.lua needs it for unicode-safe string ops
# on item/mod text) -- everything else PoB's engine needs (dkjson, base64,
# sha1/sha2, xml) is pure Lua under vendor/PathOfBuilding/runtime/lua, copied
# in below, no compilation needed.
RUN luarocks install luautf8 0.1.6-1

FROM python:3.12-alpine
RUN apk add --no-cache readline libgcc

COPY --from=luabuild /usr/local/bin/luajit* /usr/local/bin/
COPY --from=luabuild /usr/local/lib/lua /usr/local/lib/lua
COPY --from=luabuild /usr/local/share/lua /usr/local/share/lua
COPY --from=luabuild /usr/local/lib/luarocks /usr/local/lib/luarocks

WORKDIR /app

COPY apps/api/requirements.txt apps/api/requirements.txt
RUN pip install --no-cache-dir -r apps/api/requirements.txt

# Vendored PoB engine (pinned commit, fetched in the pobsrc stage above) +
# our bridge script copied alongside HeadlessWrapper.lua, exactly where it
# expects to be run from (see .busted in the submodule: directory = "src").
COPY --from=pobsrc /opt/pob/src ./vendor/PathOfBuilding/src
COPY --from=pobsrc /opt/pob/runtime ./vendor/PathOfBuilding/runtime
COPY apps/api/lua/pob-bridge.lua ./vendor/PathOfBuilding/src/pob-bridge.lua

# Sample builds only (~600KB), so scripts/smoke-test-bridge.sh can run
# straight inside this image after every league-update rebuild, as documented
# in its own header comment -- not the full spec/ dir (busted itself isn't
# vendored here, this image never runs the Lua test suite).
COPY --from=pobsrc /opt/pob/spec/TestBuilds ./vendor/PathOfBuilding/spec/TestBuilds

COPY apps/api/app ./apps/api/app
COPY scripts ./scripts

# Pre-decompress Timeless Jewel data (needed for any build socketing e.g.
# Lethal Pride/Glorious Vanity) -- see scripts/decompress_timeless_jewel_data.py
# for why headless PoB can't do this itself at runtime.
RUN python scripts/decompress_timeless_jewel_data.py

ENV PYTHONPATH=/app/apps/api
ENV LUA_EXECUTABLE=luajit
ENV POB_SRC_DIR=/app/vendor/PathOfBuilding/src
ENV PORT=8000
EXPOSE 8000

WORKDIR /app/apps/api
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port $PORT"]
