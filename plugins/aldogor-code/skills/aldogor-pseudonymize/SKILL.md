---
name: aldogor-pseudonymize
description: >-
  Masks the names and identifiers of people in a project's documents on the user's machine before Claude reads them: colleagues, staff, citizens and patients become numbered placeholders ([FULLNAME_3], [EMAIL_2], [CF_1]) shared across the project, the originals and the table that restores them stay in a private folder that Claude's permission rules block, and Claude's drafts get the real values back in a file only the user opens. Built for Italian documents of a health authority (internal emails, procedures, minutes, circulars, contact lists, letters) in Word, PDF with text, Excel, CSV, Markdown and plain text. Started only by the user, who types /aldogor-pseudonymize to pseudonymize, anonymize or mask documents before working on them ("pseudonimizza", "anonimizza", "maschera i nomi", "togli i nomi", "nascondi i dati personali", "documenti ASL", "pseudonymize", "anonymize", "redact names"); a prepared project keeps its working rules in .claude/rules/pseudonymize.md, which hold in every session there.
disable-model-invocation: true
---

# aldogor-pseudonymize

The model never sees who the documents are about. A local Italian model (rizzo-pii) with checksum rules finds people and identifiers; each becomes a placeholder that is the same in every document of the project; Claude reads and writes placeholders only; the user gets real values back in files Claude never opens.

The masked copies are pseudonymized, not anonymous: they remain personal data, and a description such as "the only nurse of a small hamlet" identifies a person without a name. When a project is first prepared, say once that whether these documents may be processed with an external service is a decision of the user's organization and its data protection officer.

## The command

From the project folder:

```
python "${CLAUDE_PLUGIN_ROOT}/skills/aldogor-pseudonymize/scripts/pseudonymize.py" --data "${CLAUDE_PLUGIN_DATA}" <command>
```

(`python3` on macOS and Linux.) Nothing it prints contains an original value or the name of an original file, which is why Claude reads its output and never the private folder.

| Command | What it does |
|---|---|
| `setup` | Once per machine: the private environment and the model, about 1.5 GB and 15 minutes; run it in the background |
| `check` | The environment, the model, and the guard of the current project |
| `init` | Once per project: the folders, the lists, the `.gitignore` lines, the deny rule and the working rules |
| `mask [--fresh]` | Every original in `pseudonymize-private/originals/` to a copy in `masked/`, the project table updated; `--fresh` starts a new table and sets the earlier one, with its copies, aside in the private folder |
| `review --open` | The review page, opened in the user's browser |
| `restore <file> [--docx]` | A draft with placeholders to real values in `pseudonymize-private/restored/`; `--docx` turns Markdown into Word with pandoc |
| `status` | The masked copies by name and the table's counts |

## Layout of a prepared project

```
.pseudonymize/config.json   marker and settings
.pseudonymize/keep.txt      terms never masked (Claude may read and extend it)
.pseudonymize/officials.txt officials left in clear when acting in role (Claude may read and extend it)
.claude/rules/pseudonymize.md the working rules, loaded in every session of the project
pseudonymize-private/       originals, table.json, always.txt, review.html, restored/: the user's only
masked/                     the copies Claude reads
```

Both `pseudonymize-private/` and `masked/` are ignored by git: the copies still hold health and work data. `init` adds `Read(pseudonymize-private/**)` to the project's `.claude/settings.json`; the same rule in the user's own settings covers sessions opened in a parent folder, and `check` reports both. The skill starts only on /aldogor-pseudonymize, so `init` also writes `.claude/rules/pseudonymize.md`, the rules of step 4 and of the list below, which Claude Code loads in every later session of the project; an existing copy is left as the user keeps it.

## Workflow

1. Ask the user to put the originals in `pseudonymize-private/originals/` themselves, by hand. A copy command run by Claude would carry their file names into the conversation. With `CLAUDE_CODE_DISABLE_FILE_MENTIONS=1` in the user's settings (`check` reports it; Claude Code ignores it in a project's settings) an @-mention gives Claude only the path: do not read a mentioned document that may name people unless it is in `masked/`. Without it, an @-mention attaches the whole file before anything is masked (inside the private folder the deny rule refuses the attachment); when that happens, say at once that its content has reached the model.
2. Run `mask` and give the user its summary: counts by type, flags, possible misses, per masked file.
3. For every document not reviewed before, run `review --open` and ask the user to read the page before Claude reads the copy. The page lists the placeholders by how often they occur, so a common word masked by mistake stands at the top, and ends each document with a fixed sample of 30 masked values on which the user counts the wrong ones. Misses go into `pseudonymize-private/always.txt`, which the user edits; terms masked by mistake go into `.pseudonymize/keep.txt`, and officials to leave in clear into `.pseudonymize/officials.txt`, which Claude may edit on the user's word. Then run `mask` again: masked names and placeholders stay stable across runs.
4. Work on `masked/` only. Keep every placeholder exactly as written: the same placeholder is the same person in every document, and the words around it (la signora, il dott.) carry gender and role. Never guess who a placeholder is and never ask the user to say it. A value a draft needs and the table lacks is written `[DA_COMPLETARE]`.
5. Run `restore` on the draft and give the user the path of the restored file. Placeholders the table lacks are reported and left as they are.

## What Claude never does

- Open, read, list, search or print anything in `pseudonymize-private/`, with any tool or command, a script included; the permission rules stop the file tools and the commands Claude Code recognizes, not a script that opens files itself.
- Commit `pseudonymize-private/` or `masked/`, or move their content elsewhere.
- Write into a masked copy or a draft a real name the user typed in the chat: use the placeholder the table already gives it, or ask the user to add the name to `always.txt` and run `mask` again.

## On claude.ai

No hook or rule runs there. The user runs the same command in a terminal, with `--project` pointing at the project folder, uploads the masked copy, and saves Claude's answer as a file to `restore`. Give the user the full commands with the paths of this installation.

## Limits

- A name the model misses passes in clear: the review page is where the user catches it, and `always.txt` keeps it masked from then on.
- The people of a large table (more than 50, a staff census or a contact list) are masked elsewhere by full name, in either order, and by surname with initial; a surname or a first name alone is masked once a document names that person.
- In a table column that names an organisation unit (Servizio, Reparto, Centro di costo and its description) the model's people are set aside, because hospitals, wards and towns there bear people's names: a person named there without a title, and unknown to the rest of the project, stays in clear.
- Descriptions that identify without naming, PDFs without a text layer (scans), Outlook `.msg` and `.eml` files are not handled.
- Text typed or pasted in the chat reaches the model as it is: the safety net on prompts is a later phase of the plugin. Paste from the masked copy.
