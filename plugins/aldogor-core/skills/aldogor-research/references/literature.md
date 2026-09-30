# The project's literature folder

A project keeps the sources it cites in one flat folder: `literature/` at the repository root, or `docs/literature/` where a development repository keeps its research side in `docs/`.

- `bibliography.json` is the record and the only file of the folder that git tracks: a CSL JSON array, one entry per work, sorted by id, which Pandoc reads as it is (`--bibliography=literature/bibliography.json`). An entry keeps what identifies and cites the work (`id`, `type`, `title`, `language` for a title not in English, `author`, `issued`, `container-title` or `publisher`, `volume`, `issue`, `page`, `DOI`, `PMID`, `PMCID`, and `URL` for a work without a DOI) and, in its `custom` object, what the project writes about it: `cited_in`, where the project uses it, and `summary`, a description written for a work without an abstract. Any other field, or custom key, is kept as found. Collaborators receive the record with the repository.
- `<key>.pdf` is the full text when a legal copy exists; `<key>.md` is the text Claude reads: the full text, else the abstract, else the summary or the metadata. Its YAML header says which in `text_source`, with the work's licence. Both stay local: the repository's `.gitignore` carries `literature/*` and `!literature/bibliography.json` (with the folder's own path), because publishers' PDFs and their text cannot be passed on, and a file committed once stays in the history.
- Nothing in the record describes one machine or goes stale: what the folder holds is read from the folder, and what a source gives again (the abstract, the licence, the open-access status, update notices) is looked up when needed; retractions and corrections are read at delivery, as the verification loop says.
- Keys are the entries' ids, name both files and serve as citation keys. A new library uses `Surname_Year` (`Iyamu_2021`, `DelReyPuech_2026`, `WHO_2025`; a second work of the same author and year gets `b`, then `c`). A library whose keys are citation keys in the form author, year, first title word (`alonzo2021interplay`) keeps that form. Keys already in a library are never renamed.
- Titles are kept as the source deposited them. A reference list that needs one in another case (CSL styles expect sentence case) gets it corrected in its own entry.

## The script

In Claude Code, `scripts/literature.py` in this skill's folder manages the folder, run with Python from anywhere inside the project (it finds the library from the working directory up to the repository root, or takes `--lib`). It needs `python -m pip install requests lxml pymupdf pymupdf4llm`, on any platform.

| Command | What it does |
| --- | --- |
| `add DOI [--key K] [--cited-in T] [--title T] [--note T] [--pdf PATH]` | a new entry from Crossref (or Europe PMC), and the legal open-access full text or else the abstract in its Markdown; `--note` becomes the summary when no abstract exists; the first `add` in a project creates the library and its `.gitignore` lines |
| `fetch [KEY ...]` | tries the open-access sources again for the works whose full text is not in the folder, and writes their Markdown |
| `collect [--from DIR]` | files the PDFs the user downloaded in the browser (default: Downloads), identified by key, DOI or title |
| `md [KEY ...] [--force]` | rewrites `<key>.md` from the PDF; a work without a PDF gets a missing Markdown from its summary or metadata |
| `check [--fix]` | the record (layout, duplicate ids or DOIs, CSL types) and its agreement with the files; exit code 1 on problems; `--fix` first rewrites the record in the script's layout |
| `list [KEY ...] [--csv PATH]` | each work with the text the folder holds for it; `--csv` writes the table for a spreadsheet, R or Python |
| `convert` | turns an older `bibliography.csv` into `bibliography.json`, once, with no network call |

`--json`, before the command, prints one JSON object on standard output and the messages on standard error. Exit codes: 0 done, 1 check found problems, 2 refused (usage, a DOI or key that does not fit, no library, an unreadable record), 3 a source the command needs could not be reached. The tests run on the fixtures in `scripts/fixtures/`.

The script fetches only legal free copies (the PMC open-access set, Europe PMC, the open locations OpenAlex and Semantic Scholar list, and a local folder given with `--archive`), never through an institutional login, never from ScienceDirect or Wiley by script, and stops at any anti-bot check; the user downloads those copies in the browser and `collect` files them. A PDF is kept only when the work's title is printed on its first pages.

A source without a DOI (a report, a web page) is an entry written by hand: `id`, `type`, `title`, `author` (an organisation as `{"literal": "World Health Organization"}`), `issued`, `publisher` or `container-title`, `URL`, and `custom.summary` when it has no abstract. Its PDF placed in the folder as `<key>.pdf` gets its Markdown with `md <key>`. After a hand edit, `check` reports anything out of the script's layout, and `check --fix` puts it back.

For LaTeX or Typst, `pandoc bibliography.json -t biblatex -o references.bib` writes a `.bib`; Zotero imports the JSON as it is.

## A fresh clone

A collaborator's clone holds `bibliography.json` and none of the files, so `check` reports in one line that the works have no Markdown. `fetch` restores what can legally travel: it downloads the open-access copies and writes each Markdown, the full text where a copy was found and the abstract otherwise. `md` writes the Markdown of the works without a DOI from their summary or metadata. The collaborator then downloads the remaining copies in the browser, through their own access, and `collect` files them; a report without a DOI comes back the same way, saved as `<key>.pdf`.

## Reading and verifying

Claude reads a source through `<key>.md`. Support for a claim (step 2 of the verification loop) needs the full text: a Markdown holding the abstract only supports a claim only as far as the abstract states it, and its verdict says so. After adding or changing sources, `check` runs before the work is committed.

## An older folder

A folder that still keeps `bibliography.csv` converts once with `convert`, in the project's own session: it writes `bibliography.json` from the rows with no network call, moves each abstract into its `<key>.md` where that file is missing or holds the metadata only, leaves any Markdown whose header does not say what it holds, updates `.gitignore` and deletes the CSV. It lists the kinds it recorded as the CSL type `document` and the entries whose single literal author may be a list of persons, which are split into names by hand; `md` then writes the full-text Markdown of the works whose PDF is in the folder, and `check` reports what is left.

A folder built another way (PDFs tracked in git, a README table, extracts in other formats) converts in the project's own session too: each source with a DOI is added again with `add DOI --key <its existing key>`, the others become entries written by hand, the PDFs and extracts leave the index (`git rm --cached`, the files stay on disk) and the `.gitignore` lines are added; `check` then reports what is left. The copies already in the git history stay there unless the history is rewritten, which matters only before the repository is shared.
