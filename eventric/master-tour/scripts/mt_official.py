#!/usr/bin/env python3
"""Master Tour official REST API client (2-legged OAuth 1.0, HMAC-SHA1).

Env: MT_API_KEY, MT_API_SECRET.

  mt_official.py tours
  mt_official.py get tour/<tourId> numPastDays=0
  mt_official.py get day/<dayId>
  mt_official.py put day/<dayId> '{"generalNotes": "...", "syncId": 12}'
  mt_official.py post guestlist '{...}'
"""
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse

import requests

BASE = "https://my.eventric.com/portal/api/v5"


def creds():
    k, s = os.environ.get("MT_API_KEY", ""), os.environ.get("MT_API_SECRET", "")
    if not (k and s):
        sys.exit("error: set $MT_API_KEY and $MT_API_SECRET")
    return k, s


def enc(s):
    return urllib.parse.quote(str(s), safe="~")


def sign(method, url, params):
    key, secret = creds()
    oauth = {
        "oauth_consumer_key": key,
        "oauth_nonce": hashlib.sha1(str(time.time_ns()).encode()).hexdigest(),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_version": "1.0",
    }
    allp = {**params, **oauth}
    items = "&".join(f"{enc(k)}={enc(allp[k])}" for k in sorted(allp))
    base_str = "&".join([method.upper(), enc(url), enc(items)])
    digest = hmac.new(f"{enc(secret)}&".encode(), base_str.encode(), hashlib.sha1).digest()
    oauth["oauth_signature"] = base64.b64encode(digest).decode()
    return {**params, **oauth}


def call(method, path, params=None, body=None):
    params = dict(params or {})
    params["version"] = "7"
    url = f"{BASE}/{path.lstrip('/')}"
    signed = sign(method, url, params)
    return requests.request(method.upper(), url, params=signed, json=body, timeout=60)


def main():
    argv = sys.argv[1:] or ["tours"]
    if argv[0] == "tours":
        r = call("GET", "tours")
        data = r.json().get("data", {})
        tours = data.get("tours", data) if isinstance(data, dict) else data
        for t in tours:
            print(" | ".join(str(t.get(f) or "") for f in
                             ("organizationName", "artistName", "legName", "tourId")))
        return
    method, path = argv[0].upper(), argv[1]
    params, body = {}, None
    for extra in argv[2:]:
        if extra.startswith("{"):
            body = json.loads(extra)
        elif "=" in extra:
            k, v = extra.split("=", 1)
            params[k] = v
    r = call(method, path, params, body)
    print(r.status_code)
    try:
        print(json.dumps(r.json(), indent=2))
    except ValueError:
        print(r.text[:2000])


if __name__ == "__main__":
    main()
