-- logic_ax.lua: drive Logic Pro through the macOS Accessibility (AX) tree from Hammerspoon.
-- No screenshots, no mouse coordinates, no keystrokes: every action is an AX attribute or AXPress.
-- Load it in a job with dofile("/tmp/logic_ax.lua") (hs_run.sh copies it there).
--
--   L.dump(L.win("Tracks"), 6)         -- print the AX tree of a window
--   L.menu({"File", "Bounce", "Project or Section…"})
--   L.slots()                          -- {insert name = bypassed?} on the inspector channel strip
--   L.bounce{name="Chorus test", s={17,1}, e={25,1}, folder="Bounces", dry=false}
--     s/e = {bar, beat}. folder (optional) must match the save panel's "where" popup or it aborts.
--     dry=true sets the range, reads the settings and cancels.
L = {}
L.ax = require("hs.axuielement")
L.app = hs.application.get("com.apple.logic10")
L.root = L.ax.applicationElement(L.app); L.root:setTimeout(4)
function L.a(el, k) return el:attributeValue(k) end
function L.wins() return L.a(L.root, "AXWindows") or {} end
function L.win(sub) for _, w in ipairs(L.wins()) do if tostring(L.a(w, "AXTitle")):find(sub, 1, true) then return w end end end
function L.desc(el)
  local p, s = L.a(el, "AXPosition") or {}, L.a(el, "AXSize") or {}
  local v = L.a(el, "AXValue"); if type(v) == "table" or type(v) == "userdata" then v = "<" .. type(v) .. ">" end
  return string.format("%s t=%s v=%s d=%s help=%s en=%s @%d,%d %dx%d", tostring(L.a(el, "AXRole")):gsub("^AX", ""), tostring(L.a(el, "AXTitle")), tostring(v), tostring(L.a(el, "AXDescription")), tostring(L.a(el, "AXHelp")):sub(1, 60), tostring(L.a(el, "AXEnabled")), math.floor(p.x or -1), math.floor(p.y or -1), math.floor(s.w or -1), math.floor(s.h or -1))
end
function L.walk(el, fn, d, maxd)
  d = d or 0; if d > (maxd or 12) then return end
  if fn(el, d) == false then return false end
  for _, c in ipairs(L.a(el, "AXChildren") or {}) do if L.walk(c, fn, d + 1, maxd) == false then return false end end
