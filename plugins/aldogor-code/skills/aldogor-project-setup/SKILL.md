---
name: aldogor-project-setup
description: >-
  Scaffolds a new project the user's way and keeps an existing one in order. Use when the user asks to create or set up a project or repository ("new project", "nuovo progetto", "scaffold", "aldogor-project-setup", "git init"), to add JOURNAL.md to a project, or to tidy a folder ("cleanup", "tidy", "riordina", "fai ordine", "sistema la cartella", "aldogor-tidy"): required files, research tree, journal, development-or-research choice, private GitHub repo; naming and staleness review with a plan applied after approval.
---

# Aldogor-project-setup

Every new project starts the same way; this skill carries the checklist so no session reinvents it. The two questions it must ask before scaffolding, in this order: is this a development project or a research project; may the repository ever become public. Never skip to the scaffold without the answers.

## Required files, any project

- `.env` (never committed) and `.env.example` (placeholders, committed)
- `.gitignore` including at least: `.env`, `__pycache__/`, `.DS_Store`, `*.log`
- `README.md`: first paragraph must be able to stand alone as the repo description
- `git init`, first commit after the skeleton exists; rename the branch to `main` before any push

## Research-project structure

For research projects (protocols, papers, reviews, data work), the base tree:

```
project/
├── docs/         # working documents: protocol, note, drafts, deliverables
├── literature/   # sources: bibliography.csv tracked, their PDFs and texts local
├── archive/      # frozen copies sent to others, superseded versions, imported chat history
├── JOURNAL.md    # the why, and what is open
├── CLAUDE.md
└── README.md
```

When the project has data (analyses, extractions, datasets), add the data subtree; do not create it empty for a writing-only project:

```
├── data/
│   ├── raw/          # original data, never modified
│   └── processed/    # cleaned/transformed data, tidy
├── scripts/          # analysis code
└── outputs/          # results, figures, tables
```

`data/raw/` immutability and "preserve originals, log transformations" are absolute rules, worth restating in the project's CLAUDE.md. Processed data is tidy: one table per file, one observation per row, one variable per column, one value per cell, plain CSV with a codebook next to it (variable, type, unit, allowed values, source); the scripts that produce it are the transformation log.

Literature: one flat folder, `literature/` (`docs/literature/` in a development repository whose research side lives in `docs/`), managed with the literature script of aldogor-research (`scripts/literature.py`, described in its references/literature.md). `bibliography.csv` is the master record and the only file of the folder git tracks; each source's `<key>.pdf` and `<key>.md` stay local (`.gitignore`: `literature/*` and `!literature/bibliography.csv`), because publishers' PDFs and their text cannot be passed on and a committed file stays in the history. Keys are `Surname_Year`, with b and c for a second and third work of the same author and year. The first source added creates the folder and its `.gitignore` lines.

Frozen copies: working documents live in `docs/` without a date in the name; the moment a document is sent to others, a dated copy goes to `archive/` (`nota-progetto_v1_2026-07-14.md`) and is never edited; it is the base for the diff at the next send. Superseded documents and the imported claude.ai history also live in `archive/`.

Development projects take their stack's layout: `src/`, `tests/`, `scripts/`, `docs/`, and the folders the stack itself brings (`public/` and `assets/` on the web, `app/` and `gradle/` on Android). In any project, a top-level folder outside these trees gets its line in CLAUDE.md saying what it holds: a folder the project needs is described there, and one nobody can describe is drift. The conventions check of aldogor-handoff reports the folders CLAUDE.md does not describe.

## Development or research?

Ask explicitly: "Is this a development project or a research project?" A research project that also builds software (analysis pipelines, generators, an app attached to the study) takes the development toolkit; research is the default when the answer is unclear. The answer sets the plugins and the journal, described next, and the git practice written into CLAUDE.md (below), which becomes the shared one as soon as collaborators push to the repository.

Research projects load no development plugins, and there is nothing to switch off: none is enabled at user scope.

Development projects get the toolkit at project scope, installed from the project directory and recorded in its `.claude/settings.json` (commit it):

```
claude plugin install superpowers@claude-plugins-official --scope project
```

```
claude plugin install security-guidance@claude-plugins-official --scope project
```

plus the language server that matches the stack, read from the files present: `package.json` or `tsconfig.json` means `typescript-lsp`, Python (`pyproject.toml`, `requirements.txt`, `*.py`) means `pyright-lsp`, both when both are there; a web front end also gets `frontend-design`. When the stack cannot be read, as in a new empty codebase, ask which languages the project will use. A language server needs its program on the PATH: check with `typescript-language-server --version` or `pyright-langserver --version`, and when it is missing give the user the one install command (`npm install -g typescript-language-server typescript`, `npm install -g pyright`). The committed settings file enables the plugins and installs nothing: each machine installs them for the folder (these commands, or the trust prompt for a collaborator), and a plugin enabled there with no install for the folder does not load, which the conventions check of aldogor-handoff reports.

