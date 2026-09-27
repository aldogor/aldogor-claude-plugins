# The project's literature folder

A project keeps the sources it cites in one flat folder: `literature/` at the repository root, or `docs/literature/` where a development repository keeps its research side in `docs/`.

- `bibliography.csv` is the master record and the only file of the folder that git tracks: one row per source, with its identifiers, access and licence, where it is cited and what text is held. Collaborators receive it with the repository.
- `<key>.pdf` is the full text when a legal copy exists; `<key>.md` is the text Claude reads, and its YAML header says in `text_source` whether it holds the full text, the abstract only or the metadata only. Both stay local: the repository's `.gitignore` carries `literature/*` and `!literature/bibliography.csv` (with the folder's own path), because publishers' PDFs and their text cannot be passed on, and a file committed once stays in the history.
- Keys name both files and serve as citation keys. A new library uses `Surname_Year` (`Iyamu_2021`, `DelReyPuech_2026`, `WHO_2025`; a second work of the same author and year gets `b`, then `c`). A library whose keys are citation keys in the form author, year, first title word (`alonzo2021interplay`) keeps that form. Keys already in a library are never renamed.

## The script

In Claude Code, `scripts/literature.py` in this skill's folder manages the folder, run with Python from anywhere inside the project (it finds the library from the working directory up to the repository root, or takes `--lib`). It needs `python -m pip install requests lxml pymupdf pymupdf4llm`, on any platform.

| Command | What it does |
| --- | --- |
| `add DOI [--key K] [--cited-in T] [--title T] [--pdf PATH]` | a new row from Crossref (or Europe PMC), the abstract, the legal open-access full text and its Markdown; the first `add` in a project creates the library and its `.gitignore` lines |
| `fetch [KEY ...]` | tries the open-access sources again for the works whose full text is not in the folder, and writes their Markdown |
| `collect [--from DIR]` | files the PDFs the user downloaded in the browser (default: Downloads), identified by key, DOI or title |
| `md [KEY ...] [--force]` | rewrites `<key>.md` from the PDF, the abstract or the metadata |
| `check` | the CSV against the files: missing, extra or misnamed files, duplicate keys or DOIs; exit code 1 on problems |
| `bib [--out PATH]` | BibTeX of the whole library, for pandoc and LaTeX |

The script fetches only legal free copies (the PMC open-access set, Europe PMC, the open locations OpenAlex and Semantic Scholar list, and a local folder given with `--archive`), never through an institutional login, never from ScienceDirect or Wiley by script, and stops at any anti-bot check; the user downloads those copies in the browser and `collect` files them. A PDF is kept only when the work's title is printed on its first pages.

A source without a DOI (a report, a web page) is a row written by hand: key, authors, year, title, source, kind, url, access. Its PDF placed in the folder as `<key>.pdf` gets its Markdown with `md <key>`.

## A fresh clone

A collaborator's clone holds `bibliography.csv` as the owner's machine wrote it and none of the files, so `check` reports in one line that the works have no local files. `fetch` restores what can legally travel: it reads from the folder, not from the `full_text` column, which works lack their text, downloads their open-access copies, writes each Markdown (the full text where a copy was found, the abstract otherwise) and sets `full_text` and `pdf` to what the folder now holds. The collaborator then downloads the remaining copies in the browser, through their own access, and `collect` files them; a report without a DOI comes back the same way, saved as `<key>.pdf`.

## Reading and verifying

Claude reads a source through `<key>.md`. Support for a claim (step 2 of the verification loop) needs the full text: a Markdown holding the abstract only supports a claim only as far as the abstract states it, and its verdict says so. After adding or changing sources, `check` runs before the work is committed.

## An older folder

A folder built another way (PDFs tracked in git, a README table, extracts in other formats) converts in the project's own session: each source with a DOI is added again with `add DOI --key <its existing key>`, the others become rows written by hand, the PDFs and extracts leave the index (`git rm --cached`, the files stay on disk) and the `.gitignore` lines are added; `check` then reports what is left. The copies already in the git history stay there unless the history is rewritten, which matters only before the repository is shared.
