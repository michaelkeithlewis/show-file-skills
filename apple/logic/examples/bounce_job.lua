-- Example job: bounce bars 17-25 of the open Logic project. Run: scripts/hs_run.sh examples/bounce_job.lua 60
dofile("/tmp/logic_ax.lua")
if not L.app then return "Logic is not running" end
return L.bounce{name = "Chorus test", s = {17, 1}, e = {25, 1}, dry = true}
