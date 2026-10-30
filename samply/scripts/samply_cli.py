#!/usr/bin/env python3
"""samply_cli.py - list projects and folders, create folders, upload audio, add versions
and rename files on samply.app through its v0 REST API.

Credentials (first one found wins; the token is never printed):
  1. $SAMPLY_API_TOKEN
  2. the file named by $SAMPLY_TOKEN_FILE
  3. ~/.config/samply/token  (one line, chmod 600)

Subcommands:
  list-projects
  list-folders  --project NAME
  create-folder --project NAME --name NAME [--parent-id FOLDER_ID]
  upload        --project NAME [--folder NAME | --folder-id ID | --version-of STACK_ID] --file PATH [--name NAME]
  stack         --project NAME --stack-id ID          a stack's name and its versions
  rename        --project NAME --file-id ID --name NEW  rename a stack or a version, no re-upload
"""
import argparse
import mimetypes
import os
import sys

BASE = os.environ.get("SAMPLY_API_BASE", "https://samply.app/api/v0")

MIME = {
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".aiff": "audio/aiff",
    ".aif": "audio/aiff",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
}


def _requests():
    try:
        import requests
    except ImportError:
        sys.exit("samply_cli.py needs requests: pip install requests")
    return requests


def token() -> str:
    t = os.environ.get("SAMPLY_API_TOKEN", "").strip()
    if t:
        return t
    for path in (os.environ.get("SAMPLY_TOKEN_FILE"), os.path.expanduser("~/.config/samply/token")):
        if path and os.path.isfile(path):
            t = open(path).read().strip()
            if t:
                return t
    sys.exit("no Samply API token: set SAMPLY_API_TOKEN, or put the token in ~/.config/samply/token "
             "(or a file named by SAMPLY_TOKEN_FILE). See README.md.")


def headers() -> dict:
    return {"Authorization": f"Bearer {token()}"}


def die(msg: str) -> None:
    sys.exit(f"error: {msg}")


def get_json(resp):
    if not resp.ok:
        die(f"HTTP {resp.status_code} {resp.url}\n{resp.text[:500]}")
    return resp.json()


def api(method, path, **kw):
    return get_json(_requests().request(method, f"{BASE}{path}", headers=headers(), timeout=kw.pop("timeout", 60), **kw))


def projects() -> list:
    return api("GET", "/projects")


def resolve_project(name: str) -> dict:
    ps = projects()
    exact = [p for p in ps if p.get("name", "").lower() == name.lower()]
    subs = [p for p in ps if name.lower() in p.get("name", "").lower()]
    matches = exact or subs
    if not matches:
        die(f"no project matching {name!r}. Available: " + ", ".join(p.get("name", "?") for p in ps))
    if len(matches) > 1:
        die(f"{len(matches)} projects match {name!r}: " + ", ".join(m.get("name", "?") for m in matches) + ". Be more specific.")
    return matches[0]


def folders(project_id: str) -> list:
    return api("GET", f"/projects/{project_id}/folders")


def _walk(items):
    """Yield (folder, depth) recursively over folders and their children arrays."""
    def rec(nodes, depth):
        for n in nodes or []:
            yield n, depth
            kids = n.get("children")
            if isinstance(kids, list):
                yield from rec([k for k in kids if isinstance(k, dict) and "name" in k], depth + 1)
    yield from rec(items, 0)


def resolve_folder(project_id: str, name: str) -> dict:
    flat = [n for n, _ in _walk(folders(project_id))]
    exact = [f for f in flat if f.get("name", "").lower() == name.lower()]
    subs = [f for f in flat if name.lower() in f.get("name", "").lower()]
    matches = exact or subs
    if not matches:
        die(f"no folder matching {name!r} in project. Available: " + ", ".join(f.get("name", "?") for f in flat))
    if len(matches) > 1:
        die(f"{len(matches)} folders match {name!r}: " + ", ".join(m.get("name", "?") for m in matches)
            + ". Be more specific, or pass --folder-id.")
    return matches[0]


def cmd_list_projects(_):
    for p in projects():
        print(f"{p.get('id'):<28} {p.get('name')}")


def cmd_list_folders(a):
    p = resolve_project(a.project)
    print(f"# project: {p.get('name')} ({p.get('id')})")
    for f, depth in _walk(folders(p["id"])):
        kids = f.get("children")
        n = len([k for k in kids if isinstance(k, dict)]) if isinstance(kids, list) else 0
        print(f"{'  ' * depth}{f.get('id'):<28} {f.get('name')}" + (f"  [{n} children]" if n else ""))


