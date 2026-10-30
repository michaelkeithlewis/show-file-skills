#!/usr/bin/env python3
"""Remove # comments from the repo's Python, keeping shebangs, coding lines and docstrings.

usage: strip-comments.py [--check] [--exclude DIR ...] [--notes]

Every removed comment is printed, so the fact it held can go in the model README.
A file is rewritten only if its AST is unchanged. --check lists files with comments and exits 1.
--notes writes references/script-notes.md under each skill folder from the removed comments.
"""
import ast, collections, io, os, subprocess, sys, tokenize


def scan(src):
    lines = src.split("\n")
    drop, cut, found = set(), {}, []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type != tokenize.COMMENT:
            continue
        row, col = tok.start
        if row <= 2 and (tok.string.startswith("#!") or "coding" in tok.string):
            continue
        found.append((row, tok.string))
        if lines[row - 1][:col].strip():
            cut[row] = col
        else:
            drop.add(row)
    out = []
    for n, line in enumerate(lines, 1):
        if n in drop:
            continue
        out.append(line[:cut[n]].rstrip() if n in cut else line)
    return "\n".join(out), found


def wanted(found):
    notes, last = [], -2
    for row, text in found:
        t = text.lstrip("#").strip()
        if not t or set(t) <= set("-=#* ") or t.startswith(("noqa", "type:", "pylint")):
            continue
        if row == last + 1 and notes:
            notes[-1] += " " + t
        else:
            notes.append(t)
        last = row
    return [n for n in notes if len(n) >= 30]


def skill_root(path):
    d = os.path.dirname(path)
    while d and not os.path.exists(os.path.join(d, "SKILL.md")):
        d = os.path.dirname(d)
    return d


def main():
    a = sys.argv[1:]
    check, notes = "--check" in a, "--notes" in a
    excl = [a[i + 1].rstrip("/") + "/" for i, x in enumerate(a) if x == "--exclude"]
    files = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "*.py"], capture_output=True, text=True).stdout.split()
    files = [f for f in files if not f.startswith(".github/") and not any(f.startswith(e) for e in excl)]
    dirty, by_skill = [], collections.defaultdict(list)
    for f in files:
        src = open(f, encoding="utf-8").read()
        new, found = scan(src)
        if not found:
            continue
        dirty.append(f)
        if check:
            continue
        if ast.dump(ast.parse(src)) != ast.dump(ast.parse(new)):
            sys.exit("AST changed, left alone: " + f)
        open(f, "w", encoding="utf-8").write(new)
        for _, text in found:
            print("%s: %s" % (f, text))
        kept = wanted(found)
        if kept:
            root = skill_root(f)
            by_skill[root].append((os.path.relpath(f, root), kept))
    if check:
        print("\n".join(dirty))
        sys.exit(1 if dirty else 0)
    if notes:
        for root, items in by_skill.items():
            os.makedirs(os.path.join(root, "references"), exist_ok=True)
            with open(os.path.join(root, "references", "script-notes.md"), "w", encoding="utf-8") as h:
                h.write("# Script notes\n\nFacts that used to sit in code comments, by script. The scripts in this repo carry no comments.\n")
                for f, kept in sorted(items):
                    h.write("\n## %s\n\n" % f)
                    h.writelines("- %s\n" % n for n in kept)


main()
