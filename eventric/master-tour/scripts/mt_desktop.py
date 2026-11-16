#!/usr/bin/env python3
"""Master Tour Desktop API client.

Env: MT_DESKTOP_TOKEN, MT_ACCOUNT_ID, optional MT_ORG_ID.

  mt_desktop.py orgs
  mt_desktop.py retrieve --voType TourVO [--org ID] [--out rows.json]
  mt_desktop.py update   --voType DayVO --data '[{...}]' [--org ID]
  mt_desktop.py call     --endpoint updatedtables --body '{"lastSyncedData":{}}' [--org ID]
"""
import argparse
import json
import os
import sys

import requests

BASE = "https://my.eventric.com/portal/api/v1/desktop"
CLIENT_VERSION = "3.9.2"

HEADERS = {
    "user-agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) MasterTour/3.9.2 Chrome/132.0.6834.210 "
                   "Electron/34.5.8 Safari/537.36"),
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
    "sec-ch-ua": '"Not A(Brand";v="8", "Chromium";v="132"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-site": "cross-site",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "accept-language": "en-US",
    "priority": "u=1, i",
}


def die(msg):
    sys.exit(f"error: {msg}")


def env(name, required=True):
    v = os.environ.get(name, "").strip()
    if required and not v:
        die(f"set ${name}")
    return v


def base_body(org_id):
    b = {
        "accountId": env("MT_ACCOUNT_ID"),
        "token": env("MT_DESKTOP_TOKEN"),
        "clientVersion": CLIENT_VERSION,
        "tzOffset": 0,
    }
    if org_id:
        b["orgId"] = org_id
        b["selectedOrganizationId"] = org_id
    return b


def call(endpoint, overrides, org_id):
    body = base_body(org_id)
    body.update(overrides or {})
    resp = requests.post(f"{BASE}/{endpoint.lstrip('/')}", headers=HEADERS, json=body, timeout=120)
    if resp.status_code == 401:
        die("401 Bad credentials: the desktop token is stale, capture a fresh one")
    try:
        data = resp.json()
    except ValueError:
        die(f"HTTP {resp.status_code} non-JSON: {resp.text[:300]}")
    if resp.status_code >= 400:
        die(f"HTTP {resp.status_code}: {json.dumps(data)[:400]}")
    return data


def retrieve(vo_type, org_id):
    rows, last_pk, last_sync = [], "", ""
    while True:
        data = call("retrieve", {
            "voType": vo_type,
            "lastPrimaryKey": last_pk,
            "lastSyncTime": last_sync,
        }, org_id)
        rows.extend(data.get("data", []) or [])
        if data.get("isTableRetrieved", True):
            break
        last_pk = data.get("primaryKey", "")
        last_sync = data.get("newSyncTime", "")
        if not last_pk:
            break
    return rows


def update(vo_type, objects, org_id):
    return call("update", {"voType": vo_type, "data": objects}, org_id)


def dump(obj, out=None):
    text = json.dumps(obj, indent=2)
    if out:
        with open(out, "w") as f:
            f.write(text)
        print(f"wrote {out}")
    else:
        print(text)


def main():
    ap = argparse.ArgumentParser(description="Master Tour Desktop API client")
    ap.add_argument("--org", default=os.environ.get("MT_ORG_ID", ""), help="organization id")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("orgs")

    c = sub.add_parser("call")
    c.add_argument("--endpoint", required=True)
    c.add_argument("--body", default="{}")

    r = sub.add_parser("retrieve")
    r.add_argument("--voType", required=True)
    r.add_argument("--out")

    u = sub.add_parser("update")
    u.add_argument("--voType", required=True)
    u.add_argument("--data", required=True, help="JSON array; add isNew:true on each object to insert")

    a = ap.parse_args()
    if a.cmd == "orgs":
        for o in retrieve("Organization", None):
            print(o.get("id"), " ", o.get("name") or o.get("organizationName"))
    elif a.cmd == "call":
        dump(call(a.endpoint, json.loads(a.body), a.org or None))
    elif a.cmd == "retrieve":
        if not a.org:
            die("--org or $MT_ORG_ID is required")
        dump(retrieve(a.voType, a.org), a.out)
    elif a.cmd == "update":
        if not a.org:
            die("--org or $MT_ORG_ID is required")
        dump(update(a.voType, json.loads(a.data), a.org))


if __name__ == "__main__":
    main()
