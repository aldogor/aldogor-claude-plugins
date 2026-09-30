#!/usr/bin/env python3
"""Checks one project repository against the conventions of the user's setup and reports what it breaks.

The conventions are those aldogor-project-setup writes and aldogor-handoff applies; they change over time, and
this script changes with them, in the same commit. It reads the repository and changes nothing:
  - CLAUDE.md exists and names the git practice on a "Git practice:" or "Pratica git:" line (research,
    development or shared);
  - git: commits ahead of or behind the upstream (after `git fetch` with --fetch), uncommitted changes,
    stashes, and local branches already merged into the main branch;
  - JOURNAL.md, when present, ends with one open list (`## Open` or `## Aperto`) rather than a list at the end
    of each entry (`### Open as of`, `### Aperto al`), and its latest entry, from 28 September 2026 on, closes
    with its Opened and closed line (`Opened: ...; closed: ...`, `Aperti: ...; chiusi: ...`);
  - no TODO.md and no CHANGELOG.md: the open list is the journal's, and git is the changelog;
  - `.env` is not tracked and is ignored;
  - the literature folder (literature/ or docs/literature/), when present, holds bibliography.json (a folder
    that keeps the older bibliography.csv is converted once), git tracks no other file of it, and the
    .gitignore keeps its PDFs and texts local;
  - the claude.ai chat exports: a project repository holds archive/chat-export-claude-ai/ only as an untracked
    working folder while its chats are distilled into the journal (aldogor-claude-setup keeps its own archive),
    and a public repository tracks JOURNAL.md or TODO.md only when they are written for the public;
  - publication: a public version is published from an include-list (publish.txt) into a sibling clone with
    aldogor-share's publish script, so an exclude-list (public_exclude.txt) or a remote named public in the
    working clone is the older model;
  - the repository's folder is never named `<name>-internal`: that suffix names only the private GitHub
    repository of a project with a public version, whose clone is the folder `<name>` and whose public
    clone is the sibling folder `<name>-public`;
  - every tracked top-level folder belongs to the standard layout (the research tree of aldogor-project-setup,
    plus the src/, tests/, public/, assets/, app/ and gradle/ that development stacks bring) or has its line
    in CLAUDE.md saying what it holds: a folder the project needs is described, drift is not;
  - every plugin that .claude/settings.json (or settings.local.json) enables is installed for this folder: the
    settings file enables plugins but installs nothing, and each machine records its installs per folder in
    ~/.claude/plugins/installed_plugins.json (skipped where that file does not exist).
Naming, stale content and the grouping of files are judgments, left to the tidy pass of aldogor-project-setup.

Usage:
  python check_project.py [PATH] [--fetch] [--no-github]

PATH defaults to the working directory (any folder inside the repository). --no-github skips the visibility
lookup through the gh CLI. Every finding is one line; the exit code is 0 whether or not there are findings.
Runs with Python 3.10 or later on Windows, macOS and Linux, with git on the PATH.
"""

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

