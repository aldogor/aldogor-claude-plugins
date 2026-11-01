#!/usr/bin/env python3
"""aldogor-pseudonymize: mask the names and identifiers in a project's documents before Claude reads them.

Commands:
  setup     create the private environment and download the model, once per machine
  check     report the environment, the model and the guard state of a project
  init      prepare a project: folders, lists, .gitignore lines, the deny rule, the working rules
  mask      originals in pseudonymize-private/originals/ -> masked copies in masked/, table updated
            (--fresh: a new table, the earlier one and its copies kept in the private folder)
  review    write the review page, pseudonymize-private/review.html, for the user to open
  restore   a file with placeholders -> real values, in pseudonymize-private/restored/
  status    what the project holds: masked files, table counts

Claude reads what this script prints, so nothing it prints contains an original value or the name of an
original file: documents are named by their masked names, values by their counts.

The private environment (Python packages and the model) lives in the plugin's data folder,
${CLAUDE_PLUGIN_DATA} in the skill, ~/.claude/plugins/data/aldogor-code-aldogor-claude-plugins/ by
default; --data points elsewhere. Commands that need the model or the Word, PDF and Excel readers run
themselves again inside that environment. The rest of the script is standard library, Python 3.10+.

Usage: python pseudonymize.py [--data DIR] [--project DIR] <command> [options]
(python3 on macOS and Linux)
"""

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import pz_engine as eng  # noqa: E402

LISTS = SCRIPTS / "data"
PRIVATE, MASKED, CFG = "pseudonymize-private", "masked", ".pseudonymize"
DENY_RULE = f"Read({PRIVATE}/**)"
PLUGIN_DATA_ID = "aldogor-code-aldogor-claude-plugins"
# The environment, pinned to the versions the plugin is evaluated with. torch comes from PyTorch's CPU
# index on Linux, where the default wheel carries CUDA; on Windows and macOS the default wheel is CPU.
TORCH = "torch==2.14.1"
PINS = ["transformers==5.20.2", "tokenizers==0.23.3", "huggingface_hub==2.2.0", "safetensors==0.8.0",
        "python-docx==1.2.0", "pypdf==6.21.2", "openpyxl==3.1.5"]
# Only these model files are fetched: weights in safetensors and the JSON configuration, never a pickle.
MODEL_PATTERNS = ["*.json", "*.safetensors"]
MODEL_FILES = ["config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json"]
VENV_COMMANDS = {"mask", "restore"}
# Masked values per document that the review page offers for the precision count of the gate.
SAMPLE = 30


# --------------------------------------------------------------------------- #
# Paths and the private environment
# --------------------------------------------------------------------------- #
def default_data_dir() -> Path:
    env = os.environ.get("CLAUDE_PLUGIN_DATA")
    return Path(env) if env else Path.home() / ".claude" / "plugins" / "data" / PLUGIN_DATA_ID


def venv_python(data: Path) -> Path:
    return data / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def model_dir(data: Path) -> Path:
    return data / "models" / f"rizzo-pii-0.3B-{eng.MODEL_REVISION[:12]}"


def in_venv(data: Path) -> bool:
    try:
        return Path(sys.prefix).resolve() == (data / "venv").resolve()
    except OSError:
        return False


