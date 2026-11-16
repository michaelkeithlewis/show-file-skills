"""mitmproxy addon that pulls the desktop token and account id out of Master Tour Desktop traffic.

  mitmdump -p 8888 -s mt_capture.py

Writes the newest values to $MT_CAPTURE_OUT (default ./mt_desktop_env) as shell exports.
"""
import json
import os

from mitmproxy import http

OUT = os.environ.get("MT_CAPTURE_OUT", "mt_desktop_env")
SEEN = {}


def request(flow: http.HTTPFlow):
    if "eventric.com" not in flow.request.pretty_host or "/desktop/" not in flow.request.path:
        return
    try:
        body = json.loads(flow.request.get_text() or "{}")
    except ValueError:
        return
    found = {k: body.get(k) for k in ("token", "accountId", "orgId") if body.get(k)}
    if not found or all(SEEN.get(k) == v for k, v in found.items()):
        return
    SEEN.update(found)
    lines = []
    if SEEN.get("token"):
        lines.append(f"export MT_DESKTOP_TOKEN='{SEEN['token']}'")
    if SEEN.get("accountId"):
        lines.append(f"export MT_ACCOUNT_ID='{SEEN['accountId']}'")
    if SEEN.get("orgId"):
        lines.append(f"export MT_ORG_ID='{SEEN['orgId']}'")
    with open(OUT, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(OUT, 0o600)
    print(f"[mt_capture] wrote {OUT}")
