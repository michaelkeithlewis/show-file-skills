"""Check, pack, unpack and re-pack .show containers. Python 3.9+, standard library only.

usage:
  show_tool.py check  <file.show>
  show_tool.py pack   <dir> <out.show>
  show_tool.py unpack <file.show> <dir>
  show_tool.py canon  <in.show> <out.show>

check    validates the container and the show module; prints "ok" and whether the
         file is already byte-canonical; on any problem prints one sentence and exits 1.
pack     builds a .show from a directory (passport.gfs plus one folder per module)
         in the deterministic profile. Refuses before writing anything.
unpack   writes every entry of a valid .show into an empty or new directory.
canon    re-packs a .show in the deterministic profile. Encrypted modules are copied
         byte for byte and are never decrypted.

Layout, rules and the deterministic profile: references/CONTAINER.md.
Schema of the show module: references/schema/show.schema.json.
"""
import hashlib
import io
import json
import os
import re
import sys
import zipfile

MIME = "application/vnd.gfs.show"
PASSPORT = "passport.gfs"
ACCESS = "META-INF/access.json"
INTEGRITY = "META-INF/integrity.json"
README = "README.txt"
MODULES = ("backline", "carnet", "changeover", "gainstage", "greenroom", "loadin", "settle", "show", "stageleft")
ALWAYS_ENCRYPTED = ("backline", "settle")
SHOW_PATH = "show/show.json"
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references", "schema", "show.schema.json")
EPOCH = (1980, 1, 1, 0, 0, 0)
NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$")
README_TEXT = "\n".join([
    "This is a .show file: a ZIP container for live-audio show data.",
    "",
    "  passport.gfs   show metadata, always readable",
    "  META-INF/      access and integrity records",
    "  show/          the show module (input list, patch, stage, outputs, processing intent)",
    "",
    "Other module folders may be present. Encrypted modules end in .enc and need a passphrase.",
    "Spec: show-file-skills, goforshow/show/references/CONTAINER.md",
    "",
])


class Refuse(Exception):
    pass


def refuse(message):
    raise Refuse(message)


def reject_constant(name):
    refuse("A JSON file contains the non-finite number " + name + ".")


def reject_duplicates(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            refuse("A JSON file repeats the key \"" + key + "\".")
        seen[key] = value
    return seen


def parse_json(raw, label):
    if raw.startswith(b"\xef\xbb\xbf"):
        refuse(label + " starts with a byte order mark.")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        refuse(label + " is not UTF-8.")
    try:
        return json.loads(text, object_pairs_hook=reject_duplicates, parse_constant=reject_constant)
    except Refuse:
        raise
    except ValueError:
        refuse(label + " is not valid JSON.")


def normalize(value):
    if isinstance(value, float) and value.is_integer() and abs(value) < 2 ** 53:
        return int(value)
    if isinstance(value, list):
        return [normalize(v) for v in value]
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items()}
    return value


def sort_list(owner, key, field):
    items = owner.get(key) if isinstance(owner, dict) else None
    if isinstance(items, list) and all(isinstance(i, dict) and isinstance(i.get(field), (int, str)) and not isinstance(i.get(field), bool) for i in items):
        if len({type(i[field]) for i in items}) <= 1:
            owner[key] = sorted(items, key=lambda i: i[field])


def order_show(show):
    if not isinstance(show, dict):
        return show
    for key, field in (("channels", "number"), ("patch", "channel"), ("outputs", "number"), ("processing", "channel")):
        sort_list(show, key, field)
    stage = show.get("stage")
    if isinstance(stage, dict):
        sort_list(stage, "elements", "id")
        for element in stage.get("elements", []) if isinstance(stage.get("elements"), list) else []:
            numbers = element.get("channels") if isinstance(element, dict) else None
            if isinstance(numbers, list) and all(isinstance(n, int) and not isinstance(n, bool) for n in numbers):
                element["channels"] = sorted(numbers)
    for proc in show.get("processing", []) if isinstance(show.get("processing"), list) else []:
        sort_list(proc, "sends", "output")
    return show


def dumps(value):
    text = json.dumps(normalize(value), sort_keys=True, indent=2, ensure_ascii=False, separators=(",", ": "))
    return (text + "\n").encode("utf-8")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def type_ok(value, name):
    if name == "string":
        return isinstance(value, str)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "array":
        return isinstance(value, list)
    if name == "object":
        return isinstance(value, dict)
    if name == "null":
        return value is None
    return False