def rerun_in_venv(data: Path) -> int:
    """Run this same command again inside the private environment."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
               TOKENIZERS_PARALLELISM="false", TRANSFORMERS_VERBOSITY="error")
    return subprocess.run([str(venv_python(data)), str(Path(__file__).resolve()), *sys.argv[1:]], env=env).returncode


def claude_settings() -> Path:
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(env) if env else Path.home() / ".claude") / "settings.json"


def file_mentions_off(settings: Path) -> bool:
    """True when the settings turn @-mention expansion off (Claude Code 2.1.299 and later), so that a mentioned
    file reaches Claude as a path it decides whether to read, not as attached content. Claude Code honours the
    variable only in the user's settings or the shell, never in a project's settings."""
    try:
        env = json.loads(settings.read_text(encoding="utf-8")).get("env", {})
    except (OSError, ValueError):
        env = {}
    return str(env.get("CLAUDE_CODE_DISABLE_FILE_MENTIONS", os.environ.get("CLAUDE_CODE_DISABLE_FILE_MENTIONS", ""))) == "1"


def has_deny_rule(settings: Path) -> bool:
    try:
        return DENY_RULE in json.loads(settings.read_text(encoding="utf-8")).get("permissions", {}).get("deny", [])
    except (OSError, ValueError):
        return False


def add_deny_rule(settings: Path) -> bool:
    """Add the deny rule to a settings file, keeping everything else; True when the file changed."""
    data = json.loads(settings.read_text(encoding="utf-8")) if settings.exists() else {}
    deny = data.setdefault("permissions", {}).setdefault("deny", [])
    if DENY_RULE in deny:
        return False
    deny.append(DENY_RULE)
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


def project_config(project: Path) -> dict:
    cfg = project / CFG / "config.json"
    if not cfg.exists():
        sys.exit(f"{project} is not prepared: run `init` first.")
    return json.loads(cfg.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# setup, check, init
# --------------------------------------------------------------------------- #
DOWNLOAD = (
    "import sys\n"
    "from huggingface_hub import snapshot_download\n"
    "snapshot_download(repo_id=sys.argv[1], revision=sys.argv[2], local_dir=sys.argv[3], allow_patterns=sys.argv[4:])\n"
)


def cmd_setup(a) -> int:
    data = a.data
    data.mkdir(parents=True, exist_ok=True)
    py, uv = venv_python(data), shutil.which("uv")
    if not py.exists():
        print(f"Creating the environment in {data / 'venv'}")
        if uv:
            subprocess.run([uv, "venv", "--python", sys.executable, str(data / "venv")], check=True)
        else:
            subprocess.run([sys.executable, "-m", "venv", str(data / "venv")], check=True)
    install = [uv, "pip", "install", "--python", str(py)] if uv else [str(py), "-m", "pip", "install"]
    cpu = ["--index-url", "https://download.pytorch.org/whl/cpu"] if sys.platform.startswith("linux") else []
    print("Installing the packages (about 1 GB the first time)")
    subprocess.run(install + cpu + [TORCH], check=True)
    subprocess.run(install + PINS, check=True)
    target = model_dir(data)
    if a.model_from:
        target.mkdir(parents=True, exist_ok=True)
        for name in MODEL_FILES:
            shutil.copy2(Path(a.model_from) / name, target / name)
        print(f"Model copied from {a.model_from}")
    else:
        print(f"Downloading the model {eng.MODEL_REPO} at revision {eng.MODEL_REVISION[:12]} (about 1.2 GB)")
        subprocess.run([str(py), "-c", DOWNLOAD, eng.MODEL_REPO, eng.MODEL_REVISION, str(target), *MODEL_PATTERNS],
                       check=True, env=dict(os.environ, HF_HUB_DISABLE_SYMLINKS_WARNING="1"))
    missing = [n for n in MODEL_FILES if not (target / n).exists()]
    if missing:
        print("Model incomplete, missing: " + ", ".join(missing))
        return 1
    print("Setup complete. Run `check` in a project.")
    return 0


def cmd_check(a) -> int:
    data, project = a.data, a.project
    ok = True
    py = venv_python(data)
    print(f"Data folder: {data}")
    if py.exists():
        code = ("import importlib.metadata as m\n"
                "print(', '.join(f'{p} {m.version(p)}' for p in ['torch','transformers','python-docx','pypdf','openpyxl']))")
        res = subprocess.run([str(py), "-c", code], capture_output=True, text=True)
        print(f"Environment: {res.stdout.strip() or res.stderr.strip().splitlines()[-1]}")
        ok &= res.returncode == 0
    else:
        print("Environment: missing (run `setup`)")
        ok = False
    m = model_dir(data)
    have = [n for n in MODEL_FILES if (m / n).exists()]
    print(f"Model: {eng.MODEL_REPO} at {eng.MODEL_REVISION[:12]}, {len(have)}/{len(MODEL_FILES)} files")
    ok &= len(have) == len(MODEL_FILES)
    user_rule = has_deny_rule(claude_settings())
    print(f"Deny rule in the user settings ({claude_settings()}): {'present' if user_rule else 'missing'}")
    print("File mentions: " + ("off in the user settings, an @-mention passes the path" if file_mentions_off(claude_settings())
                               else "on, an @-mention attaches the whole file (set CLAUDE_CODE_DISABLE_FILE_MENTIONS=1 in the user settings)"))
    if (project / CFG / "config.json").exists():
        proj_rule = has_deny_rule(project / ".claude" / "settings.json")
        ignored = (project / ".gitignore").exists() and f"/{PRIVATE}/" in (project / ".gitignore").read_text(encoding="utf-8")
        rules = (project / RULES_FILE).exists()
        print(f"Project {project.name}: prepared; deny rule {'present' if proj_rule else 'missing'}; "
              f"private folder {'ignored by git' if ignored else 'NOT ignored by git'}; "
              f"working rules {'present' if rules else 'missing (run `init`)'}")
        ok &= (proj_rule or user_rule) and ignored and rules
    else:
        print(f"Project {project.name}: not prepared (run `init`)")
    print("Safety net on prompts and tool results: not installed (phase 2 of the design)")
    print("Ready." if ok else "Not ready: see the lines above.")
    return 0 if ok else 1


HEADERS = {
    "keep.txt": "# Terms never masked in this project, one per line: services, places, institutions, functional\n"
                "# mailboxes. No personal data here: Claude may read and extend this file.\n",
    "officials.txt": "# Names left in clear in this project: officials acting in their role (a mayor, a director).\n"
                     "# One name per line, as it is written in the documents. Claude may read this file.\n",
    "always.txt": "# Values masked wherever they appear, one per line: names the model misses, hamlets, nicknames.\n"
                  "# Optionally with a type: \"STREET: borgata Tora\". This file is personal data: Claude never reads it.\n",
}


# The skill starts only when the user types /aldogor-pseudonymize, so its rules are not in context in the
# project's later sessions. This file is: Claude Code loads every .claude/rules/ file of a project at the start
# of each session there. init writes it once and leaves an existing copy as the user may have changed it.
RULES_FILE = Path(".claude") / "rules" / "pseudonymize.md"
RULES_TEXT = """# Pseudonymized documents

