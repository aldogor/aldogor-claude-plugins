---
name: aldogor-handoff
description: >-
  Guides the user through the close of a working session and leaves the project in order: closes the threads the session left open and asks what the next session should put first, brings the state document and the project's JOURNAL.md up to date, reviews the documents a later session reads first so that they agree with the work as it is, settles git (leftovers, commit, branch or worktree, sync with the remote, the push question), and ends with a minimal continuation prompt. Use when the user says "aldogor-handoff", "handoff", "prompt per la prossima chat", "prepara il passaggio", "chiudi la sessione", "gimme next prompt", or is ending a long session that continues elsewhere.
---

# Aldogor-handoff

The close is a short sequence that the user walks through with you, in this order. Each step reports in a line or two what it did, gathers the questions it needs the user to answer, asks them together, and ends before the next begins. The continuation prompt comes last, once everything else is settled: the prompt is not the store, the documents are.

## 1. Open threads and the next priority

Before anything is written, list what the session leaves open: questions put to the user and never answered, decisions still pending, work started and not finished, things promised in the chat ("I'll check X"), and background tasks or agents still running. Each thread closes now if it can (answer it, finish it, or stop a task that is no longer needed); one that cannot close in this session becomes an open item for the journal, with what unblocks it. Running background work is waited for or stopped on the user's word, never left behind in silence.

In the same round, ask the user what the next session should put first, with your recommendation drawn from the open items. The answer orders the journal's open list and becomes the prompt's next task.

## 2. The canonical state

Find where this work's state lives and bring it current:

- In a project with a state document (a context file, a "Current state" section): update it there, in final-state prose, with no session narrative.
- In a chat project: update, or produce for re-upload, the context file the project already uses.
- If no state document exists yet, create the smallest one that fits the project's conventions and say where it now lives.

What goes in: decisions taken, current status, open items with what unblocks them. What stays out: the conversation's history, preferences and standing rules, anything the documents already say, lists of files touched (git is the changelog).

## 3. The journal, when the project has one

If `JOURNAL.md` exists in the project root, it gets one section headed by today's ISO date (`## 2026-08-18`, or a range if the work spanned days) with what the session verified and decided: the data (counts, yields, measurements) and the sources (DOI, URL) behind each decision, and the alternatives discarded and why. Consolidated decisions go in the canonical document; the journal keeps the evidence that motivates them. The section ends with `### Open as of <date>` (`### Aperto al <data>` in Italian projects; keep the label the journal already uses): every open node and pending task, one line each with its state (open, in progress; aperto, in corso), carried over from the previous entry, minus what closed, plus the threads of step 1 that stayed open, with the user's priority first. A node closes only when the decision is written in the canonical document and reflected in CLAUDE.md and README, and the entry says so.

If the session verified or decided nothing and no item changed state, there is no journal entry: say so. A project that still carries a TODO.md folds its items into the journal's open list, deletes the file and removes its mentions from CLAUDE.md and README.

## 4. The documents agree with the work

The next session reads a few documents first and trusts them, so they have to describe the project as it now is. The pass covers the files the session created or changed, the project's CLAUDE.md and README, the state document, the journal, and the documents CLAUDE.md names as authoritative (its key files or its table of which document owns what). Each is read against the current state, looking for a path or a file that no longer exists, a line describing a decision since changed, two documents that say different things about the same fact, and a document that only repeats another.

- Safe fixes are applied directly: dead references, stale lines, and contradictions where the session makes the current state clear.
- Renames, moves, merges, deletions, and contradictions where it is unclear which side is current go to the user as a short list, one line each with the reason, and wait for approval.

Dated frozen copies (in `archive/`), `data/raw/` and anything CLAUDE.md marks as historical are read, never edited. The review of a whole folder (naming, grouping, staleness across the tree) is the tidy pass of aldogor-project-setup, in Claude Code.

## 5. Git

When the project is a git repository and the session can run commands, settle it in this order. A repository whose CLAUDE.md or AGENTS.md sets its own rules (no remote, pull requests, who merges) follows them. Without a shell, this step does not apply.

1. **Leftovers.** From `git status` and `git stash list`, list what is changed, untracked or stashed but is not the session's finished work, each with what it is. The user decides for each: commit it, keep it for later, or discard it; discarding waits for an explicit word, because it cannot be undone.
2. **Commit** the session's finished work, the updated documents included: message in the repository's language and style, nothing secret and no `.env` staged.
3. **Branch or worktree.** If the session worked outside the main branch, propose how the work lands: merged into the main branch, pushed with a pull request, or kept as it is for later. After a merge, offer to delete the branch or the worktree. In a worktree that the desktop app manages, its own sync with the base branch comes before any manual merge.
4. **Sync.** Fetch. If the remote has commits the local branch lacks, integrate them before pushing (a rebase in a repository only the user commits to, a merge or a pull request where the repository's rules say so) and report any conflict to the user instead of resolving it by guesswork.
5. **Push.** Say what is not yet on the remote and ask whether to push; the push waits for the answer. This is the one point where the push is always proposed.

## 6. The continuation prompt

Three to five lines, written once the steps above are done:

1. What to read first, by name or path: the state document and, if needed, one or two authoritative files; in a project with a journal, its last "Open as of" (or "Aperto al") section and the canonical document.
2. Where the work stands, in one sentence.
3. The next task with its reason, taken from the priority the user gave in step 1: "I'm working on [larger goal]. The next step is [task] because [what it enables]."

If the prompt needs more than five lines, the missing content belongs in the state documents.
