-- hs_runner.lua: run a Lua job inside Hammerspoon asynchronously and write the result to a file.
-- `hs -c` can hang forever on some return values, so jobs are queued on a timer and the
-- caller polls /tmp/hs_job_out.txt instead of waiting on the CLI.
function HS_RUN(path)
  os.remove("/tmp/hs_job_out.txt")
  hs.timer.doAfter(0.05, function()
    local t0 = hs.timer.secondsSinceEpoch()
    local ok, res = pcall(dofile, path)
    local f = io.open("/tmp/hs_job_out.txt", "w")
    f:write(string.format("ok=%s dt=%.2fs\n%s\n", tostring(ok), hs.timer.secondsSinceEpoch() - t0, tostring(res)))
    f:close()
  end)
  return "queued"
end
return "runner loaded"