This project masks the names and identifiers of people with aldogor-pseudonymize before Claude reads its
documents. The same rules hold in every session here, whether or not the skill is loaded.

- Read and write the masked copies in `masked/` and Claude's own drafts. Never open, list, search or print
  anything in `pseudonymize-private/`, with any tool or command, a script included.
- When the user mentions with @ a document outside `masked/` that may name people, do not read it: ask the
  user to put it in `pseudonymize-private/originals/` by hand and run /aldogor-pseudonymize.
- Keep every placeholder ([FULLNAME_3], [EMAIL_2], [CF_1]) exactly as written: the same placeholder is the
  same person in every document. Never guess who a placeholder is and never ask the user to say it.
- A value a draft needs and the table lacks is written [DA_COMPLETARE].
- A real name the user types in the chat never goes into a masked copy or a draft: use the placeholder the
  table already gives it, or ask the user to add the name to `pseudonymize-private/always.txt` and mask again.
- Masking new originals, the review page and the restore of a draft to real values run through
  /aldogor-pseudonymize, which the user starts.
"""


def cmd_init(a) -> int:
    p = a.project
    for d in (p / CFG, p / PRIVATE / "originals", p / PRIVATE / "restored", p / PRIVATE / "review", p / MASKED):
        d.mkdir(parents=True, exist_ok=True)
    written = []
    cfg = p / CFG / "config.json"
    if not cfg.exists():
        # Without "excluded_tags" the project follows the plugin's default list (eng.EXCLUDED_DEFAULT) as it
        # changes; a project that needs its own list adds the key.
        cfg.write_text(json.dumps({"version": 1, "detector": "rizzo-pii", "model_revision": eng.MODEL_REVISION},
                                  indent=2) + "\n", encoding="utf-8")
        written.append(f"{CFG}/config.json")
    for name, folder in (("keep.txt", CFG), ("officials.txt", CFG), ("always.txt", PRIVATE)):
        f = p / folder / name
        if not f.exists():
            f.write_text(HEADERS[name], encoding="utf-8")
            written.append(f"{folder}/{name}")
    gi = p / ".gitignore"
    lines = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    add = [l for l in (f"/{PRIVATE}/", f"/{MASKED}/") if l not in lines]
    if add:
        gi.write_text("\n".join(lines + add) + "\n", encoding="utf-8")
        written.append(".gitignore (" + ", ".join(add) + ")")
    if add_deny_rule(p / ".claude" / "settings.json"):
        written.append(f".claude/settings.json ({DENY_RULE})")
    rules = p / RULES_FILE
    if not rules.exists():
        rules.parent.mkdir(parents=True, exist_ok=True)
        rules.write_text(RULES_TEXT, encoding="utf-8")
        written.append(RULES_FILE.as_posix())
    print(f"Prepared {p.name}: " + ("; ".join(written) if written else "already prepared"))
    print(f"Put the originals in {PRIVATE}/originals/, then run `mask`.")
    return 0


# --------------------------------------------------------------------------- #
# mask, review, restore, status
# --------------------------------------------------------------------------- #
def load_context(project: Path, cfg: dict) -> eng.Context:
    ctx = eng.Context.load(LISTS, project / CFG, excluded=cfg.get("excluded_tags", eng.EXCLUDED_DEFAULT))
    ctx.load_always(project / PRIVATE / "always.txt")
    return ctx


def originals_of(project: Path):
    """The originals the engine reads, and how many other files sit beside them."""
    import pz_formats as fmt
    originals = project / PRIVATE / "originals"
    files = sorted(p for p in originals.rglob("*") if p.is_file() and p.suffix.lower() in fmt.SUPPORTED)
    others = sum(1 for p in originals.rglob("*") if p.is_file() and p.suffix.lower() not in fmt.SUPPORTED)
    return files, others


def start_fresh(project: Path) -> None:
    """Set the table, the masked names and the masked copies aside, so that `mask` starts numbering anew.
    They move into a dated folder of the private folder: the copies' placeholders mean nothing without
    their table, and nothing is deleted."""
    priv = project / PRIVATE
    names_file = priv / "files.json"
    names = json.loads(names_file.read_text(encoding="utf-8")) if names_file.exists() else {}
    backup = priv / f"backup-{time.strftime('%Y%m%d-%H%M%S')}"
    moved = 0
    for f in (priv / "table.json", names_file):
        if f.exists():
            backup.mkdir(parents=True, exist_ok=True)
            shutil.move(str(f), str(backup / f.name))
    for mname in names.values():
        copy = project / MASKED / mname
        if copy.is_file():
            (backup / MASKED).mkdir(parents=True, exist_ok=True)
            shutil.move(str(copy), str(backup / MASKED / mname))
            moved += 1
    if backup.exists():
        print(f"Started a new table: the earlier table, masked names and {moved} masked copies are in "
              f"{PRIVATE}/{backup.name}/.")


def cmd_mask(a) -> int:
    project_config(a.project)
    files, others = originals_of(a.project)
    if not files:
        print(f"No originals to mask in {PRIVATE}/originals/ ({others} files of formats not handled).")
        return 0
    if a.fresh:
        start_fresh(a.project)
    if a.detector == "regex-only":
        detector = eng.RegexOnlyDetector()
    else:
        print("Loading the model...")
        detector = eng.RizzoDetector(model_dir(a.data))
    return mask_project(a.project, detector)


def mask_project(project: Path, detector) -> int:
    """Mask every original of a project with a detector (any object with `name` and `detect_many`)."""
    import pz_formats as fmt
    cfg = project_config(project)
    ctx = load_context(project, cfg)
    priv = project / PRIVATE
    originals = priv / "originals"
    files, others = originals_of(project)
    table = eng.Table(priv / "table.json")
    names_file = priv / "files.json"
    names = json.loads(names_file.read_text(encoding="utf-8")) if names_file.exists() else {}
    docs = [fmt.read_document(p) for p in files]
    rel = [p.relative_to(originals).as_posix() for p in files]
    t0 = time.time()

    # One pass over the whole project: the people of the tables' name columns, the texts, and the free cells
    # of the tables go through the engine together, so a name found anywhere masks it everywhere.
    people = [n for d, r in zip(docs, rel) if d.kind == "table" for _, rows in d.sheets for n in fmt.table_people(rows, r)]
    texts, owners, sources, org = [], [], [], []
    for i, d in enumerate(docs):
        if d.kind == "text":
            texts.append(d.text)
            owners.append((i, None))
            sources.append(rel[i])
            org.append(False)
        elif d.kind == "table":
            free, where, in_org = fmt.sheet_free_cells(d.sheets)
            texts += free
            owners += [(i, w) for w in where]
            sources += [rel[i]] * len(free)
            org += in_org
    results = eng.mask_texts(texts, detector, table, ctx, sources, people=people, org=org)
    masked, by_table = {}, {}
    for (i, w), r in zip(owners, results):
        if w is None:
            masked[i] = r
        else:
            by_table.setdefault(i, []).append((w, r))
    sheets = {}
    for i, d in enumerate(docs):
        if d.kind == "table":
            pairs = by_table.get(i, [])
            sheets[i] = fmt.build_sheets(d.sheets, [w for w, _ in pairs], [r for _, r in pairs], table, rel[i])

    # Masked names: kept from earlier runs, so that Claude's references stay valid.
    todo = [i for i, r in enumerate(rel) if r not in names]
    for i, stem in zip(todo, eng.mask_names([files[i].stem for i in todo], detector, table, ctx)):
        name, n = stem, 2
        while name + docs[i].out_ext in names.values():
            name, n = f"{stem}_{n}", n + 1
        names[rel[i]] = name + docs[i].out_ext

    review = priv / "review"
    review.mkdir(parents=True, exist_ok=True)
    for old in review.glob("*.json"):
        old.unlink()
    out_dir = project / MASKED
    log, frequency = [], {}
    print(f"Masked into {MASKED}/ with {detector.name} (model revision {eng.MODEL_REVISION[:12]}):")
    for i, d in enumerate(docs):
        mname = names[rel[i]]
        record = {"original_name": rel[i], "masked_name": mname, "kind": d.kind}
        if d.kind == "skipped":
            record["note"] = d.note
            print(f"  one file skipped: {d.note} (named on the review page)")
            entry = {"masked_name": None, "skipped": d.note}
        elif d.kind == "text":
            r = masked[i]
            fmt.write_masked(d, r.text, out_dir / mname)
            misses = eng.possible_misses(d.text, r.spans, ctx)
            record.update(original=d.text, masked=r.text, flags=r.flags, misses=misses,
                          spans=[{k: e[k] for k in ("start", "end", "label", "ph", "source")} for e in r.spans])
            pairs = [(d.text[e["start"]:e["end"]], e["ph"]) for e in r.spans]
            entry = {"masked_name": mname, "counts": r.counts, "flags": len(r.flags), "misses": len(misses)}
        else:
            ms, cells = sheets[i]
            fmt.write_masked(d, ms, out_dir / mname)
            counts = {}
            for *_, m in cells:
                for ph in set(re.findall(r"\[[A-Z_]+_\d+\]", m)):
                    counts[table.entries[ph]["type"]] = counts.get(table.entries[ph]["type"], 0) + 1
            record["cells"] = cells
            pairs = [(orig, m) for *_, orig, m in cells]
            entry = {"masked_name": mname, "counts": counts, "flags": 0, "misses": 0}
        if d.kind != "skipped":
            for _, m in pairs:
                for ph in re.findall(r"\[[A-Z_]+_\d+\]", m):
                    frequency[ph] = frequency.get(ph, 0) + 1
            # The same sample at every run of the same document, for the precision count of the gate.
            record["sample"] = random.Random(mname).sample(pairs, min(SAMPLE, len(pairs)))
        if d.kind != "skipped":
            c = ", ".join(f"{k} {v}" for k, v in sorted(entry["counts"].items(), key=lambda x: -x[1])) or "nothing found"
            print(f"  {mname}: {c}; {entry['flags']} flags; {entry['misses']} possible misses")
        (review / f"{mname if d.kind != 'skipped' else 'skipped_' + str(i)}.json").write_text(
            json.dumps(record, ensure_ascii=False), encoding="utf-8")
        log.append(dict(entry, time=time.strftime("%Y-%m-%dT%H:%M:%S"), detector=detector.name,
                        model_revision=eng.MODEL_REVISION))
    (review / "_run.json").write_text(json.dumps({"added": table.added, "frequency": frequency}), encoding="utf-8")
    table.save()
    names_file.write_text(json.dumps(names, indent=1, ensure_ascii=False), encoding="utf-8")
    with (priv / "log.jsonl").open("a", encoding="utf-8") as f:
        for e in log:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    types = {}
    for e in table.entries.values():
        types[e["type"]] = types.get(e["type"], 0) + 1
    print(f"Table: {', '.join(f'{k} {v}' for k, v in sorted(types.items()))}; {len(table.added)} new this run. "
          f"{others} files of formats not handled. {time.time() - t0:.1f} s.")
    print("Next: run `review` and ask the user to open the page before reading a new copy.")
    return 0


def cmd_review(a) -> int:
    import pz_review
    project = a.project
    project_config(project)
    priv = project / PRIVATE
    out = priv / "review.html"
    n = pz_review.build(priv / "review", eng.Table(priv / "table.json"), out)
    print(f"Review page for {n} files: {out}")
    if a.open:
        if os.name == "nt":
            os.startfile(out)  # noqa: S606 (opens the user's browser)
        else:
            subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", str(out)], check=False)
    return 0


def cmd_restore(a) -> int:
    import pz_formats as fmt
    project = a.project
    project_config(project)
    src = Path(a.file).resolve()
    priv = (project / PRIVATE).resolve()
    if priv in src.parents:
        sys.exit("The file to restore is inside the private folder: restore works on masked copies and drafts.")
    out, n, unknown = fmt.restore_file(src, eng.Table(project / PRIVATE / "table.json"), project / PRIVATE / "restored", a.docx)
    print(f"Restored {n} placeholders into {out.relative_to(project).as_posix()} (for the user to open).")
    if unknown:
        print("Placeholders not in the table, left as they are: " + ", ".join(unknown))
    return 0


def cmd_status(a) -> int:
    project = a.project
    project_config(project)
    priv = project / PRIVATE
    table = eng.Table(priv / "table.json")
    masked = sorted(p.name for p in (project / MASKED).glob("*") if p.is_file())
    n_orig = sum(1 for p in (priv / "originals").rglob("*") if p.is_file())
    types = {}
    for e in table.entries.values():
        types[e["type"]] = types.get(e["type"], 0) + 1
    print(f"{n_orig} originals; {len(masked)} masked copies in {MASKED}/:")
    for name in masked:
        print(f"  {name}")
    print("Table: " + (", ".join(f"{k} {v}" for k, v in sorted(types.items())) or "empty"))
    return 0


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", type=Path, default=default_data_dir(), help="the plugin's data folder")
    ap.add_argument("--project", type=Path, default=Path.cwd(), help="the project folder (default: here)")
    sub = ap.add_subparsers(dest="command", required=True)
    s = sub.add_parser("setup")
    s.add_argument("--model-from", help="copy the model from a folder that already holds it")
    sub.add_parser("check")
    sub.add_parser("init")
    m = sub.add_parser("mask")
    m.add_argument("--detector", choices=["rizzo-pii", "regex-only"], default="rizzo-pii")
    m.add_argument("--fresh", action="store_true", help="start a new table, keeping the earlier one in the private folder")
    r = sub.add_parser("review")
    r.add_argument("--open", action="store_true", help="open the page in the browser")
    rs = sub.add_parser("restore")
    rs.add_argument("file")
    rs.add_argument("--docx", action="store_true", help="also convert a restored Markdown file to Word with pandoc")
    sub.add_parser("status")
    a = ap.parse_args(argv)
    a.data, a.project = a.data.resolve(), a.project.resolve()
    # mask and restore run inside the private environment when it exists. Without it, only what needs no
    # model and no Word or Excel reader can run: restoring text, masking with the regex net alone.
    if a.command in VENV_COMMANDS and not in_venv(a.data):
        if venv_python(a.data).exists():
            return rerun_in_venv(a.data)
        if a.command == "mask" and a.detector != "regex-only":
            sys.exit("The private environment is missing: run `setup` first.")
    return {"setup": cmd_setup, "check": cmd_check, "init": cmd_init, "mask": cmd_mask, "review": cmd_review,
            "restore": cmd_restore, "status": cmd_status}[a.command](a)


if __name__ == "__main__":
    sys.exit(main())
