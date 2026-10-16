#!/usr/bin/env python3
"""Sends a review packet to other models through their command-line tools and collects their answers.

aldogor-second-opinion works in a run folder inside the session's scratchpad:

    <run>/packet/        what the reviewers see, and their working folder
        prompt.md        the instructions for this review or draft
        context.md       the reader, the purpose, the register, the user's rules that bear on the material
        files/           copies of the material, never the project's own files
    <run>/out/           this machine's side: Claude's own view, the answers, the logs, run.json

This script creates that layout (`new`), checks that each reviewer's tool is installed and signed in (`check`),
and runs the reviewers in parallel on a packet (`run`). Each reviewer is one entry of REVIEWERS (executable,
command line, how the message goes in and the answer comes out), so a tool that changes its flags costs one
entry.

`run` sends each reviewer the whole packet as one message on stdin: a short header, then prompt.md, context.md
and every text file under files/, each under its own heading. The reviewers need no file access: both tools
read a file by running a shell command, and both block shell commands when they run unattended (Codex's
read-only sandbox, Antigravity's headless permissions), so a reviewer told to read the packet answers that it
cannot. A file that is not UTF-8 text (Word, PowerPoint, PDF, images) is left out of the message and reported:
the skill puts a Markdown extract next to it.

  gpt     Codex CLI (OpenAI), signed in with the user's ChatGPT plan: `codex exec` in a read-only sandbox, run
          on the packet, the message on stdin and the final answer written to out/gpt.md.
  gemini  Antigravity CLI (Google), signed in with the user's Google account: `agy` in stream-json mode run
          inside the packet, the message as one JSON user event on stdin, the answer taken from the final
          `result` event into out/gemini.md. Antigravity may still write in its working folder without asking:
          the folder is a copy for that reason, and `run` hashes every packet file before and after and reports
          any change.

Usage:
  python second_opinion.py new SCRATCHPAD SLUG
  python second_opinion.py check [--reviewers gpt,gemini]
  python second_opinion.py run RUN [--reviewers gpt,gemini] [--model NAME=MODEL] [--effort NAME=LEVEL]
                               [--timeout SECONDS] [--dry-run]

`new` prints the run folder it created. `run` writes out/run.json (per reviewer: status, exit code, seconds,
answer file; the packet files left out of the message, and those that changed) and prints a summary; it exits 1 when no reviewer produced an
answer. `--model` and `--effort` override a reviewer's defaults and may be repeated. No key or password passes
through this script: each tool keeps its own sign-in. Python 3.10 or later, standard library only, on Windows,
macOS and Linux.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import datetime
import hashlib
import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import time
from typing import Callable

# The opening of the message every reviewer receives; prompt.md, context.md and the files follow it.
MESSAGE_HEADER = (
    "Everything you need is in this message: the instructions (prompt.md), then the context (context.md), then the "
    "material, one section per file under files/. Answer from this message alone: do not read files, run commands "
    "or browse. Give your whole answer as your reply, and do not create or edit any file."
)
DEFAULT_TIMEOUT = 1200  # seconds per reviewer; a long deck at high effort can take several minutes
STATUS_TIMEOUT = 60  # seconds for a sign-in check


@dataclasses.dataclass(frozen=True)
class Reviewer:
    """How to run one outside reviewer.

    build(exe, packet, answer, model, effort) returns the command line; `stdin_format` turns the message into
    what the tool reads on stdin; `parse_stdout`, when set, turns the tool's stdout into the answer (otherwise
    the tool writes the answer file itself). `status` is the command that exits 0 when
    the tool is installed and signed in, and `status_lists_models` says that its output lists the model names,
    so check can confirm the default model is among them; `install` is what the user runs to get there.
    `aliases` are other names the same tool may have on the PATH, tried in order when `executable` is not found.
    """

    name: str
    label: str
    executable: str
    build: Callable[[str, pathlib.Path, pathlib.Path, str | None, str | None], list[str]]
    stdin_format: Callable[[str], str]
    parse_stdout: Callable[[str], str] | None
    status: Callable[[str], list[str]]
    install: str
    model: str | None = None
    effort: str | None = None
    status_lists_models: bool = False
    aliases: tuple[str, ...] = ()


def find_executable(rev: Reviewer) -> str | None:
    """The full path of the reviewer's tool: its usual name first, then its aliases; None when none is on the PATH."""
    for name in (rev.executable, *rev.aliases):
        found = shutil.which(name)
        if found:
            return found
    return None


