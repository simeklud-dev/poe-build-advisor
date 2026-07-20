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

FROM alpine:3.18 AS luabuild
RUN apk add --no-cache cmake readline-dev build-base tar git wget

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
RUN apk add --no-cache libreadline readline libgcc

COPY --from=luabuild /usr/local/bin/luajit* /usr/local/bin/
COPY --from=luabuild /usr/local/lib/lua /usr/local/lib/lua
COPY --from=luabuild /usr/local/share/lua /usr/local/share/lua
COPY --from=luabuild /usr/local/lib/luarocks /usr/local/lib/luarocks

WORKDIR /app

COPY apps/api/requirements.txt apps/api/requirements.txt
RUN pip install --no-cache-dir -r apps/api/requirements.txt

# Vendored PoB engine (git submodule) + our bridge script copied alongside
# HeadlessWrapper.lua, exactly where it expects to be run from (see
# .busted in the submodule: directory = "src").
COPY vendor/PathOfBuilding/src ./vendor/PathOfBuilding/src
COPY vendor/PathOfBuilding/runtime ./vendor/PathOfBuilding/runtime
COPY apps/api/lua/pob-bridge.lua ./vendor/PathOfBuilding/src/pob-bridge.lua

COPY apps/api/app ./apps/api/app
COPY scripts ./scripts

ENV PYTHONPATH=/app/apps/api
ENV LUA_EXECUTABLE=luajit
ENV POB_SRC_DIR=/app/vendor/PathOfBuilding/src
ENV PORT=8000
EXPOSE 8000

WORKDIR /app/apps/api
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port $PORT"]