Research projects also get `JOURNAL.md`, described next, unless the user says git alone is enough for this one (a small analysis, a single script). Development projects skip it unless the user asks for it (long-lived work with many design decisions or collaborators who do not read git).

## The project journal: JOURNAL.md

Two questions, two tools. Git holds *what changed*, so no CHANGELOG. `JOURNAL.md` holds *why* and *what is open*: a dated, chronological record of verifications made, evidence gathered, decisions with their rationale, ideas discarded, and at its end the one list of what remains open, with each item's state. It lives in the project root next to README.md and CLAUDE.md, because it is a project file, not project content; deliverables live in docs/. Not an ADR set (one file per decision is too rigid for research work), not a journal inside docs/, not a separate task file.

The journal pays off where something human-readable beyond git is needed: research projects, long documents, protocols, work with many methodological decisions, collaborators who do not read git. Where git suffices (small code, scripts, configuration repos) it is not created.

One section per session that verified or decided something, headed by the ISO date (a range when the work spanned days: `## 2026-07-14 / 2026-07-17`). Entries are concise but complete: they carry the data (counts, yields, measurements) and the sources (DOI or URL) that motivate a decision, not a summary of the conversation. Consolidated decisions do not live here but in the project's canonical document (protocol, note, CLAUDE.md): the journal records the intermediate evidence that motivates them and the doubts not yet resolved. Decisions about how the work is organized belong here with their reason; lists of files created, moved or renamed and editorial rules applied do not: the journal is not a changelog.

The journal ends with a single open list, `## Open` (`## Aperto` in Italian projects), kept after the last dated entry and edited in place: every open node and pending task, one line each, with its state (open, in progress, or waits on what unblocks it) and, where useful, a pointer to the section of the canonical document where it closes. The next session's priority comes first. A new entry goes above the list, and ends with one line naming what it opened and what it closed (`Opened: ...; closed: ...`), so the history of the list lives in the entries and the list itself holds only the present. A node closes only when the decision is written in the canonical document and reflected in the linked files (CLAUDE.md, README); it leaves the list in the same edit that records its closing. A fresh session reads the open list.

A journal that still ends each entry with its own `### Open as of <date>` (`### Aperto al <data>`) converts once, in a commit of its own: the latest of those lists becomes `## Open` at the end, and the older ones are removed, since git keeps them.

The journal is written in the project's language, taken from its README or CLAUDE.md, and the labels that other skills look for are fixed per language: `## Open` / `## Aperto`, `open, in progress, waits on` / `aperto, in corso, in attesa di`, `Opened:` / `Aperti:`, `closed:` / `chiusi:`. Header (English shown; the Italian rendering follows the same wording):

```markdown
# Journal

Dated record of the project's verifications, decisions and open questions. Consolidated decisions live in <canonical document> and in CLAUDE.md; here are the intermediate evidence behind them and the ideas discarded, and at the end the list of what is still open. Git holds what changed.
```

Italian: `# Journal` with "Registro cronologico delle verifiche, delle decisioni e delle questioni aperte del progetto. Le decisioni consolidate stanno in <documento canonico> e nel CLAUDE.md; qui stanno le evidenze intermedie che le motivano e le idee scartate, e in fondo l'elenco di ciò che resta aperto. Git tiene il cosa è cambiato."

## Project conventions to seed

State these in the project's CLAUDE.md so later sessions and tidy passes find them there:

- Git is the changelog: no CHANGELOG.md, no "modifiche" or "changelog" sections in documents; the reasoning behind a change goes in JOURNAL.md, the change itself in the commit message.
- Commit at every consolidated decision or completed step; at the end of a session, say what is not on the remote and ask whether to push. A repository kept local on purpose states that it has no remote and is never pushed.
- The git practice, one line naming the project's kind, which aldogor-handoff applies at every close:
  - research: all work on `main`, committed as it consolidates;
  - development: `main` always passes its tests; each feature or fix gets its own branch (or the worktree the desktop app creates), merged into `main` when its tests pass and then deleted, locally and on the remote;
  - shared (collaborators may edit the repository): the development practice, with every branch reaching `main` through a pull request that the owner merges.
- Working files carry no date in the name; a dated copy goes to `archive/` when a document is sent to others and is never edited afterwards.
- For projects with data: `data/raw/` is immutable; processed data is tidy CSV with a codebook; every transformation is a script.

## Project CLAUDE.md

Offer a starter CLAUDE.md: what the project is (2-3 sentences), where authority lives (which doc owns what), the 3-5 rules easiest to break by accident, the conventions above, and a "Key files" ("File chiave") list with one line per file saying what it holds and when to update it. The journal appears once, in the authority table or in the key files, never in both. Its line reads, in the project's language (adapt the canonical document's name):

