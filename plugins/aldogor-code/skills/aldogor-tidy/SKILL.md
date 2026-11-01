---
name: aldogor-tidy
description: >-
  Reviews an existing project folder and puts it in order: names that say what files are, no stale or duplicated documents, related files grouped, nothing that misleads. Inventories the tree, proposes renames, merges, moves and deletions as a table, applies what the user approves and repairs every reference the changes break. Use when the user asks to tidy, clean up or reorder a project or folder ("aldogor-tidy", "tidy", "cleanup", "riordina", "fai ordine", "sistema la cartella", "metti in ordine il progetto"), or when another skill, aldogor-handoff at the close of a session among them, finds disorder that runs across a folder.
---

# Aldogor-tidy

"Cleanup" has a precise meaning for this user: looking at a folder and seeing sense. Names that say what files are, no stale or duplicated documents, related files grouped, nothing that misleads. Curation is incremental: a file correctly named last month may need renaming, merging or moving today because the project moved.

Scope: the docs/ tree and the project-level documents (README, notes, plans, JOURNAL.md) of the current project; code files only on explicit request. Never touch data/raw/, gitignored private material, anything CLAUDE.md marks as do-not-modify or historical, or the content of dated frozen copies.

1. Read the project's CLAUDE.md and README for its stated conventions; they outrank generic taste. The conventions check of aldogor-handoff (its `scripts/check_project.py`, run in the project) lists what the project breaks among the conventions a script can test; the review below covers the judgments. Where a project states none, these apply (the layout of aldogor-project-setup): descriptive kebab-or-snake names, working files without dates, frozen copies dated in archive/, literature in one folder with bibliography.json tracked and the texts local, folders by function, JOURNAL.md in the root. A TODO.md, a CHANGELOG or a "modifiche" section is a finding.
2. Inventory the target tree, one line per file saying its role; a role that cannot be stated in one line is a finding.
3. Evaluate, with evidence: misnamed (the name no longer describes the content or breaks the convention), stale (superseded, dead references, a state long past; dates and contradictions, never age alone), merge candidates (one topic in two files, or a fragment that only makes sense inside another document), grouping (files that belong together and sit apart, with the folder proposed). Maintained tools do the mechanical part, run without being added to the project: `npx jscpd <folders>` finds passages repeated across documents and code; when code is in scope, `uvx ruff check` (Python) and `npx knip` (JavaScript and TypeScript, which needs typescript and @types/node in the project) find dead code and unused files, exports and dependencies.
4. Propose the plan as a table: action (rename, merge into, move, delete, leave), target, one-line reason. Deletions only for true duplicates or generated artifacts; unique content merges or archives. Wait for approval, item by item if the user wants.
5. Apply the approved items, then repair what the moves broke: every reference to a renamed or moved path in docs, README, CLAUDE.md, code comments and scripts. In git projects, `git mv` and a commit listing the mapping.
6. Report what is now true: the resulting tree, one line per change, what was declined.

The pass at the close of a working session, limited to what the session touched and the documents CLAUDE.md points to, belongs to aldogor-handoff, which offers this skill when that pass finds disorder across the folder.