def codex_command(exe: str, packet: pathlib.Path, answer: pathlib.Path, model: str | None, effort: str | None) -> list[str]:
    """`codex exec` on the packet: read-only sandbox (Codex can change nothing), no git repository required (the
    scratchpad is not one), no session saved, the final message written to the answer file, and the message read
    from stdin (`-`)."""
    argv = [exe, "exec", "--sandbox", "read-only", "--skip-git-repo-check", "--ephemeral", "-C", str(packet), "-o", str(answer)]
    if model:
        argv += ["-m", model]
    if effort:
        argv += ["-c", f"model_reasoning_effort={effort}"]
    return argv + ["-"]


def agy_command(exe: str, packet: pathlib.Path, answer: pathlib.Path, model: str | None, effort: str | None) -> list[str]:
    """`agy` in stream-json mode, the only headless mode that reads the prompt from stdin, which has no length
    limit (`-p` puts it on the command line, and plain text on stdin is ignored). Stream-json input requires
    stream-json output and refuses `-p`. Antigravity takes its working folder from the current directory, which
    run_reviewer sets to the packet; the model slug comes from `agy models` (an unknown slug is an error, never a
    silent fallback)."""
    argv = [exe, "--input-format", "stream-json", "--output-format", "stream-json"]
    if model:
        argv += ["--model", model]
    if effort:
        argv += ["--effort", effort]
    return argv


def agy_stdin(message: str) -> str:
    """The message as the one JSON user event Antigravity's stream-json mode reads, on a single line."""
    return json.dumps({"event": "user", "message": {"content": message}}, ensure_ascii=False) + "\n"


def agy_answer(stdout: str) -> str:
    """The answer in Antigravity's stream-json output: the `response` of the final `result` event when its status
    is SUCCESS, otherwise an empty string (the log keeps the whole stream)."""
    for line in reversed(stdout.splitlines()):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("event") == "result":
            result = event.get("result") or {}
            return result.get("response", "") if result.get("status") == "SUCCESS" else ""
    return ""


REVIEWERS: dict[str, Reviewer] = {
    "gpt": Reviewer(
        name="gpt",
        label="GPT (Codex CLI)",
        executable="codex",
        build=codex_command,
        stdin_format=lambda message: message,
        parse_stdout=None,  # Codex writes the answer file itself (-o)
        status=lambda exe: [exe, "login", "status"],
        install="npm install -g @openai/codex, then `codex login` once in a terminal (ChatGPT account); with winget on Windows the command is codex-x86_64-pc-windows-msvc",
        model=None,  # Codex's own default, which follows OpenAI's current model
        effort="high",
        # winget installs Codex on Windows as a portable package. When it cannot create the `codex` link (its Links
        # folder needs symlink rights), it puts the package folder on the PATH instead, and the only command there
        # is the binary's own name, which carries the platform.
        aliases=("codex-x86_64-pc-windows-msvc", "codex-aarch64-pc-windows-msvc"),
    ),
    "gemini": Reviewer(
        name="gemini",
        label="Gemini (Antigravity CLI)",
        executable="agy",
        build=agy_command,
        stdin_format=agy_stdin,
        parse_stdout=agy_answer,
        status=lambda exe: [exe, "models"],
        install="the Antigravity CLI from https://antigravity.google/docs/getting-started, then `agy` once in a terminal to sign in (Google account)",
        # The strongest Gemini that the user's plan offers in the CLI; `check` lists the others, and
        # gemini-4-argon-high takes its place once it appears there. The slug carries the thinking level, so no
        # separate effort.
        model="gemini-3.8-flash-high",
        effort=None,
        status_lists_models=True,
    ),
}


# ---------------------------------------------------------------------------------------------------------------
# new


