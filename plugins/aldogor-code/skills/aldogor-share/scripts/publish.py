#!/usr/bin/env python3
"""Publishes the public version of a repository from its private one.

Two repositories, one direction: the private repository (conventionally `<name>-internal`) is where all the
work happens; the public repository only receives what the private one lists in `publish.txt`, one commit per
publication, and never its history. The public repository sits in a sibling clone that nobody works in, so the
private history can never be pushed to the public remote by mistake.

publish.txt, at the private repository's root, is an include-list: a file the list does not name stays private,
so a new file is never published by accident, and the list itself is never published. One entry per line, `#`
comments and blank lines ignored:
    target: ../<public clone>          the folder of the public repository's clone (required, once)
    check: <command>                   run at the private root before anything is built (repeatable)
    validate: <command>                run after the public tree is written, before the commit (repeatable)
                                       In both, {python} stands for the Python running this script and {target}
                                       for the clone's path, so the commands work on every platform.
    <path or glob>                     published at the same path; `dir/**` takes a whole folder, and `*` in a
                                       glob also matches across folders
    <source> -> <destination>          published under another path: a file to a file, or `dir/**` to a folder
                                       (`-> .` for the root)
Only committed content is published (HEAD); uncommitted changes are reported and left out. Python caches are
never published.

Some files never go public, whatever the list says: publish.txt, JOURNAL.md, CLAUDE.local.md, .env files
(.env.example and its kin excepted), .claude/settings.local.json, claude.ai chat exports, data/raw/, and the texts
of a literature folder (its bibliography.csv may go). A glob or folder rule holds them back and reports them.
Before anything is written, the publication stops on any of these findings:
  - a rule that names a never-public file explicitly;
  - a rule that matches no committed file (a rule left behind by a rename protects nothing);
  - two sources for one destination;
  - a line matching a known credential format (private keys, AWS, GitHub, Anthropic, OpenAI, Google, Slack and
    Stripe keys).
Files over 10 MB are reported. The public clone then becomes exactly the published tree: files the list no
longer names are removed from it. The push stays the user's step.

Usage:
  python publish.py [--repo DIR] [--check] [-m MESSAGE]

--repo defaults to the working directory (any folder inside the private repository). --check runs the checks
and lists what would be published, writing nothing. The default commit message is "Publish <short sha>: <the
last commit's subject>". Runs with Python 3.10 or later on Windows, macOS and Linux, with git on the PATH.
"""

import argparse
import fnmatch
import os
import pathlib
import re
import shutil
import subprocess
import sys

