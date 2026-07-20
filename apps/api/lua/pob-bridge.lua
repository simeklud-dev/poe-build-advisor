--- Headless JSON bridge around Path of Building's calculation engine.
--
-- MUST run with the current working directory set to PathOfBuilding's
-- `src/` folder, and this file must be copied alongside `HeadlessWrapper.lua`
-- there (see Dockerfile) -- this mirrors exactly how PoB's own busted tests
-- run it (.busted: directory = "src", helper = "HeadlessWrapper.lua").
--
-- Protocol: one JSON command per line on stdin, one JSON response per line
-- on stdout, until stdin closes (EOF), e.g.:
--   -> {"cmd":"import_xml","args":{"xml":"<PathOfBuilding>...."}}
--   <- {"ok":true,"result":{"level":92,...}}
--
-- Never touches Deflate/Inflate: HeadlessWrapper.lua stubs them out (the
-- real (de)compression lives in a compiled runtime library that the headless
-- environment doesn't have -- see runtime-win32.zip / rundown.md). Callers
-- must send/receive raw XML, not base64+zlib PoB share codes; do that
-- encode/decode step on the Python side (app/pob/decode.py).

package.path = package.path .. ";../runtime/lua/?.lua;../runtime/lua/?/init.lua"

-- PoB's own startup/ConPrintf logging ("Loading main script...", tree
-- loading progress, etc.) goes through Lua's built-in print(), which writes
-- to stdout by default -- exactly the channel our line-delimited JSON
-- protocol uses. Redirect print() to stderr for the whole process lifetime
-- so nothing but our own JSON responses (written directly via
-- io.stdout:write in respond(), below) ever reaches stdout.
_G.print = function(...)
	local parts = {}
	for i = 1, select("#", ...) do
		parts[i] = tostring(select(i, ...))
	end
	io.stderr:write(table.concat(parts, "\t"), "\n")
end

dofile("HeadlessWrapper.lua")

local dkjson = require("dkjson")

-- Recursively converts a Lua value into something dkjson can encode safely:
-- keeps scalars, walks tables up to a depth limit, drops functions/userdata,
-- breaks reference cycles, and replaces NaN/Inf (JSON has no syntax for
-- them) with nil. We dump whole PoB output tables rather than hardcoding
-- specific stat names, so the bridge doesn't need updating when upstream
-- renames/adds fields across leagues (see AI_BUILD_ADVISOR_PLAN.md).
local function sanitize(value, depth, seen)
	depth = depth or 0
	if depth > 6 then
		return nil
	end
	local t = type(value)
	if t == "number" then
		if value ~= value or value == math.huge or value == -math.huge then
			return nil
		end
		return value
	elseif t == "string" or t == "boolean" then
		return value
	elseif t == "table" then
		seen = seen or {}
		if seen[value] then
			return nil
		end
		seen[value] = true
		local n = 0
		local isArray = true
		for k in pairs(value) do
			n = n + 1
			if type(k) ~= "number" then
				isArray = false
			end
		end
		if n == 0 then
			return {}
		end
		if isArray then
			local arr = {}
			for i = 1, n do
				arr[i] = sanitize(value[i], depth + 1, seen)
			end
			return arr
		end
		local out = {}
		for k, v in pairs(value) do
			if type(k) == "string" or type(k) == "number" then
				local sv = sanitize(v, depth + 1, seen)
				if sv ~= nil then
					out[tostring(k)] = sv
				end
			end
		end
		return out
	end
	return nil
end

local function respond(ok, payload)
	local msg
	if ok then
		msg = { ok = true, result = payload }
	else
		msg = { ok = false, error = tostring(payload) }
	end
	io.stdout:write(dkjson.encode(msg), "\n")
	io.stdout:flush()
end