def new_run(scratchpad: pathlib.Path, slug: str, now: datetime.datetime | None = None) -> pathlib.Path:
    """Creates <scratchpad>/second-opinion/<timestamp>-<slug>/ with packet/files/ and out/, and returns it.

    The slug is reduced to lowercase letters, digits and hyphens, so the folder name is safe on every platform.
    """
    clean = re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-") or "review"
    stamp = (now or datetime.datetime.now()).strftime("%Y%m%d-%H%M%S")
    run = scratchpad / "second-opinion" / f"{stamp}-{clean}"
    (run / "packet" / "files").mkdir(parents=True)
    (run / "out").mkdir()
    return run


# ---------------------------------------------------------------------------------------------------------------
# processes


def run_process(argv: list[str], cwd: pathlib.Path | None, stdin_text: str, timeout: float) -> tuple[int | None, str, str, bool]:
    """Runs argv and returns (exit code, stdout, stderr, timed out).

    The process starts in a group of its own, so that a timeout stops the whole tree: the CLIs are Node programs
    launched through a wrapper (codex.cmd on Windows), and killing only the wrapper would leave the model call
    running and spending the user's quota. NO_COLOR keeps terminal colour codes out of the captured answer.
    """
    kwargs: dict = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    proc = subprocess.Popen(
        argv,
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "NO_COLOR": "1"},
        **kwargs,
    )
    try:
        out, err = proc.communicate(stdin_text, timeout=timeout)
        return proc.returncode, out, err, False
    except subprocess.TimeoutExpired:
        kill_tree(proc)
        out, err = proc.communicate()
        return None, out, err, True


