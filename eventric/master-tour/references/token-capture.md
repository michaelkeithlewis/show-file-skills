# Getting the desktop token

There is no endpoint that issues a desktop token. You take it from the desktop app's own traffic.

1. Install mitmproxy: `brew install mitmproxy`.
2. Run the addon: `mitmdump -p 8888 -s scripts/mt_capture.py`.
3. Trust the mitmproxy CA: open `http://mitm.it` with the proxy on, install the certificate, and set it to Always Trust in Keychain Access.
4. Point the Mac at the proxy: System Settings, Network, your interface, Details, Proxies. Turn on HTTP and HTTPS proxy, `127.0.0.1` port `8888`.
5. Open Master Tour Desktop and click around until it syncs.
6. The addon writes `mt_desktop_env` (mode 600) with `MT_DESKTOP_TOKEN`, `MT_ACCOUNT_ID` and the current `MT_ORG_ID`. Run `source mt_desktop_env`.
7. Turn the system proxy off again.

Put the token in a password manager or keychain, not in a file in a repo. Do the capture again when calls start returning 401: the token changes each time you log out and back in to the app.

The same capture shows the full header set the app sends. If a new app version starts to get 401s with a fresh token, compare the captured User-Agent with `HEADERS` in `scripts/mt_desktop.py`.