SETUP_REPO = "aldogor-claude-setup"
ARCHIVE = "archive/chat-export-claude-ai"
PRACTICE = re.compile(r"(?:Git practice|Pratica git)\s*:\s*\**\s*(\w+)", re.I)
PRACTICE_NAMES = {"research": "research", "ricerca": "research", "development": "development", "sviluppo": "development", "shared": "shared", "condiviso": "shared", "condivisa": "shared"}
OLD_LIST = re.compile(r"^### (Open as of|Aperto al)\b", re.M)
NEW_LIST = re.compile(r"^## (Open|Aperto)\s*$", re.M)
ENTRY = re.compile(r"^## (\d{4}-\d{2}-\d{2})\b.*$", re.M)
CLOSING_LINE = re.compile(r"^\s*(?:-\s*)?(Opened|Closed|Aperti|Chiusi)\s*:", re.I | re.M)
# The date from which each journal entry closes with its Opened and closed line.
CLOSING_LINE_SINCE = "2026-09-28"
LITERATURE_DIRS = ("literature", "docs/literature")
# The top-level folders of the standard layout: the research tree of aldogor-project-setup and the folders that
# development stacks bring. Any other tracked top-level folder is described in the project's CLAUDE.md.
LAYOUT = {"docs", "literature", "archive", "data", "scripts", "outputs", "src", "tests", "public", "assets", "app", "gradle"}


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    """Run a command and capture its text output; a missing program counts as a failed run."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return subprocess.CompletedProcess(cmd, 127, "", "not found")


def git(repo: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return run(["git", "-C", str(repo), *args])


def plural(n: int, word: str) -> str:
    """"1 commit", "2 commits": the count with the word in the right number."""
    return f"{n} {word}{'' if n == 1 else ('es' if word.endswith('sh') else 's')}"


def github_visibility(repo: pathlib.Path) -> str:
    """public or private from GitHub, local-only without an origin, remote-unknown when gh gives no answer."""
    res = git(repo, "remote", "get-url", "origin")
    if res.returncode != 0 or not res.stdout.strip():
        return "local-only"
    # owner/name from https://github.com/owner/name(.git) or git@github.com:owner/name(.git)
    name = re.sub(r"^.*github\.com[:/]", "", re.sub(r"\.git$", "", res.stdout.strip()))
    if not shutil.which("gh"):
        return "remote-unknown"
    vis = run(["gh", "repo", "view", name, "--json", "visibility", "--jq", ".visibility"])
    return vis.stdout.strip().lower() if vis.returncode == 0 and vis.stdout.strip() else "remote-unknown"


def tracked(repo: pathlib.Path, *paths: str) -> list[str]:
    """The files git tracks under the given paths."""
    return [l for l in git(repo, "ls-files", *paths).stdout.splitlines() if l.strip()]


def ignored(repo: pathlib.Path, path: str) -> bool:
    """True when the repository's ignore rules cover the path, whether or not it exists."""
    return git(repo, "check-ignore", "-q", "--no-index", path).returncode == 0


def main_branch(repo: pathlib.Path) -> str:
    """The repository's main branch: the remote's HEAD when known, else main, else master, else the current branch."""
    head = git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if head.returncode == 0 and head.stdout.strip():
        return head.stdout.strip().split("/", 1)[1]
    for name in ("main", "master"):
        if git(repo, "rev-parse", "--verify", "-q", f"refs/heads/{name}").returncode == 0:
            return name
    return git(repo, "branch", "--show-current").stdout.strip()


def practice(repo: pathlib.Path) -> str:
    """The git practice named in CLAUDE.md, normalized to English, or "-" when none is named."""
    f = repo / "CLAUDE.md"
    m = PRACTICE.search(f.read_text(encoding="utf-8", errors="replace")) if f.is_file() else None
    return PRACTICE_NAMES.get(m.group(1).lower(), m.group(1).lower()) if m else "-"


def journal_form(text: str | None) -> str:
    """one list, N old lists, no open list, or - when the repository has no journal."""
    if text is None:
        return "-"
    old = len(OLD_LIST.findall(text))
    if old:
        return plural(old, "old list")
    return "one list" if NEW_LIST.search(text) else "no open list"


def latest_entry_without_closing_line(text: str) -> str | None:
    """The date of the journal's latest entry when it lacks its Opened and closed line, else None.

    Entries dated before CLOSING_LINE_SINCE predate the convention and are not reported."""
    entries = list(ENTRY.finditer(text))
    if not entries:
        return None
    last = entries[-1]
    end = NEW_LIST.search(text, last.end())
    body = text[last.end():end.start() if end else len(text)]
    date = last.group(1)
    return date if date >= CLOSING_LINE_SINCE and not CLOSING_LINE.search(body) else None


def literature_findings(repo: pathlib.Path) -> list[str]:
    """The literature folder against its convention: bibliography.json present, nothing else tracked, texts ignored.
    A folder that still keeps the older bibliography.csv is reported once, as a conversion to run."""
    out = []
    for rel in LITERATURE_DIRS:
        if not (repo / rel).is_dir():
            continue
        if (repo / rel / "bibliography.json").is_file():
            pass
        elif (repo / rel / "bibliography.csv").is_file():
            out.append(f"{rel}/ keeps the older bibliography.csv: turn it into bibliography.json with `literature.py convert` (aldogor-research)")
        else:
            out.append(f"{rel}/ has no bibliography.json: convert it with aldogor-research's literature script")
        others = [f for f in tracked(repo, rel) if f not in (f"{rel}/bibliography.json", f"{rel}/bibliography.csv")]
        if others:
            out.append(f"{plural(len(others), 'file')} of {rel}/ tracked by git besides bibliography.json: untrack them (git rm --cached)")
        if not ignored(repo, f"{rel}/any.pdf") or not ignored(repo, f"{rel}/any.md"):
            out.append(f"{rel}/ PDFs and texts not ignored: add `{rel}/*` and `!{rel}/bibliography.json` to .gitignore")
    return out