def check_schema(value, schema, root, where):
    if "$ref" in schema:
        target = root
        for part in schema["$ref"].lstrip("#/").split("/"):
            target = target[part]
        check_schema(value, target, root, where)
        return
    if "const" in schema and value != schema["const"]:
        refuse("show/show.json " + where + " must be " + json.dumps(schema["const"]) + ".")
    if "enum" in schema and value not in schema["enum"]:
        refuse("show/show.json " + where + " must be one of " + ", ".join(json.dumps(v) for v in schema["enum"]) + ".")
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(type_ok(value, n) for n in names):
            refuse("show/show.json " + where + " must be of type " + " or ".join(names) + ".")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            refuse("show/show.json " + where + " is shorter than " + str(schema["minLength"]) + " characters.")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            refuse("show/show.json " + where + " is longer than " + str(schema["maxLength"]) + " characters.")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            refuse("show/show.json " + where + " does not match its required pattern.")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            refuse("show/show.json " + where + " is below " + str(schema["minimum"]) + ".")
        if "maximum" in schema and value > schema["maximum"]:
            refuse("show/show.json " + where + " is above " + str(schema["maximum"]) + ".")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            refuse("show/show.json " + where + " has fewer than " + str(schema["minItems"]) + " items.")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            refuse("show/show.json " + where + " has more than " + str(schema["maxItems"]) + " items.")
        if "items" in schema:
            for index, item in enumerate(value):
                check_schema(item, schema["items"], root, where + "/" + str(index))
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                refuse("show/show.json " + where + " is missing \"" + key + "\".")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    refuse("show/show.json " + where + " has the unknown key \"" + key + "\".")
        for key, sub in props.items():
            if key in value:
                check_schema(value[key], sub, root, where + "/" + key)


def load_schema():
    try:
        with open(SCHEMA_PATH, "rb") as handle:
            return json.loads(handle.read().decode("utf-8"))
    except (OSError, ValueError):
        refuse("The schema file references/schema/show.schema.json is missing or unreadable.")


def unique(values, what):
    if len(values) != len(set(values)):
        refuse("show/show.json repeats a " + what + ".")


def check_meaning(show):
    numbers = [c["number"] for c in show["channels"]]
    unique(numbers, "channel number")
    known = set(numbers)
    by_number = {c["number"]: c for c in show["channels"]}
    for channel in show["channels"]:
        link = channel.get("stereo_link")
        if link:
            other = by_number.get(link["partner"])
            if other is None:
                refuse("Channel " + str(channel["number"]) + " links to channel " + str(link["partner"]) + ", which does not exist.")
            back = other.get("stereo_link")
            if not back or back["partner"] != channel["number"] or back["side"] == link["side"]:
                refuse("Channel " + str(channel["number"]) + " and channel " + str(link["partner"]) + " do not link to each other on opposite sides.")
    patch = show.get("patch", [])
    unique([p["channel"] for p in patch], "patched channel")
    unique([(p["location"], p["socket"]) for p in patch], "patch socket")
    for entry in patch:
        if entry["channel"] not in known:
            refuse("The patch uses channel " + str(entry["channel"]) + ", which does not exist.")
    outputs = show.get("outputs", [])
    out_numbers = [o["number"] for o in outputs]
    unique(out_numbers, "output number")
    stage = show.get("stage")
    if stage:
        unique([e["id"] for e in stage["elements"]], "stage element id")
        for element in stage["elements"]:
            for number in element.get("channels", []):
                if number not in known:
                    refuse("Stage element \"" + element["id"] + "\" uses channel " + str(number) + ", which does not exist.")
    unique([p["channel"] for p in show.get("processing", [])], "processing channel")
    for proc in show.get("processing", []):
        if proc["channel"] not in known:
            refuse("Processing names channel " + str(proc["channel"]) + ", which does not exist.")
        for send in proc.get("sends", []):
            if outputs and send["output"] not in out_numbers:
                refuse("Channel " + str(proc["channel"]) + " sends to output " + str(send["output"]) + ", which does not exist.")


def split_entries(entries):
    modules = {}
    for path in entries:
        if "/" not in path or path.startswith("META-INF/"):
            continue
        app = path.split("/", 1)[0]
        modules.setdefault(app, []).append(path)
    return modules


