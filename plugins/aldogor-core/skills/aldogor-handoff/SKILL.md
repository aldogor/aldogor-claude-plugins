---
name: aldogor-handoff
description: >-
  Closes a working session and leaves the project in order: brings the state document and the project's JOURNAL.md up to date, reviews the documents a later session reads first (the files the session touched, CLAUDE.md, README and the documents CLAUDE.md points to) so that they agree with the work as it is, commits and asks whether to push, and writes a minimal continuation prompt. Use when the user says "aldogor-handoff", "handoff", "prompt per la prossima chat", "prepara il passaggio", "chiudi la sessione", "gimme next prompt", or is ending a long session that continues elsewhere.
---

# Aldogor-handoff

A handoff has four parts, in this order: the state lands in the documents that own it, those documents are brought into agreement with the work as it now is, the repository takes the commit, and the next session gets a short pointer. The prompt is not the store; the documents are.

## 1. The canonical state

Find where this work's state lives and bring it current:

- In a project with a state document (a context file, a "Current state" section): update it there, in final-state prose, with no session narrative.
- In a chat project: update, or produce for re-upload, the context file the project already uses.
- If no state document exists yet, create the smallest one that fits the project's conventions and say where it now lives.

What goes in: decisions taken, current status, open items with what unblocks them. What stays out: the conversation's history, preferences and standing rules, anything the documents already say, lists of files touched (git is the changelog).

## 2. The journal, when the project has one

If `JOURNAL.md` exists in the project root, it gets one section headed by today's ISO date (`## 2026-08-18`, or a range if the work spanned days) with what the session verified and decided: the data (counts, yields, measurements) and the sources (DOI, URL) behind each decision, and the alternatives discarded and why. Consolidated decisions go in the canonical document; the journal keeps the evidence that motivates them. The section ends with `### Open as of <date>` (`### Aperto al <data>` in Italian projects; keep the label the journal already uses): every open node and pending task, one line each with its state (open, in progress; aperto, in corso), carried over from the previous entry, minus what closed, plus what opened. A node closes only when the decision is written in the canonical document and reflected in CLAUDE.md and README, and the entry says so.

If the session verified or decided nothing and no item changed state, there is no journal entry: say so. A project that still carries a TODO.md folds its items into the journal's open list, deletes the file and removes its mentions from CLAUDE.md and README.

## 3. The documents agree with the work

The next session reads a few documents first and trusts them, so they have to describe the project as it now is. The pass covers the files the session created or changed, the project's CLAUDE.md and README, the state document, the journal, and the documents CLAUDE.md names as authoritative (its key files or its table of which document owns what). Each is read against the current state, looking for a path or a file that no longer exists, a line describing a decision since changed, two documents that say different things about the same fact, and a document that only repeats another.

- Safe fixes are applied directly: dead references, stale lines, and contradictions where the session makes the current state clear.
- Renames, moves, merges, deletions, and contradictions where it is unclear which side is current go to the user as a short list, one line each with the reason, and wait for approval.

Dated frozen copies (in `archive/`), `data/raw/` and anything CLAUDE.md marks as historical are read, never edited. The review of a whole folder (naming, grouping, staleness across the tree) is the tidy pass of aldogor-project-setup, in Claude Code.

## 4. Commit, then ask to push

When the project is a git repository and the session can run commands, the updated documents and any other finished work of the session are committed before the prompt is written: message in the repository's language and style, nothing secret and no `.env` staged. Then say what is not yet on the remote and ask whether to push; the push waits for the answer. This is the one point where the push is always proposed. A repository whose CLAUDE.md sets its own rules (no remote, pull requests) follows those. Without a shell, this step does not apply.

## 5. The continuation prompt

Three to five lines:

1. What to read first, by name or path: the state document and, if needed, one or two authoritative files; in a project with a journal, its last "Open as of" (or "Aperto al") section and the canonical document.
2. Where the work stands, in one sentence.
3. The next task with its reason: "I'm working on [larger goal]. The next step is [task] because [what it enables]."

If the prompt needs more than five lines, the missing content belongs in the state documents.