def publication_findings(repo: pathlib.Path) -> list[str]:
    """The public version against the publication model: an include-list (publish.txt) and a sibling clone."""
    out = []
    for rel in ("public_exclude.txt", "config/public_exclude.txt"):
        if (repo / rel).is_file():
            out.append(f"{rel} is an exclude-list: publish with an include-list (publish.txt) through aldogor-share's publish script")
    if "public" in git(repo, "remote").stdout.split():
        out.append("the public repository is a remote of this clone: publish into a sibling clone with aldogor-share's publish script")
    # -internal belongs to the GitHub repository's name only; the local folder carries the bare project name.
    if repo.name.endswith("-internal"):
        out.append(f"folder named {repo.name}: only the GitHub repository carries -internal, rename the folder to {repo.name.removesuffix('-internal')}")
    return out


def layout_findings(repo: pathlib.Path) -> list[str]:
    """Tracked top-level folders outside the standard layout that CLAUDE.md does not describe (named as `folder/`)."""
    claude_md = repo / "CLAUDE.md"
    text = claude_md.read_text(encoding="utf-8", errors="replace") if claude_md.is_file() else ""
    tops = sorted({p.split("/")[0] for p in tracked(repo) if "/" in p and not p.startswith(".")})
    extra = [t for t in tops if t not in LAYOUT and not re.search(rf"(?<![\w.-]){re.escape(t)}/", text)]
    return [f"top-level folder {t}/ is outside the standard layout and CLAUDE.md does not say what it holds" for t in extra]


def claude_dir() -> pathlib.Path:
    """The Claude Code folder: CLAUDE_CONFIG_DIR when set, otherwise ~/.claude."""
    return pathlib.Path(os.environ.get("CLAUDE_CONFIG_DIR") or pathlib.Path.home() / ".claude")


def plugin_findings(repo: pathlib.Path) -> list[str]:
    """Plugins the project's settings enable that have no install for this folder, and so do not load here.

    A user-scope install covers every folder; otherwise the registry needs a record of the settings file's scope
    (project for settings.json, local for settings.local.json) whose projectPath is this folder."""
    registry = claude_dir() / "plugins" / "installed_plugins.json"
    here = os.path.normcase(os.path.normpath(repo))
    out = []
    for rel, scope in ((".claude/settings.json", "project"), (".claude/settings.local.json", "local")):
        settings = repo / rel
        if not settings.is_file() or not registry.is_file():
            continue
        try:
            enabled = [k for k, v in (json.loads(settings.read_text(encoding="utf-8")).get("enabledPlugins") or {}).items() if v is True]
            records = json.loads(registry.read_text(encoding="utf-8")).get("plugins", {})
        except (json.JSONDecodeError, AttributeError):
            out.append(f"{rel} or the plugin registry is not valid JSON")
            continue
        for pid in enabled:
            if any(r.get("scope") == "user" or (r.get("scope") == scope and os.path.normcase(os.path.normpath(r.get("projectPath") or "")) == here) for r in records.get(pid, [])):
                continue
            out.append(f"{pid} is enabled in {rel} but not installed for this folder, so it does not load: claude plugin install {pid} --scope {scope}")
    return out