def kill_tree(proc: subprocess.Popen) -> None:
    """Stops a process and everything it started: taskkill /T on Windows, the process group elsewhere."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


# ---------------------------------------------------------------------------------------------------------------
# check


def check(names: list[str], reviewers: dict[str, Reviewer] = REVIEWERS) -> list[dict]:
    """For each reviewer: whether its tool is on the PATH and its sign-in check exits 0.

    Status is "ready", "not installed" or "not signed in" (the tool's own message is kept in `detail`). For
    Antigravity the check also says whether the default model slug is among those `agy models` lists.
    """
    results = []
    for name in names:
        rev = reviewers[name]
        exe = find_executable(rev)
        if not exe:
            results.append({"reviewer": name, "status": "not installed", "detail": f"install: {rev.install}"})
            continue
        try:
            code, out, err, timed_out = run_process(rev.status(exe), None, "", STATUS_TIMEOUT)
        except OSError as e:
            results.append({"reviewer": name, "status": "not signed in", "detail": str(e)})
            continue
        text = (out + "\n" + err).strip()
        if code == 0 and not timed_out:
            detail = first_lines(text)
            if rev.status_lists_models:
                # `agy models` prints one model per line: the slug, a tab, the display name.
                slugs = [line.split("\t")[0].strip() for line in out.splitlines() if "\t" in line]
                detail = "models: " + ", ".join(slugs)
                if rev.model and rev.model not in slugs:
                    detail = f"default model {rev.model} not listed, pass --model {name}=<slug>; {detail}"
            results.append({"reviewer": name, "status": "ready", "detail": detail})
        else:
            results.append({"reviewer": name, "status": "not signed in", "detail": first_lines(text) or f"exit code {code}"})
    return results


def first_lines(text: str, n: int = 3) -> str:
    """The first n non-empty lines of a tool's output on one line, at most 300 characters, for the report."""
    return " | ".join([line.strip() for line in text.splitlines() if line.strip()][:n])[:300]


# ---------------------------------------------------------------------------------------------------------------
# run


def hash_tree(root: pathlib.Path) -> dict[str, str]:
    """sha256 of every file under root, by relative path with forward slashes."""
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


def tree_changes(before: dict[str, str], after: dict[str, str]) -> dict[str, list[str]]:
    """Files added, changed and removed between two hash_tree snapshots."""
    return {
        "added": sorted(set(after) - set(before)),
        "changed": sorted(k for k in set(before) & set(after) if before[k] != after[k]),
        "removed": sorted(set(before) - set(after)),
    }


def compose_message(packet: pathlib.Path) -> tuple[str, list[str]]:
    """The message every reviewer receives, and the packet files left out of it.

    MESSAGE_HEADER, then prompt.md, context.md (when present) and every file under files/ in path order, each
    under a heading with its path. A file that does not decode as UTF-8 is left out and listed, so the report can
    say what the reviewers did not see.
    """
    sections, skipped = [], []
    paths = [packet / "prompt.md", packet / "context.md", *sorted(p for p in (packet / "files").rglob("*") if p.is_file())]
    for path in paths:
        if not path.is_file():
            continue
        rel = path.relative_to(packet).as_posix()
        try:
            sections.append(f"===== {rel} =====\n{path.read_text(encoding='utf-8').strip()}\n")
        except UnicodeDecodeError:
            skipped.append(rel)
    return MESSAGE_HEADER + "\n\n" + "\n".join(sections), skipped


def run_reviewer(rev: Reviewer, run: pathlib.Path, message: str, model: str | None, effort: str | None, timeout: float) -> dict:
    """Runs one reviewer on run/packet with the message on stdin and returns its record for run.json.

    The answer lands in out/<name>.md and the log (command, exit code, stderr and stdout) in out/<name>.log.
    Status is "ok", "empty" (exit 0 but no answer), "failed", "timeout" or "not installed".
    """
    packet, out = run / "packet", run / "out"
    answer, log = out / f"{rev.name}.md", out / f"{rev.name}.log"
    record = {"reviewer": rev.name, "label": rev.label, "model": model, "effort": effort, "answer": None}
    exe = find_executable(rev)
    if not exe:
        return {**record, "status": "not installed", "detail": f"install: {rev.install}"}
    argv = rev.build(exe, packet, answer, model, effort)
    answer.unlink(missing_ok=True)  # an answer left by an earlier run in this folder must not pass for a new one
    start = time.monotonic()
    try:
        code, stdout, stderr, timed_out = run_process(argv, packet, rev.stdin_format(message), timeout)
    except OSError as e:
        return {**record, "status": "failed", "detail": str(e)}
    seconds = round(time.monotonic() - start, 1)
    if rev.parse_stdout and code == 0:
        text = rev.parse_stdout(stdout)
        if text.strip():
            answer.write_text(text, encoding="utf-8")
    log.write_text(
        f"command: {subprocess.list2cmdline(argv)}\nexit code: {code}\ntimed out: {timed_out}\nseconds: {seconds}\n\n"
        f"--- stderr ---\n{stderr}\n--- stdout ---\n{stdout}\n",
        encoding="utf-8",
    )
    has_answer = answer.is_file() and answer.read_text(encoding="utf-8", errors="replace").strip() != ""
    if timed_out:
        status = "timeout"
    elif code != 0:
        status = "failed"
    else:
        status = "ok" if has_answer else "empty"
    return {**record, "status": status, "exit_code": code, "seconds": seconds, "answer": answer.name if has_answer else None, "log": log.name}


def run_all(run: pathlib.Path, names: list[str], models: dict[str, str], efforts: dict[str, str], timeout: float, reviewers: dict[str, Reviewer] = REVIEWERS) -> dict:
    """Runs the named reviewers in parallel on run/packet and writes out/run.json.

    The message is composed once, so every reviewer receives the same one. The packet is hashed before and
    after: a reviewer that wrote into its working folder shows up under packet_changes, and the report to the
    user says so.
    """
    packet = run / "packet"
    if not (packet / "prompt.md").is_file():
        raise SystemExit(f"no packet/prompt.md in {run}: build the packet first")
    (run / "out").mkdir(exist_ok=True)
    message, skipped = compose_message(packet)
    before = hash_tree(packet)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(names) or 1) as pool:
        futures = [
            pool.submit(run_reviewer, reviewers[n], run, message, models.get(n, reviewers[n].model), efforts.get(n, reviewers[n].effort), timeout)
            for n in names
        ]
        results = [f.result() for f in futures]
    report = {"run": str(run), "reviewers": results, "not_sent": skipped, "packet_changes": tree_changes(before, hash_tree(packet))}
    (run / "out" / "run.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def dry_run(run: pathlib.Path, names: list[str], models: dict[str, str], efforts: dict[str, str], reviewers: dict[str, Reviewer] = REVIEWERS) -> list[str]:
    """The command lines run would execute, one per reviewer, the size of the message and the files it would
    leave out, with nothing run or written."""
    message, skipped = compose_message(run / "packet")
    lines = []
    for n in names:
        rev = reviewers[n]
        exe = find_executable(rev) or rev.executable
        argv = rev.build(exe, run / "packet", run / "out" / f"{n}.md", models.get(n, rev.model), efforts.get(n, rev.effort))
        lines.append(f"{n}: (in {run / 'packet'}) {subprocess.list2cmdline(argv)} < message of {len(message)} characters on stdin")
    if skipped:
        lines.append("not sent (not UTF-8 text): " + ", ".join(skipped))
    return lines


# ---------------------------------------------------------------------------------------------------------------
# command line


def pairs(values: list[str] | None, known: dict[str, Reviewer]) -> dict[str, str]:
    """NAME=VALUE options (--model, --effort) as a dict, rejecting reviewer names that do not exist."""
    result = {}
    for item in values or []:
        name, sep, value = item.partition("=")
        if not sep or name not in known:
            raise SystemExit(f"expected NAME=VALUE with NAME in {', '.join(known)}: {item}")
        result[name] = value
    return result


def names_arg(value: str, known: dict[str, Reviewer]) -> list[str]:
    names = [n.strip() for n in value.split(",") if n.strip()]
    unknown = [n for n in names if n not in known]
    if unknown or not names:
        raise SystemExit(f"reviewers must be among {', '.join(known)}: {value}")
    return names


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    p_new = sub.add_parser("new", help="create a run folder in the scratchpad")
    p_new.add_argument("scratchpad")
    p_new.add_argument("slug")
    p_check = sub.add_parser("check", help="check that the tools are installed and signed in")
    p_check.add_argument("--reviewers", default=",".join(REVIEWERS))
    p_run = sub.add_parser("run", help="run the reviewers on a packet")
    p_run.add_argument("run")
    p_run.add_argument("--reviewers", default=",".join(REVIEWERS))
    p_run.add_argument("--model", action="append", help="NAME=MODEL, e.g. gemini=gemini-3.1-pro-high")
    p_run.add_argument("--effort", action="append", help="NAME=LEVEL, e.g. gpt=xhigh")
    p_run.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    p_run.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    # A Windows console on cp1252 cannot print every character: replace what it lacks, never crash.
    sys.stdout.reconfigure(errors="replace")

    if args.command == "new":
        print(new_run(pathlib.Path(args.scratchpad), args.slug))
        return 0
    if args.command == "check":
        results = check(names_arg(args.reviewers, REVIEWERS))
        for r in results:
            print(f"{r['reviewer']}: {r['status']}" + (f" ({r['detail']})" if r["detail"] else ""))
        return 0 if all(r["status"] == "ready" for r in results) else 1
    run = pathlib.Path(args.run)
    names = names_arg(args.reviewers, REVIEWERS)
    models, efforts = pairs(args.model, REVIEWERS), pairs(args.effort, REVIEWERS)
    if args.dry_run:
        print("\n".join(dry_run(run, names, models, efforts)))
        return 0
    report = run_all(run, names, models, efforts, args.timeout)
    for r in report["reviewers"]:
        print(f"{r['reviewer']}: {r['status']}" + (f", {r['seconds']} s" if "seconds" in r else "") + (f", answer in out/{r['answer']}" if r["answer"] else "") + (f" ({r['detail']})" if "detail" in r else ""))
    if report["not_sent"]:
        print("not sent (not UTF-8 text): " + ", ".join(report["not_sent"]))
    changes = report["packet_changes"]
    if any(changes.values()):
        print("packet changed during the run: " + "; ".join(f"{k}: {', '.join(v)}" for k, v in changes.items() if v))
    return 0 if any(r["status"] == "ok" for r in report["reviewers"]) else 1


if __name__ == "__main__":
    sys.exit(main())