-- Rebuilds both the fast sidebar output (MAIN) and the breakdown-enabled
-- output (CALCS) -- exactly what the GUI does on every change (Build.lua's
-- per-frame buildFlag handler: `wipeGlobalCache() ... self.calcsTab:BuildOutput()`).
-- wipeGlobalCache() matters: GlobalCache.cachedData caches per-active-skill
-- calc environments keyed by a UUID that doesn't change across a tree/item
-- edit, so without wiping it, a second recalc after e.g. deallocating a node
-- can silently keep serving stale values for anything the skill-level cache
-- touched (found by live-testing try_node_toggle: Life didn't revert on
-- deallocation until this was added). Called explicitly here (rather than
-- relying on PoB's internal dirty-flag/frame-driven refresh) so results are
-- deterministic for a script driving the app with no render loop.
local function refreshOutput()
	wipeGlobalCache()
	build.calcsTab:BuildOutput()
end

local handlers = {}

function handlers.ping()
	return "pong"
end

--- args: { xml = "<PathOfBuilding>...", name = "optional label" }
function handlers.import_xml(args)
	if not args or not args.xml or args.xml == "" then
		error("import_xml requires a non-empty 'xml' argument")
	end
	loadBuildFromXML(args.xml, args.name or "bridge-import")
	runCallback("OnFrame")
	-- Note: HeadlessWrapper.lua's own startup-error check (`mainObject.promptMsg`)
	-- isn't reachable here -- `mainObject` is a local upvalue inside that file's
	-- chunk, not a global -- so we check success at the one place we *can*
	-- observe it: whether the build actually produced calculated output below.
	refreshOutput()
	if not build or not build.calcsTab or not build.calcsTab.mainOutput then
		error("PoB failed to load the build (no calculated output after import)")
	end
	-- Best-effort metadata; wrapped so an internal field-name mismatch
	-- (possible across PoB versions) never fails the whole import -- the
	-- full numeric picture is available separately via get_summary.
	local metaOk, meta = pcall(function()
		return {
			className = build.spec and build.spec.curClassName,
			ascendClassName = build.spec and build.spec.curAscendClassName,
			level = build.characterLevel,
		}
	end)
	if metaOk then
		return sanitize(meta)
	end
	return {}
end

function handlers.get_summary()
	if not build or not build.calcsTab or not build.calcsTab.mainOutput then
		error("no build loaded -- call import_xml first")
	end
	return sanitize(build.calcsTab.mainOutput)
end

--- args: { stat = "CritChance" }
function handlers.get_breakdown(args)
	if not args or not args.stat then
		error("get_breakdown requires a 'stat' argument")
	end
	if not build or not build.calcsTab or not build.calcsTab.calcsEnv then
		error("no build loaded -- call import_xml first")
	end
	local breakdown = build.calcsTab.calcsEnv.player.breakdown
	if not breakdown then
		return nil
	end
	return sanitize(breakdown[args.stat])
end

function handlers.list_items()
	if not build then
		error("no build loaded -- call import_xml first")
	end
	local itemsTab = build.itemsTab
	local out = {}
	for slotName, slot in pairs(itemsTab.slots) do
		-- Skip tree jewel-socket slots (identified by slot.nodeId) -- those
		-- are addressed by node id via try_node_toggle/jewel handling later,
		-- not by slot name.
		if not slot.nodeId then
			local activeSet = itemsTab.activeItemSet[slotName]
			local selId = activeSet and activeSet.selItemId
			if selId and selId ~= 0 and itemsTab.items[selId] then
				out[slotName] = itemsTab.items[selId].raw
			end
		end
	end
	return sanitize(out)
end

--- Equips an item (given as raw in-game/PoB tooltip text) into a named slot,
--- persists the change and recalculates. Returns MAIN-mode output before and
--- after so the caller (Python/Claude) can compute a delta -- mirrors what
--- happens when you paste an item over an existing one in the GUI.
--- args: { slot = "Weapon 1", item_text = "Rarity: UNIQUE\n..." }
function handlers.try_item_change(args)
	if not build then
		error("no build loaded -- call import_xml first")
	end
	if not args or not args.slot or not args.item_text or args.item_text == "" then
		error("try_item_change requires 'slot' and non-empty 'item_text' arguments")
	end
	local itemsTab = build.itemsTab
	if not itemsTab.slots[args.slot] then
		error("unknown item slot: " .. tostring(args.slot) .. " (call list_items to see valid slot names)")
	end

	local before = sanitize(build.calcsTab.mainOutput)

	local newItem = new("Item", args.item_text)
	if not newItem.base then
		error("could not parse item_text -- not a recognised PoB/in-game item tooltip format")
	end
	newItem:NormaliseQuality()
	-- noAutoEquip=true: we equip explicitly into the requested slot below,
	-- rather than letting AddItem's normal "first empty matching slot" logic
	-- decide (which is what the GUI does for a brand new item, but here the
	-- caller told us exactly where it goes -- possibly replacing an item
	-- already there).
	itemsTab:AddItem(newItem, true)
	itemsTab.slots[args.slot]:SetSelItemId(newItem.id)
	itemsTab:PopulateSlots()
	refreshOutput()

	return {
		slot = args.slot,
		before = before,
		after = sanitize(build.calcsTab.mainOutput),
	}
end

--- Allocates the node if it isn't allocated, deallocates it (and anything
--- that depended on it) if it is -- same as clicking it on the tree.
--- args: { node_id = 12345 }
function handlers.try_node_toggle(args)
	if not build then
		error("no build loaded -- call import_xml first")
	end
	local nodeId = args and args.node_id
	if not nodeId then
		error("try_node_toggle requires a 'node_id' argument")
	end
	local node = build.spec.nodes[nodeId]
	if not node then
		error("unknown node id: " .. tostring(nodeId))
	end

	local before = sanitize(build.calcsTab.mainOutput)

	if node.alloc then
		build.spec:DeallocNode(node)
	else
		build.spec:AllocNode(node)
	end
	refreshOutput()

	return {
		nodeId = node.id,
		allocated = node.alloc and true or false,
		before = before,
		after = sanitize(build.calcsTab.mainOutput),
	}
end

function handlers.export_xml()
	if not build then
		error("no build loaded -- call import_xml first")
	end
	local xml = build:SaveDB("bridge-export")
	if not xml then
		error("PoB failed to serialise the current build")
	end
	return xml
end

-- Main loop.
while true do
	local line = io.read("*l")
	if not line then
		break
	end
	if line:match("%S") then
		local decodeOk, decoded = pcall(dkjson.decode, line)
		if not decodeOk or type(decoded) ~= "table" or not decoded.cmd then
			respond(false, "invalid request: expected a JSON object with a 'cmd' field")
		else
			local handler = handlers[decoded.cmd]
			if not handler then
				respond(false, "unknown command: " .. tostring(decoded.cmd))
			else
				local success, result = pcall(handler, decoded.args)
				respond(success, result)
			end
		end
	end
end