MANIFEST = "publish.txt"
BIG = 10 * 1024 * 1024
# Known credential formats; the same list as the user-level secrets hook (home/hooks/check_commit_secrets.py),
# which a test keeps in step.
SECRETS = [
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{50,}\b")),
    ("Anthropic key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("OpenAI key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{20,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("Stripe live key", re.compile(r"\b[rs]k_live_[0-9a-zA-Z]{20,}")),
]
ENV_FILE = re.compile(r"(^|/)\.env(\.[^/]+)?$")
ENV_ALLOWED = re.compile(r"\.env\.(example|sample|template|dist)$")
LITERATURE = re.compile(r"(^|/)literature/(?!bibliography\.csv$)[^/]+$")


class PublishError(Exception):
    """A reason not to publish; the message lists every finding."""


def git(repo: pathlib.Path, *args: str, text: bool = True) -> subprocess.CompletedProcess:
    res = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=text, **({"encoding": "utf-8", "errors": "replace"} if text else {}))
    if res.returncode != 0:
        raise PublishError(f"git {' '.join(args)} failed in {repo}: {res.stderr}")
    return res


def read_manifest(root: pathlib.Path) -> dict:
    """The manifest as {"target": str, "check": [...], "validate": [...], "rules": [(source, destination or None)]}."""
    path = root / MANIFEST
    if not path.is_file():
        raise PublishError(f"no {MANIFEST} at {root}: the include-list names what the public repository receives")
    out = {"target": None, "check": [], "validate": [], "rules": []}
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split(" #", 1)[0].strip() if not raw.lstrip().startswith("#") else ""
        if not line:
            continue
        key = re.match(r"^(target|check|validate):\s*(.+)$", line)
        if key:
            if key.group(1) == "target":
                out["target"] = key.group(2).strip()
            else:
                out[key.group(1)].append(key.group(2).strip())
            continue
        if "->" in line:
            src, dst = (s.strip() for s in line.split("->", 1))
            if any(c in src for c in "*?[") and not src.endswith("/**"):
                raise PublishError(f"{MANIFEST}:{n}: a renamed glob must be a whole folder (dir/** -> folder)")
            out["rules"].append((src, dst))
        else:
            out["rules"].append((line, None))
    if not out["target"]:
        raise PublishError(f"{MANIFEST} names no target (target: ../<public clone>)")
    return out


def never_public(path: str) -> str | None:
    """Why a path never goes public, or None."""
    name = path.rsplit("/", 1)[-1]
    if name in (MANIFEST, "JOURNAL.md", "CLAUDE.local.md"):
        return f"{name} never goes public"
    if ENV_FILE.search(path) and not ENV_ALLOWED.search(path):
        return ".env files never go public"
    if path.endswith(".claude/settings.local.json"):
        return "personal Claude settings never go public"
    if "archive/chat-export-claude-ai/" in path:
        return "claude.ai chat exports never go public"
    if re.search(r"(^|/)data/raw/", path):
        return "raw data never goes public"
    if LITERATURE.search(path):
        return "the texts of a literature folder never go public (bibliography.csv may)"
    return None


def plan(files: list[str], rules: list[tuple[str, str | None]]) -> tuple[dict[str, str], list[str]]:
    """({destination: source}, held back) for the committed files the rules select.

    A glob or a folder rule holds back the never-public files it matches and reports them; a rule that names a
    never-public file explicitly, a rule matching nothing and two sources for one destination stop the publication.
    """
    out: dict[str, str] = {}
    problems, held = [], []
    files = [f for f in files if "__pycache__" not in f.split("/")]
    for src, dst in rules:
        explicit = not any(c in src for c in "*?[")
        if dst is None:
            pairs = [(f, f) for f in files if f == src or fnmatch.fnmatchcase(f, src)]
        elif src.endswith("/**"):
            base = src[:-3]
            folder = "" if dst in (".", "./", "") else dst.rstrip("/") + "/"
            pairs = [(f, folder + f[len(base) + 1:]) for f in files if f.startswith(base + "/")]
        else:
            pairs = [(src, dst)] if src in files else []
        if not pairs:
            problems.append(f"rule matches no committed file: {src}" + (f" -> {dst}" if dst else ""))
        for s, d in pairs:
            why = never_public(s) or never_public(d)
            if why:
                if explicit:
                    problems.append(f"{s}: {why}")
                elif s not in held:
                    held.append(s)
                continue
            if d in out and out[d] != s:
                problems.append(f"two sources for {d}: {out[d]} and {s}")
            out[d] = s
    if problems:
        raise PublishError("\n".join(problems))
    return out, held


def scan(blobs: dict[str, bytes]) -> list[str]:
    """Credential findings in the files to publish, redacted."""
    found = []
    for path, data in sorted(blobs.items()):
        if b"\0" in data[:8000]:
            continue  # binary
        text = data.decode("utf-8", errors="replace")
        for name, pat in SECRETS:
            m = pat.search(text)
            if m:
                found.append(f"{name} in {path}: {m.group(0)[:6]}... (redacted)")
    return found


def run_commands(commands: list[str], cwd: pathlib.Path, label: str, target: pathlib.Path | None = None) -> None:
    """Run each command through the shell at cwd, with {python} (this interpreter) and {target} filled in; stop at a failure."""
    for cmd in commands:
        cmd = cmd.replace("{python}", f'"{sys.executable}"')
        cmd = cmd.replace("{target}", f'"{target.as_posix()}"') if target else cmd
        res = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        last = (res.stdout.strip().splitlines() or [""])[-1]
        print(f"{label}: {cmd} -> {'ok' if res.returncode == 0 else 'FAILED'} {last}")
        if res.returncode != 0:
            raise PublishError(f"{label} failed: {cmd}\n{res.stdout}{res.stderr}")


def write_tree(target: pathlib.Path, blobs: dict[str, bytes]) -> tuple[int, int]:
    """Make the clone's working tree exactly `blobs` (its .git untouched); return (written, removed)."""
    written = removed = 0
    for p in sorted(target.rglob("*"), reverse=True):
        rel = p.relative_to(target).as_posix()
        if rel == ".git" or rel.startswith(".git/"):
            continue
        if p.is_file() and rel not in blobs:
            p.unlink()
            removed += 1
        elif p.is_dir() and not any(p.iterdir()):
            p.rmdir()
    for rel, data in blobs.items():
        f = target / rel
        if f.is_file() and f.read_bytes() == data:
            continue
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
        written += 1
    return written, removed


def publish(repo: pathlib.Path, check_only: bool = False, message: str | None = None, log=print) -> tuple[str | None, pathlib.Path]:
    """Build, check and commit the public version; return (the new commit's summary or None, the public clone)."""
    root = pathlib.Path(git(repo, "rev-parse", "--show-toplevel").stdout.strip())
    manifest = read_manifest(root)
    target = (root / manifest["target"]).resolve()
    run_commands(manifest["check"], root, "check")

    files = [f for f in git(root, "ls-tree", "-r", "-z", "--name-only", "HEAD").stdout.split("\0") if f]
    selected, held = plan(files, manifest["rules"])
    if held:
        log("held back, never public: " + ", ".join(held))
    blobs = {d: git(root, "show", f"HEAD:{s}", text=False).stdout for d, s in selected.items()}
    findings = scan(blobs)
    if findings:
        raise PublishError("\n".join(findings))
    for d, data in sorted(blobs.items()):
        if len(data) > BIG:
            log(f"large file: {d} ({len(data) // (1024 * 1024)} MB)")
    dirty = [l[3:] for l in git(root, "status", "--porcelain").stdout.splitlines() if l.strip()]
    touched = [p for p in dirty if p in set(selected.values())]
    if touched:
        log("uncommitted changes left out: " + ", ".join(touched))
    log(f"{len(blobs)} files from {len(manifest['rules'])} rules, into {target}")
    if check_only:
        return None, target

    if not (target / ".git").exists():
        target.mkdir(parents=True, exist_ok=True)
        git(target, "init", "-q", "-b", "main")
        log(f"new public clone at {target}: add its remote before the first push")
    written, removed = write_tree(target, blobs)
    log(f"public tree: {written} files written, {removed} removed")
    run_commands(manifest["validate"], root, "validate", target)
    git(target, "add", "-A")
    if not git(target, "status", "--porcelain").stdout.strip():
        log("Nothing changed in the public repository.")
        return None, target
    head = git(root, "log", "-1", "--format=%h %s").stdout.strip().split(" ", 1)
    git(target, "commit", "-q", "-m", message or f"Publish {head[0]}: {head[1] if len(head) > 1 else ''}".strip())
    return git(target, "log", "--oneline", "-1").stdout.strip(), target


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", default=".", help="a folder inside the private repository (default: the working directory)")
    ap.add_argument("--check", action="store_true", help="run the checks and list what would be published; write nothing")
    ap.add_argument("-m", "--message", help="commit message in the public repository (default: Publish <sha>: <subject>)")
    args = ap.parse_args(argv)
    # A Windows console on cp1252 cannot print every character: replace what it lacks, never crash.
    sys.stdout.reconfigure(errors="replace")
    try:
        commit, target = publish(pathlib.Path(args.repo), args.check, args.message)
    except PublishError as e:
        print("Not published:\n" + str(e))
        return 1
    if commit:
        print(commit)
        print(f'Push when ready: git -C "{target}" push')
    return 0


if __name__ == "__main__":
    sys.exit(main())