end
function L.find(el, pred, maxd) local hit; L.walk(el, function(x) if pred(x) then hit = x; return false end end, 0, maxd); return hit end
function L.findAll(el, pred, maxd) local t = {}; L.walk(el, function(x) if pred(x) then t[#t + 1] = x end end, 0, maxd); return t end
function L.dump(el, maxd, maxn) local o, n = {}, 0; L.walk(el, function(x, d) n = n + 1; if n > (maxn or 300) then return false end; o[#o + 1] = string.rep("  ", d) .. L.desc(x) end, 0, maxd); return table.concat(o, "\n") end
function L.is(role, key, val) return function(x) return L.a(x, "AXRole") == role and (key == nil or L.a(x, key) == val) end end
function L.menu(path)
  -- press a menu item by path via AX (no keystrokes)
  local cur = L.a(L.root, "AXMenuBar")
  for i, name in ipairs(path) do
    local nxt
    for _, c in ipairs(L.a(cur, "AXChildren") or {}) do
      if L.a(c, "AXRole") == "AXMenu" then for _, c2 in ipairs(L.a(c, "AXChildren") or {}) do if L.a(c2, "AXTitle") == name then nxt = c2 end end
      elseif L.a(c, "AXTitle") == name then nxt = c end
      if nxt then break end
    end
    if not nxt then return nil, "menu item not found: " .. name end
    cur = nxt
  end
  if L.a(cur, "AXEnabled") == false then return nil, "disabled: " .. table.concat(path, " > ") end
  cur:performAction("AXPress"); return true end

-- insert-slot bypass states on the inspector channel strip: returns {name=bool}
function L.slots()
  local t = {}
  L.walk(L.win("Tracks"), function(x)
    if L.a(x, "AXRole") == "AXGroup" and L.a(x, "AXHelp") == nil then
      local kids = L.a(x, "AXChildren") or {}
      if #kids == 3 and L.a(kids[1], "AXDescription") == "bypass" and L.a(kids[2], "AXDescription") == "open" then
        local nm = tostring(L.a(x, "AXDescription")):gsub("%s+$", "")
        if t[nm] == nil then t[nm] = L.a(kids[1], "AXValue") end
      end
    end
  end, 0, 8)
  return t
end
function L.slotstr() local s = {}; for k, v in pairs(L.slots()) do s[#s+1] = k .. "=" .. (v == true and "BYPASSED" or "on") end; table.sort(s); return table.concat(s, ", ") end

-- Bounce dialog position: value = ticks * 2^32, bar 1 = 38400 ticks, 3840 ticks/bar (4/4, 960 ppq)
function L.pos(bar, beat) return ((bar - 1 + 10) * 3840 + ((beat or 1) - 1) * 960) * 4294967296 end
function L.waitwin(sub, pred, secs)
  for _ = 1, (secs or 8) * 5 do local w = L.win(sub); if w and (not pred or pred(w)) then return w end; hs.timer.usleep(200000) end
end
-- Bounce dialog position fields: AXIncrement/AXDecrement = 10 units, setting AXValue = 1 unit toward the value.
-- seg 1 = bars (3840 ticks), seg 2 = beats (960 ticks)
function L.posgroups(w) return L.findAll(w, function(x) return L.a(x, "AXRole") == "AXGroup" and type(L.a(x, "AXValue")) == "string" and L.a(x, "AXValue"):find("\t") end) end
function L.postext(g) return (L.a(g, "AXValue"):gsub("^%s+", ""):gsub("\t", " ")) end
function L.setpos2(w, idx, bar, beat)
  local target = math.tointeger(L.pos(bar, beat) // 4294967296)
  local function cur() return math.tointeger(math.floor(L.a(L.a(L.posgroups(w)[idx], "AXChildren")[1], "AXValue") / 4294967296 + 0.5)) end
  local guard = 0
  for segi, unit in ipairs({3840, 960}) do
    while true do
      guard = guard + 1; if guard > 400 then return nil, "guard tripped at " .. cur() end
      local d = target - cur()
      local steps = (d >= 0) and (d // unit) or -((-d) // unit)
      if steps == 0 then break end
      local seg = L.a(L.posgroups(w)[idx], "AXChildren")[segi]
      local before = cur()
      if math.abs(steps) >= 10 then seg:performAction(steps > 0 and "AXIncrement" or "AXDecrement")
      else seg:setAttributeValue("AXValue", (before + (steps > 0 and unit or -unit)) * 4294967296) end
      hs.timer.usleep(60000)
      if cur() == before then hs.timer.usleep(250000); if cur() == before then return nil, "stuck at " .. before .. " wanting " .. target end end
    end
  end
  return L.postext(L.posgroups(w)[idx])
end
function L.bounce(o)
  local log = {}
  local isSave = function(w) return L.a(w, "AXIdentifier") == "save-panel" end
  local w = L.win("Bounce")
  if w and isSave(w) then return "ABORT: a save panel is already open" end
  if not w then
    L.app:activate(); hs.timer.usleep(300000)
    L.menu({"File", "Bounce", "Project or Section…"})
    w = L.waitwin("Bounce", function(x) return not isSave(x) end, 8)
  end
  if not w then return "ABORT: bounce dialog did not open" end
  local want = function(be) return string.format("%d %d 1 1", be[1], be[2] or 1) end
  local function cancel(msg) L.find(w, L.is("AXButton", "AXTitle", "Cancel")):performAction("AXPress"); return "ABORT: " .. msg .. "; " .. table.concat(log, "; ") end
  -- order: if the new range sits earlier, move Start first; otherwise End first (keeps start < end throughout)
  local curStart = L.a(L.a(L.posgroups(w)[1], "AXChildren")[1], "AXValue")
  local order = (L.pos(o.s[1], o.s[2]) <= curStart) and {1, 2} or {2, 1}
  for _, idx in ipairs(order) do
    local be = (idx == 1) and o.s or o.e
    local got, err = L.setpos2(w, idx, be[1], be[2] or 1)
    if not got then return cancel("setpos " .. idx .. ": " .. tostring(err)) end
  end
  local gs, ge = L.postext(L.posgroups(w)[1]), L.postext(L.posgroups(w)[2])
  log[#log+1] = "range " .. gs .. " -> " .. ge
  if gs ~= want(o.s) or ge ~= want(o.e) then return cancel("range mismatch") end
  local pops = {}
  for _, p in ipairs(L.findAll(w, L.is("AXPopUpButton"))) do pops[#pops+1] = tostring(L.a(p, "AXValue")) end
  log[#log+1] = "settings " .. table.concat(pops, ",")
  local info = L.find(w, function(x) return L.a(x, "AXRole") == "AXStaticText" and tostring(L.a(x, "AXValue")):find("Requires", 1, true) end)
  log[#log+1] = tostring(info and L.a(info, "AXValue"))
  if o.dry then return cancel("dry run") end
  L.find(w, L.is("AXButton", "AXTitle", "OK")):performAction("AXPress")
  local sp = L.waitwin("Bounce", isSave, 8)
  if not sp then return "ABORT: save panel did not open; " .. table.concat(log, "; ") end
  local id = function(v) return function(x) return L.a(x, "AXIdentifier") == v end end
  local name, where = L.find(sp, id("saveAsNameTextField")), L.find(sp, id("where popup"))
  name:setAttributeValue("AXValue", o.name); hs.timer.usleep(300000)
  if L.a(name, "AXValue") ~= o.name or (o.folder and L.a(where, "AXValue") ~= o.folder) then
    L.find(sp, id("CancelButton")):performAction("AXPress")
    return "ABORT: name=" .. tostring(L.a(name, "AXValue")) .. " where=" .. tostring(L.a(where, "AXValue"))
  end
  log[#log+1] = "inserts " .. L.slotstr()
  L.find(sp, id("OKButton")):performAction("AXPress")
  log[#log+1] = "bouncing " .. o.name .. " to " .. tostring(L.a(where, "AXValue"))
  return table.concat(log, "\n")
end
return L
