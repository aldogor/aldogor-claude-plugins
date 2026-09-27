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

If `JOURNAL.md` exists in the project root, it gets one section headed by today's ISO date (`## 2026-08-18`, or a range if the work spanned days), placed above the open list that ends the file, with what the session verified and decided: the data (counts, yields, measurements) and the sources (DOI, URL) behind each decision, and the alternatives discarded and why. Consolidated decisions go in the canonical document; the journal keeps the evidence that motivates them. The section's last line names what the session opened and what it closed (`Opened: ...; closed: ...`, in Italian `Aperti: ...; chiusi: ...`).

The open list, `## Open` (`## Aperto` in Italian projects), is the journal's last section and is edited in place: every open node and pending task, one line each with its state (open, in progress, or waits on what unblocks it; aperto, in corso, in attesa di), with what closed removed, the threads of step 1 that stayed open added, and the user's priority first. A node closes only when the decision is written in the canonical document and reflected in CLAUDE.md and README. A journal that still ends each entry with its own `### Open as of <date>` (`### Aperto al <data>`) converts first, in a commit of its own: the latest of those lists becomes the open list at the end, and the older ones are removed, since git keeps them.

If the session verified or decided nothing and no item changed state, there is no journal entry: say so. A project that still carries a TODO.md folds its items into the journal's open list, deletes the file and removes its mentions from CLAUDE.md and README.

## 4. The documents agree with the work

The next session reads a few documents first and trusts them, so they have to describe the project as it now is. The pass covers the files the session created or changed, the project's CLAUDE.md and README, the state document, the journal, and the documents CLAUDE.md names as authoritative (its key files or its table of which document owns what). Each is read against the current state, looking for a path or a file that no longer exists, a line describing a decision since changed, two documents that say different things about the same fact, and a document that only repeats another.

The project also has to follow the conventions of the setup, which change over time. In Claude Code, `python <this skill's folder>/scripts/check_project.py`, run in the project, lists what the project breaks among them: the git practice named in CLAUDE.md, the journal's single open list and each entry's closing line, TODO or CHANGELOG files, `.env`, the literature folder, the placement of chat exports, and the git state that step 5 settles. It changes nothing; its findings join the ones below.

- Safe fixes are applied directly: dead references, stale lines, contradictions where the session makes the current state clear, and small convention fixes (a missing closing line in the journal, a `.gitignore` line, the practice line in CLAUDE.md).
- Renames, moves, merges, deletions, contradictions where it is unclear which side is current, and conversions that reshape the project (a literature folder or a journal to convert) go to the user as a short list, one line each with the reason, and wait for approval; what the user defers becomes an item of the open list.

Dated frozen copies (in `archive/`), `data/raw/` and anything CLAUDE.md marks as historical are read, never edited. The review of a whole folder (naming, grouping, staleness across the tree) is the tidy pass of aldogor-project-setup, in Claude Code.

## 5. Git

When the project is a git repository and the session can run commands, settle it in this order. The repository's CLAUDE.md names its git practice, and the steps apply it:

- research: all work on the main branch;
- development: each feature or fix on its own branch, merged into the main branch when its tests pass and then deleted;
- shared: as development, with every branch reaching the main branch through a pull request that the owner merges.

Other rules the repository sets (no remote, who merges) hold too. Where no practice is named, propose the one that fits the project and write it into CLAUDE.md on the user's word. Without a shell, this step does not apply.

1. **Leftovers.** From `git status`, `git stash list` and `git branch --merged`, list what is changed, untracked or stashed but is not the session's finished work, and the local branches already merged but not deleted, each with what it is. The user decides for each: commit it, keep it for later, or discard it; discarding waits for an explicit word, because it cannot be undone.
2. **Commit** the session's finished work, the updated documents included: message in the repository's language and style, nothing secret and no `.env` staged.
3. **Branch or worktree.** If the session worked outside the main branch, the work lands as the practice says: merged once its tests pass, or through a pull request; work not ready stays on its branch, and the open list says so. After a merge, delete the branch with `git branch -d` (it refuses an unmerged one) and the worktree, and offer to delete the remote branch. In a worktree that the desktop app manages, its own sync with the base branch comes before any manual merge.
4. **Sync.** Fetch. If the remote has commits the local branch lacks, integrate them before pushing (a rebase in a repository only the user commits to, a merge or a pull request where the repository's rules say so) and report any conflict to the user instead of resolving it by guesswork.
5. **Push.** Say what is not yet on the remote and ask whether to push; the push waits for the answer. This is the one point where the push is always proposed.

## 6. The continuation prompt

Three to five lines, written once the steps above are done:

1. What to read first, by name or path: the state document and, if needed, one or two authoritative files; in a project with a journal, its open list (`## Open` or `## Aperto`, at the end) and the canonical document.
2. Where the work stands, in one sentence.
3. The next task with its reason, taken from the priority the user gave in step 1: "I'm working on [larger goal]. The next step is [task] because [what it enables]." Then the rest of the journal's open list, which the next session works through until each item is closed or waits on something outside it.

If the prompt needs more than five lines, the missing content belongs in the state documents.
