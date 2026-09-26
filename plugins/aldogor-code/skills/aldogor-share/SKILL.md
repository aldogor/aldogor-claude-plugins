---
name: aldogor-share
description: >-
  Prepares a project repository for collaborators and checks it before anyone is invited: what git ignores or does not track (what will not be shared), secrets, personal data and local paths in the tree and in the whole history, and the project layer collaborators need (AGENTS.md with the project's conventions, CLAUDE.md importing it, .claude/settings.json installing the shared plugins). Run by the user ("aldogor-share", "prepara il repo per la condivisione", "condividi il repo", "share this repo with collaborators").
disable-model-invocation: true
---

# Aldogor-share

The work runs in rounds with the user, one section at a time. Nothing is committed without the user's word, and inviting collaborators on GitHub stays the user's step.

## 1. What stays on this machine

List what git will not send: `git status --ignored --porcelain` for ignored paths and `git ls-files --others --exclude-standard` for untracked ones, grouped by folder with sizes. Add the local Claude files (`.claude/settings.local.json`, `CLAUDE.local.md`, and the auto-memory of this project under `~/.claude/projects/`). For each group, name the `.gitignore` line that keeps it out and what the group is (raw data, outputs, environments, credentials). The user confirms each group, or moves it into the repository or into `.gitignore`.

## 2. What the history holds

A clone carries every commit, so the check covers the whole history as well as the current tree:

- secrets: `gitleaks git --redact` when gitleaks is installed (`winget install Gitleaks.Gitleaks`), otherwise a search of every commit for keys, tokens, passwords and private keys, and every `.env` file ever added (`git log --all --diff-filter=A --name-only`);
- personal data: files under `data/` with identifiers, and email addresses, phone numbers or health data in documents;
- claude.ai chat exports ever committed;
- absolute local paths (`C:\Users\...`, `/Users/...`) in tracked files;
- large binaries.

For each finding the user chooses: accept it for these collaborators, remove it from the current tree only, rewrite the history before anyone clones (`git filter-repo`, which changes every commit id and needs a force push), or start a fresh repository from the current tree and keep this one private.

## 3. The project layer

Collaborators receive the repository's files and never the user's global instructions, so every convention the shared work depends on is written into the project. With the user, write or update:

- `AGENTS.md`, read by Claude Code (from v2.1.277, when no CLAUDE.md exists), Codex, Cursor and Copilot: what the project is and where authority lives; the journal convention (dated entries, the last "Open as of" as the state of the project); the citation format (inline author and year linked to the DOI); no dashes as punctuation; the data rules (`data/raw/` read-only, a value with no source is [n/d]); the language of documents and commits; the collaboration workflow (a branch per piece of work, pull requests, no direct commits to main, who merges).
- `CLAUDE.md`, whose first line is `@AGENTS.md` (an import, because a symlink breaks on Windows clones), followed by any Claude-specific lines.
- `.claude/settings.json`: `extraKnownMarketplaces` with the public marketplace `aldogor-claude-plugins` (GitHub source `aldogor/aldogor-claude-plugins`) and `enabledPlugins` for the plugins the project uses; collaborators install them by accepting the trust prompt.
- `.gitignore`: `.claude/settings.local.json`, `CLAUDE.local.md`, `.env` and the data that stays local.
- `README.md`: a short section on working in the repository with Claude (what the trust prompt installs, where the conventions live).

## 4. Close

Give the user a checklist: what is shared, what stays local, the history decisions, the files written. Commit on the user's word. Then the user invites the collaborators on GitHub; on a personal account's private repository, collaborators get write access.