def validate(entries):
    names = list(entries)
    if not names or names[0] != "mimetype":
        refuse("The first ZIP entry must be mimetype.")
    if entries["mimetype"] != MIME.encode("ascii"):
        refuse("The mimetype entry must read " + MIME + ".")
    for name in (PASSPORT, ACCESS, INTEGRITY):
        if name not in entries:
            refuse("The container has no " + name + ".")
    passport = parse_json(entries[PASSPORT], PASSPORT)
    if not isinstance(passport, dict) or passport.get("gfs_version") != 3 or passport.get("type") != "passport":
        refuse(PASSPORT + " must have gfs_version 3 and type passport.")
    event = passport.get("event")
    if not isinstance(event, dict) or not isinstance(event.get("name"), str) or not event["name"]:
        refuse(PASSPORT + " needs event.name.")
    summaries = passport.get("modules")
    if not isinstance(summaries, dict) or not summaries:
        refuse(PASSPORT + " needs at least one module summary.")
    for app in summaries:
        if app not in MODULES:
            refuse(PASSPORT + " names the unknown module \"" + app + "\".")
    access = parse_json(entries[ACCESS], ACCESS)
    integrity = parse_json(entries[INTEGRITY], INTEGRITY)
    if not isinstance(access, dict) or not isinstance(access.get("modules"), dict):
        refuse(ACCESS + " needs a modules object.")
    if not isinstance(integrity, dict) or not isinstance(integrity.get("files"), dict) or integrity.get("algorithm") != "SHA-256":
        refuse(INTEGRITY + " needs algorithm SHA-256 and a files object.")
    modules = split_entries(entries)
    covered = set(integrity["files"])
    expected = {p for p in entries if p not in ("mimetype", ACCESS, INTEGRITY, README)}
    if covered != expected:
        refuse(INTEGRITY + " must list exactly the passport and every module file.")
    for path, digest in integrity["files"].items():
        if sha256(entries[path]) != digest:
            refuse("The hash of " + path + " does not match " + INTEGRITY + ".")
    module_hashes = [integrity["files"][p] for p in sorted(integrity["files"]) if p != PASSPORT]
    if passport.get("integrity") != "sha256:" + sha256("".join(module_hashes).encode("ascii")):
        refuse("The passport integrity value does not match the module hashes.")
    for app, paths in modules.items():
        if app not in MODULES:
            refuse("The container holds the unknown module folder \"" + app + "\".")
        if len(paths) != 1:
            refuse("The module " + app + " must hold exactly one file.")
        encrypted = paths[0].endswith(".enc")
        info = access["modules"].get(app)
        if not isinstance(info, dict) or info.get("encrypted") != encrypted:
            refuse("The access record for " + app + " disagrees with its file name.")
        if encrypted and not info.get("salt"):
            refuse("The encrypted module " + app + " has no salt in " + ACCESS + ".")
        if app in ALWAYS_ENCRYPTED and not encrypted:
            refuse("The module " + app + " must be encrypted.")
        if app == "show" and encrypted:
            refuse("The show module must not be encrypted.")
        if not encrypted:
            parse_json(entries[paths[0]], paths[0])
    if "show" in modules:
        if modules["show"][0] != SHOW_PATH:
            refuse("The show module file must be named " + SHOW_PATH + ".")
        show = parse_json(entries[SHOW_PATH], SHOW_PATH)
        schema = load_schema()
        check_schema(show, schema, schema, "")
        check_meaning(show)
    return passport


def read_entries(path):
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError:
        refuse("The file " + path + " cannot be read.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        refuse("The file is not a ZIP archive.")
    entries = {}
    for info in archive.infolist():
        name = info.filename
        if info.is_dir() or not NAME_RE.match(name) or ".." in name.split("/"):
            refuse("The entry name \"" + name + "\" is not allowed.")
        if name in entries:
            refuse("The entry \"" + name + "\" appears twice.")
        if info.flag_bits & 1:
            refuse("The entry \"" + name + "\" uses ZIP encryption.")
        if info.file_size > 64 * 1024 * 1024:
            refuse("The entry \"" + name + "\" is larger than 64 MiB.")
        try:
            entries[name] = archive.read(info)
        except (zipfile.BadZipFile, NotImplementedError, RuntimeError):
            refuse("The entry \"" + name + "\" cannot be read.")
    return raw, entries


def write_zip(entries):
    order = ["mimetype"] + sorted(p for p in entries if p != "mimetype")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in order:
            info = zipfile.ZipInfo(name, EPOCH)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, entries[name])
    return buffer.getvalue()


def build(passport, modules, access_in):
    entries = {"mimetype": MIME.encode("ascii")}
    access = {"version": 1, "modules": {}}
    files = {}
    for app in sorted(modules):
        filename, raw, encrypted = modules[app]
        path = app + "/" + filename
        if encrypted:
            record = access_in.get(app)
            if not isinstance(record, dict) or not record.get("salt"):
                refuse("The encrypted module " + app + " has no salt record to carry over.")
            data = raw
            access["modules"][app] = dict(record, encrypted=True)
        else:
            parsed = parse_json(raw, path)
            data = dumps(order_show(parsed) if app == "show" else parsed)
            access["modules"][app] = {"encrypted": False}
        entries[path] = data
        files[path] = sha256(data)
    passport = dict(passport)
    passport["integrity"] = "sha256:" + sha256("".join(files[p] for p in sorted(files)).encode("ascii"))
    entries[PASSPORT] = dumps(passport)
    files[PASSPORT] = sha256(entries[PASSPORT])
    entries[ACCESS] = dumps(access)
    entries[INTEGRITY] = dumps({"algorithm": "SHA-256", "files": files, "version": 1})
    entries[README] = README_TEXT.encode("utf-8")
    validate(ordered(entries))
    return entries