def check(repo: pathlib.Path, visibility: str | None = None, fetch: bool = False, mirror: bool = False) -> dict:
    """The project's state and the conventions it breaks, as a dict whose "findings" lists one line each.

    visibility: public, private, local-only or remote-unknown; None asks GitHub. mirror: a generated copy of
    another repository (the public plugins), checked for git state and .env only."""
    top = git(repo, "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        raise SystemExit(f"{repo} is not inside a git repository")
    repo = pathlib.Path(top.stdout.strip())
    if visibility is None:
        visibility = github_visibility(repo)
    if fetch and git(repo, "remote").stdout.strip():
        git(repo, "fetch", "-q", "--prune")

    branch = git(repo, "branch", "--show-current").stdout.strip() or "(detached)"
    counts = git(repo, "rev-list", "--left-right", "--count", "@{upstream}...HEAD")
    if counts.returncode == 0:
        behind, ahead = (int(x) for x in counts.stdout.split())
        remote = f"+{ahead} -{behind}"
    else:
        behind = ahead = 0
        remote = "no upstream"
    dirty = len([l for l in git(repo, "status", "--porcelain").stdout.splitlines() if l.strip()])
    stashes = len(git(repo, "stash", "list").stdout.splitlines())
    base = main_branch(repo)
    merged = [b.strip() for b in git(repo, "branch", "--merged", base, "--format=%(refname:short)").stdout.splitlines() if b.strip() and b.strip() not in (base, branch)]
    journal_path = repo / "JOURNAL.md"
    journal_text = journal_path.read_text(encoding="utf-8", errors="replace") if journal_path.is_file() else None
    named = "mirror" if mirror else practice(repo)
    journal = journal_form(journal_text)

    f = []
    if not mirror:
        if not (repo / "CLAUDE.md").is_file():
            f.append("no CLAUDE.md")
        elif named == "-":
            f.append("git practice not named in CLAUDE.md")
    if ahead:
        f.append(f"{plural(ahead, 'commit')} not pushed")
    if behind:
        f.append(f"{plural(behind, 'commit')} behind the remote")
    if dirty:
        f.append(f"{plural(dirty, 'uncommitted change')}")
    if stashes:
        f.append(plural(stashes, "stash"))
    if merged:
        f.append("merged branches not deleted: " + ", ".join(merged))
    if journal_text is not None:
        if "old list" in journal:
            f.append(f"journal: {journal} to convert into one open list at the end")
        elif journal == "no open list":
            f.append("journal without an open list at the end")
        missing = latest_entry_without_closing_line(journal_text)
        if missing:
            f.append(f"journal: the entry of {missing} has no Opened and closed line")
    for name in ("TODO.md", "CHANGELOG.md"):
        if (repo / name).is_file() and not mirror:
            f.append(f"{name} present: fold it into the journal's open list, or leave the changes to git")
    if tracked(repo, ".env"):
        f.append(".env tracked by git")
    elif not ignored(repo, ".env"):
        f.append(".env not ignored")
    if not mirror:
        f += literature_findings(repo)
        f += publication_findings(repo)
        f += layout_findings(repo)
        f += plugin_findings(repo)
    present = (repo / ARCHIVE).exists()
    archive_tracked = present and bool(tracked(repo, ARCHIVE))
    if visibility == "public" and tracked(repo, "JOURNAL.md", "TODO.md"):
        f.append("JOURNAL/TODO tracked in a public repo: confirm they are written for the public")
    if present and repo.name != SETUP_REPO:
        f.append("chat archive tracked: distil into the journal, keep knowledge documents in archive/, remove" if archive_tracked else "chat export working folder pending: distil into the journal, then delete")
    return {
        "repo": repo.name, "branch": branch, "practice": named, "remote": remote, "visibility": visibility,
        "journal": journal, "archive": ("tracked" if archive_tracked else "untracked") if present else "-",
        "findings": f,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("path", nargs="?", default=".", help="a folder inside the repository (default: the working directory)")
    ap.add_argument("--fetch", action="store_true", help="git fetch before comparing with the upstream")
    ap.add_argument("--no-github", action="store_true", help="skip the visibility lookup through gh")
    args = ap.parse_args(argv)
    # A Windows console on cp1252 cannot print every character: replace what it lacks, never crash.
    sys.stdout.reconfigure(errors="replace")
    row = check(pathlib.Path(args.path), visibility="remote-unknown" if args.no_github else None, fetch=args.fetch)
    print(f"{row['repo']}: branch {row['branch']}, practice {row['practice']}, remote {row['remote']}, journal {row['journal']}")
    for line in row["findings"]:
        print(f"- {line}")
    if not row["findings"]:
        print("- conventions: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