```markdown
- `JOURNAL.md`: dated record of verifications, intermediate decisions and what is open (the *why*; git holds *what changed*). Update it, with the date, in every session that verifies or decides something; its closing "Open" list is the project's state.
```

Italian: "`JOURNAL.md`: registro datato di verifiche, decisioni intermedie e questioni aperte (il *perché*; git tiene il *cosa è cambiato*). Aggiornarlo a ogni sessione che verifica o decide qualcosa, con la data; l'elenco "Aperto" in fondo è lo stato del progetto."

Keep it lean; facts and invariants, not tutorials. The README's structure tree lists the journal with the same one-line role.

## History from a claude.ai project (optional)

When the project continues work started in a claude.ai Project, its chats and memory block can be distilled into the journal, and its knowledge documents kept in `archive/`, with the aldogor-chat-export skill, a repo-local skill of the aldogor-claude-setup repo (.claude/skills/), next to the claude.ai data export, run from a session there. Offer it once, as a pointer.

## Visibility, decided once

Before the first commit, ask whether the repository may ever become public. Private forever (research, institutional, personal): JOURNAL.md is versioned. Public, or possibly public later: two repositories. `<name>-internal`, private, holds all the work and its whole history, journal included; `<name>`, public, receives only what `publish.txt` at the private root lists, one commit per publication, through the publish script of aldogor-share, into a sibling clone that nobody works in. Only the GitHub name carries the suffix: the private repository is cloned in the folder `<name>`, and the public one in the sibling folder `<name>-public`, which is publish.txt's `target:`. The public repository never receives the private history, and a new file stays private until the list names it. A repository kept local on purpose (identity data, credentials) has no off-machine copy: remind the user that it needs an offline backup, and write that in its README.

## GitHub

Once the first commit exists, ask whether to create the remote, unless the repository is local on purpose: a repository with no remote has no off-machine copy. Private repo with proper metadata, one command plus topics, named `<name>-internal` when the project may become public:

```
gh repo create <name> --private --source . --push --description "<one sentence: what it is, who it is for>" --disable-wiki
```

```
gh repo edit --add-topic <ecosystem> --add-topic <artifact-type> --add-topic <domain>
```

Convention: every repo gets a one-sentence description, three to six topics (ecosystem, artifact type, domain), wiki disabled unless used.

## Tidy an existing project

"Cleanup" has a precise meaning for this user: looking at a folder and seeing sense. Names that say what files are, no stale or duplicated documents, related files grouped, nothing that misleads. Curation is incremental: a file correctly named last month may need renaming, merging or moving today because the project moved.

Scope: the docs/ tree and the project-level documents (README, notes, plans, JOURNAL.md) of the current project; code files only on explicit request. Never touch data/raw/, gitignored private material, anything CLAUDE.md marks as do-not-modify or historical, or the content of dated frozen copies.

1. Read the project's CLAUDE.md and README for its stated conventions; they outrank generic taste. The conventions check of aldogor-handoff (its `scripts/check_project.py`, run in the project) lists what the project breaks among the conventions a script can test; the review below covers the judgments. Where none exist, the conventions above apply: descriptive kebab-or-snake names, working files without dates, frozen copies dated in archive/, literature in one folder with bibliography.csv tracked and the texts local, folders by function, JOURNAL.md in the root. A TODO.md, a CHANGELOG or a "modifiche" section is a finding.
2. Inventory the target tree, one line per file saying its role; a role that cannot be stated in one line is a finding.
3. Evaluate, with evidence: misnamed (the name no longer describes the content or breaks the convention), stale (superseded, dead references, a state long past; dates and contradictions, never age alone), merge candidates (one topic in two files, or a fragment that only makes sense inside another document), grouping (files that belong together and sit apart, with the folder proposed). Maintained tools do the mechanical part, run without being added to the project: `npx jscpd <folders>` finds passages repeated across documents and code; when code is in scope, `uvx ruff check` (Python) and `npx knip` (JavaScript and TypeScript, which needs typescript and @types/node in the project) find dead code and unused files, exports and dependencies.
4. Propose the plan as a table: action (rename, merge into, move, delete, leave), target, one-line reason. Deletions only for true duplicates or generated artifacts; unique content merges or archives. Wait for approval, item by item if the user wants.
5. Apply the approved items, then repair what the moves broke: every reference to a renamed or moved path in docs, README, CLAUDE.md, code comments and scripts. In git projects, `git mv` and a commit listing the mapping.
6. Report what is now true: the resulting tree, one line per change, what was declined.

The pass at the close of a working session, limited to what the session touched and the documents CLAUDE.md points to, belongs to aldogor-handoff.
