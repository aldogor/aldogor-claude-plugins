---
name: aldogor-share
description: >-
  Prepares a project repository for collaborators and checks it before anyone is invited: what git ignores or does not track (what will not be shared), secrets, personal data and local paths in the tree and in the whole history, and the project layer collaborators need (CLAUDE.md with the project's conventions, .claude/settings.json installing the shared plugins); publishes a repository's public version from its private one through an include-list. Use when the user asks to share a repository ("aldogor-share", "prepara il repo per la condivisione", "condividi il repo", "share this repo with collaborators"), before collaborators are invited, before a repository gets a public version, and when that version is published ("pubblica la versione pubblica", "publish the public repo").
---

# Aldogor-share

The work runs in rounds with the user, one section at a time. Nothing is committed without the user's word, and inviting collaborators on GitHub stays the user's step.

## 1. What stays on this machine

List what git will not send: `git status --ignored --porcelain` for ignored paths and `git ls-files --others --exclude-standard` for untracked ones, grouped by folder with sizes. Add the local Claude files (`.claude/settings.local.json`, `CLAUDE.local.md`, and the auto-memory of this project under `~/.claude/projects/`). For each group, name the `.gitignore` line that keeps it out and what the group is (raw data, outputs, environments, credentials). The user confirms each group, or moves it into the repository or into `.gitignore`.

## 2. What the history holds

A clone carries every commit, so the check covers the whole history as well as the current tree:

- secrets: `gitleaks git --redact` when gitleaks is installed (`winget install Gitleaks.Gitleaks` on Windows, `brew install gitleaks` on macOS, the release binary from its GitHub page on Linux), otherwise a search of every commit for keys, tokens, passwords and private keys, and every `.env` file ever added (`git log --all --diff-filter=A --name-only`);
- personal data: files under `data/` with identifiers, and email addresses, phone numbers or health data in documents;
- claude.ai chat exports ever committed;
- absolute local paths (`C:\Users\...`, `/Users/...`) in tracked files;
- large binaries.

For each finding the user chooses: accept it for these collaborators, remove it from the current tree only, rewrite the history before anyone clones (`git filter-repo`, which changes every commit id and needs a force push), or start a fresh repository from the current tree and keep this one private.

## 3. The project layer

Collaborators receive the repository's files and never the user's global instructions (`~/.claude`), so every convention the shared work depends on is written into the project. With the user, write or update:

- `CLAUDE.md`: what the project is and where authority lives; the journal convention (dated entries, and one open list at the end, edited in place, as the state of the project); the citation format (inline author and year linked to the DOI); no dashes as punctuation; the data rules (`data/raw/` read-only, a value with no source is [n/d]); the language of documents and commits; the git practice line set to shared (a branch per piece of work, merged through a pull request that the owner merges). CLAUDE.md travels with every copy of the repository, a public repository or a public cut included, so it holds conventions and pointers and never private context: names of people, study details and anything else not meant for publication stay in documents that remain internal.
- `.claude/settings.json`: the repository's whole Claude configuration, in one committed file: `extraKnownMarketplaces` with the public marketplace `aldogor-claude-plugins` (GitHub source `aldogor/aldogor-claude-plugins`) and `enabledPlugins` for every plugin the project uses, the development ones included; collaborators install them by accepting the trust prompt. No second, personal layer sits next to it. A `.gitignore` that excludes `.claude/` gets `!.claude/settings.json`.
- `.gitignore`: `.claude/settings.local.json`, `CLAUDE.local.md`, `.env` and the data that stays local.
- `README.md`: a short section on working in the repository with Claude: install git and the GitHub CLI and sign in (`gh auth login`), accept the trust prompt, which installs the plugins, and find the conventions in CLAUDE.md. Each person's Claude then creates the branch and opens the pull request, and the owner merges it; GitHub Free does not enforce reviews on a private repository, so the rule rests on CLAUDE.md.

## 4. Publishing a public version

A repository with a public version is two repositories, as aldogor-project-setup sets them up: `<name>-internal` holds the work and its history, and `<name>` receives only what `publish.txt`, at the private root, lists. `scripts/publish.py` in this skill's folder builds the public tree from the last commit, holds back the files that never go public (the list itself, JOURNAL.md, CLAUDE.local.md, `.env` files, personal settings, chat exports, raw data, literature texts), stops on a stale rule or a credential, writes into the sibling clone of the public repository and commits there; `--check` shows what would go and writes nothing.

With the user, write `publish.txt`: `target:` the sibling clone, `check:` and `validate:` commands where the project has them, then one line per published folder or file, explicit paths before broad globs. A repository published another way (an exclude-list, a public branch or remote in the working clone) moves to this one: the paths it published become the include-list, its publishing tools stay private, and the public repository's next commit drops them. Pushing the public clone stays the user's step.

## 5. Close

Give the user a checklist: what is shared, what stays local, the history decisions, the files written. Commit on the user's word. Then the user invites the collaborators on GitHub; on a personal account's private repository, collaborators get write access.