def cmd_create_folder(a):
    p = resolve_project(a.project)
    body = {"name": a.name, **({"parentid": a.parent_id} if a.parent_id else {})}
    r = api("POST", f"/projects/{p['id']}/folders", json=body, timeout=30)
    print(f"created folder {a.name!r} -> {r.get('id')}")


def cmd_stack(a):
    p = resolve_project(a.project)
    st = api("GET", f"/projects/{p['id']}/files/{a.stack_id}")
    print(f"{st.get('object', '?')} {st.get('id')} {st.get('name')!r}")
    for c in st.get("children") or []:
        if isinstance(c, dict):
            print(f"  {c.get('id'):<28} {c.get('name')}")


def cmd_rename(a):
    p = resolve_project(a.project)
    api("POST", f"/projects/{p['id']}/files/{a.file_id}", json={"name": a.name}, timeout=30)
    print(f"renamed {a.file_id} -> {a.name!r}")


def cmd_upload(a):
    path = a.file
    if not os.path.isfile(path):
        die(f"file not found: {path}")
    if sum(bool(x) for x in (a.folder, a.folder_id, a.version_of)) > 1:
        die("pass only one of --folder, --folder-id, --version-of")
    name = a.name or os.path.basename(path)
    ext = os.path.splitext(path)[1].lower()
    mime = MIME.get(ext) or mimetypes.guess_type(path)[0] or "application/octet-stream"
    size = os.path.getsize(path)

    p = resolve_project(a.project)
    if a.version_of:
        parent, where = a.version_of, f"stack {a.version_of} (new version)"
    elif a.folder_id:
        parent, where = a.folder_id, f"folder {a.folder_id}"
    elif a.folder:
        f = resolve_folder(p["id"], a.folder)
        parent, where = f["id"], f.get("name")
    else:
        parent, where = None, "(root)"

    init = api("POST", f"/projects/{p['id']}/files",
               json={"name": name, "mimeType": mime, "size": size, **({"parentid": parent} if parent else {})})
    url = init.get("url")
    content_type = init.get("contentType", mime)
    meta = init.get("metadata", {}) or {}
    if not url:
        die(f"no signed url in response: {init}")

    put_headers = {
        "Content-Type": content_type,
        "x-goog-meta-destination": meta.get("destination", ""),
        "x-goog-meta-projectid": meta.get("projectid", p["id"]),
        "x-goog-meta-boxpath": meta.get("boxpath", ""),
    }
    with open(path, "rb") as fh:
        put = _requests().put(url, headers=put_headers, data=fh, timeout=3600)
    if not put.ok:
        die(f"upload PUT failed HTTP {put.status_code}\n{put.text[:500]}")

    print(f"uploaded {name!r} ({size} bytes, {mime}) -> {p.get('name')}/{where}")
    print(f"stackid={init.get('stackid')} boxid={init.get('boxid')}")
    print("check the web app: the track must show a duration, not a spinner")


def main():
    ap = argparse.ArgumentParser(description="Samply CLI", epilog=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list-projects").set_defaults(func=cmd_list_projects)

    lf = sub.add_parser("list-folders")
    lf.add_argument("--project", required=True)
    lf.set_defaults(func=cmd_list_folders)

    cf = sub.add_parser("create-folder")
    cf.add_argument("--project", required=True)
    cf.add_argument("--name", required=True)
    cf.add_argument("--parent-id", default=None, help="nest under this folder id")
    cf.set_defaults(func=cmd_create_folder)

    up = sub.add_parser("upload")
    up.add_argument("--project", required=True)
    up.add_argument("--folder", default=None, help="folder name; omit all three to upload to the project root")
    up.add_argument("--folder-id", default=None, help="exact folder id (use when folder names repeat)")
    up.add_argument("--version-of", default=None, metavar="STACK_ID",
                    help="add the file as the newest version of this stack (a new mix of the same song)")
    up.add_argument("--file", required=True)
    up.add_argument("--name", default=None, help="name on Samply (default: the file's basename)")
    up.set_defaults(func=cmd_upload)

    st = sub.add_parser("stack")
    st.add_argument("--project", required=True)
    st.add_argument("--stack-id", required=True)
    st.set_defaults(func=cmd_stack)

    rn = sub.add_parser("rename")
    rn.add_argument("--project", required=True)
    rn.add_argument("--file-id", required=True, help="a stack id or a version file id")
    rn.add_argument("--name", required=True)
    rn.set_defaults(func=cmd_rename)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