def ordered(entries):
    names = ["mimetype"] + sorted(p for p in entries if p != "mimetype")
    return {name: entries[name] for name in names}


def modules_from_entries(entries):
    found = {}
    for app, paths in split_entries(entries).items():
        if len(paths) != 1:
            refuse("The module " + app + " must hold exactly one file.")
        path = paths[0]
        found[app] = (path.split("/", 1)[1], entries[path], path.endswith(".enc"))
    return found


def rebuild(entries):
    if PASSPORT not in entries or ACCESS not in entries:
        refuse("The container has no " + PASSPORT + " or " + ACCESS + ".")
    passport = parse_json(entries[PASSPORT], PASSPORT)
    access = parse_json(entries[ACCESS], ACCESS)
    if not isinstance(passport, dict) or not isinstance(access, dict) or not isinstance(access.get("modules"), dict):
        refuse("The passport or the access record is malformed.")
    return write_zip(build(passport, modules_from_entries(entries), access["modules"]))


def cmd_check(path):
    raw, entries = read_entries(path)
    validate(entries)
    again = rebuild(entries)
    print("ok")
    print("canonical: " + ("yes" if again == raw else "no"))


def cmd_unpack(path, target):
    _, entries = read_entries(path)
    validate(entries)
    if os.path.exists(target) and (not os.path.isdir(target) or os.listdir(target)):
        refuse("The target " + target + " must be a new or empty directory.")
    for name, data in entries.items():
        full = os.path.join(target, *name.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as handle:
            handle.write(data)


def cmd_canon(src, dst):
    _, entries = read_entries(src)
    validate(entries)
    data = rebuild(entries)
    with open(dst, "wb") as handle:
        handle.write(data)


def cmd_pack(source, dst):
    if not os.path.isdir(source):
        refuse("The source " + source + " is not a directory.")
    allowed = {"mimetype", PASSPORT, "META-INF", README} | set(MODULES)
    for item in os.listdir(source):
        if item not in allowed:
            refuse("The source holds the unexpected item \"" + item + "\".")
        if os.path.islink(os.path.join(source, item)):
            refuse("The source item \"" + item + "\" is a symbolic link.")
    passport_path = os.path.join(source, PASSPORT)
    if not os.path.isfile(passport_path):
        refuse("The source has no " + PASSPORT + ".")
    with open(passport_path, "rb") as handle:
        passport = parse_json(handle.read(), PASSPORT)
    if not isinstance(passport, dict):
        refuse(PASSPORT + " must be a JSON object.")
    access_in = {}
    access_path = os.path.join(source, "META-INF", "access.json")
    if os.path.isfile(access_path):
        with open(access_path, "rb") as handle:
            loaded = parse_json(handle.read(), ACCESS)
        if isinstance(loaded, dict) and isinstance(loaded.get("modules"), dict):
            access_in = loaded["modules"]
    modules = {}
    for app in MODULES:
        folder = os.path.join(source, app)
        if not os.path.isdir(folder):
            continue
        names = sorted(os.listdir(folder))
        member = os.path.join(folder, names[0]) if names else ""
        if len(names) != 1 or not os.path.isfile(member) or os.path.islink(member):
            refuse("The module folder " + app + " must hold exactly one regular file.")
        with open(member, "rb") as handle:
            modules[app] = (names[0], handle.read(), names[0].endswith(".enc"))
    if not modules:
        refuse("The source holds no module folder.")
    data = write_zip(build(passport, modules, access_in))
    with open(dst, "wb") as handle:
        handle.write(data)


def main(argv):
    arity = {"check": 1, "pack": 2, "unpack": 2, "canon": 2}
    if len(argv) < 2 or argv[1] not in arity or len(argv) != 2 + arity[argv[1]]:
        print("usage: show_tool.py check <file.show> | pack <dir> <out.show> | unpack <file.show> <dir> | canon <in.show> <out.show>")
        return 2
    handlers = {"check": cmd_check, "pack": cmd_pack, "unpack": cmd_unpack, "canon": cmd_canon}
    try:
        handlers[argv[1]](*argv[2:])
    except Refuse as exc:
        print("Refused: " + str(exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
