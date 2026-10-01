"""Measure: how much source did the paper's authors actually ship vs how much we wrote.

Compares the fork's mani_skill/ against the pristine PyPI wheel of mani_skill 3.0.0b14
(installed in _repro/venv), normalising line endings so CRLF/LF does not count as a change.
"""
import os
import re
import sys
from pathlib import Path

REPO = Path(r"E:\Users\bobxu\PycharmProjects\PCK-RL")
FORK = REPO / "mani_skill"
SP = REPO / "_repro" / "venv" / "Lib" / "site-packages" / "mani_skill"

SKIP = re.compile(r"__pycache__|\.pyc$")
TEXT_EXT = {".py", ".sh", ".md", ".txt", ".json", ".yaml", ".yml", ".cfg", ".toml", ".rst"}

# markers that identify the paper authors' own files
AUTHOR_MARK = re.compile(r"fhz|psl|PCL|pck[_-]?rl|tabletop_fhz|hammer|peg_only|two_hammer|kong\.|xiao\.", re.I)


def walk(root: Path) -> dict[str, Path]:
    out = {}
    if not root.is_dir():
        return out
    for p in root.rglob("*"):
        if p.is_file():
            rel = p.relative_to(root).as_posix()
            if SKIP.search(rel):
                continue
            out[rel] = p
    return out


def norm(p: Path) -> bytes:
    try:
        return p.read_bytes().replace(b"\r\n", b"\n")
    except OSError:
        return b""


def loc(p: Path) -> int:
    try:
        return p.read_text(encoding="utf-8", errors="replace").count("\n")
    except OSError:
        return 0


fork = walk(FORK)
sp = walk(SP)

added = sorted(set(fork) - set(sp))
missing = sorted(set(sp) - set(fork))
common = sorted(set(fork) & set(sp))
modified = [f for f in common if norm(fork[f]) != norm(sp[f])]

# author files among the fork: marker hit AND (added OR modified) -- i.e. the authors touched it
touched = set(added) | set(modified)
author_files = sorted(f for f in touched if AUTHOR_MARK.search(f))

lines = []
w = lines.append

w(f"fork mani_skill files : {len(fork)}")
w(f"upstream wheel files  : {len(sp)}")
w(f"  added by authors    : {len(added)}")
w(f"  modified by authors : {len(modified)}")
w(f"  deleted             : {len(missing)}")
w("")

w("=== A. author's OWN task/env files (marker hit) ===")
tot = 0
for f in author_files:
    n = loc(fork[f])
    tot += n
    w(f"  {n:6d}  {f}")
w(f"  ---- author task files total: {tot} lines in {len(author_files)} files")
w("")

w("=== B. the other 'added' files (likely upstream files the wheel simply omits) ===")
for f in added:
    if f not in author_files:
        w(f"  {loc(fork[f]):6d}  {f}")
w("")

w("=== C. modified upstream files, first 40 of " + str(len(modified)) + " ===")
for f in modified[:40]:
    w(f"  {loc(fork[f]):6d}  {f}")
w("")

# our own code
w("=== D. OUR code (_repro/**) ===")
our_total = 0
for p in sorted((REPO / "_repro").rglob("*")):
    if p.is_file() and p.suffix in TEXT_EXT and "venv" not in p.parts and "__pycache__" not in p.parts:
        n = loc(p)
        our_total += n
        w(f"  {n:6d}  {p.relative_to(REPO).as_posix()}")
w(f"  ---- our code total: {our_total} lines")
w("")

# author executable python only (exclude data assets)
w("=== E. author .py only (marker hit) ===")
py = [f for f in author_files if f.endswith(".py")]
w(f"  {len(py)} files, {sum(loc(fork[f]) for f in py)} lines")
for f in py:
    w(f"  {loc(fork[f]):6d}  {f}")

sys.stdout.write("\n".join(lines) + "\n")
