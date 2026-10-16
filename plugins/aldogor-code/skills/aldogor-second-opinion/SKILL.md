---
name: aldogor-second-opinion
description: >-
  Gets a second opinion from another model on a text, a design, a method, code or a deck, and sets it next to Claude's own view: Fable through the aldogor-second-opinion-fable agent by default, and GPT through the Codex CLI and Gemini through the Antigravity CLI, each signed in with the user's own subscription, when the user names them. Each reviewer returns a review or, for signed prose, an alternative draft in the text's register; Claude gives its own view before reading theirs and applies nothing until the user chooses. For GPT and Gemini it replaces the manual loop of a context file and a prompt pasted into another chat. Use when the user asks for a second opinion, another model's view or draft, or an external review ("aldogor-second-opinion", "secondo parere", "second opinion", "chiedi a Fable", "senti Fable", "what would Fable say", "chiedi a ChatGPT", "chiedi a GPT", "senti Gemini", "fallo rivedere a ChatGPT e Gemini", "consiglio esterno", "revisione esterna", "external review", "ask GPT", "ask Gemini", "counsel", "counselor"), or when Claude would otherwise prepare files and a prompt for the user to paste into another chat. GPT and Gemini receive copies of the files on OpenAI's and Google's servers, so they run only when the user names them, after the user approves the list of files.
argument-hint: "[gpt] [gemini] [all] [what to look at]"
---

# Aldogor-second-opinion

| Reviewer | Runs through | What leaves the machine | When |
|---|---|---|---|
| fable | the aldogor-second-opinion-fable agent, inside this session | nothing beyond this session's own provider | by default, and on Claude's initiative where the user's instructions call for it |
| gpt | Codex CLI (`codex exec`, read-only sandbox), on the user's ChatGPT plan | the packet, to OpenAI | when the user names it |
| gemini | Antigravity CLI (`agy -p`), on the user's Google AI plan | the packet, to Google | when the user names it |

A request that names no model goes to Fable by the quick path. A request that names GPT or Gemini, or asks for all of them, goes by the packet path, and Fable joins it when named or with "all". The words the user typed after the command name the reviewers and what to look at; without them, the subject is what the conversation is working on.

## The mode

**Review** for designs, plans, methods and protocols, code, analyses and decks, and any text the user wants critiqued. Each reviewer returns findings ranked by consequence, each tied to a place in the material, with the change it proposes.

**Alternative draft** for signed prose longer than a paragraph (a letter, an email, an abstract, a post, a note), in Italian or English, unless the user asks for a review. Each reviewer writes its own version from the idea the reader must take away, in the register of the genre, and states that idea in one line. A draft gives the user something to choose, which a list of corrections to Claude's text does not.

## Fable: the quick path

1. Claude's own view comes first, in the chat, in the shape of the mode: findings ranked by consequence, or Claude's own draft with its idea in one line. The user has it at once, and it cannot borrow from Fable's.
2. Launch the aldogor-second-opinion-fable agent with a brief that stands alone, since the agent sees none of the conversation: the question and the mode; the files that matter, by absolute path (the agent reads them itself and edits nothing, so no copies are needed); the options already weighed; the constraints and the user's stated preferences; for prose, the reader, the genre and its register profile in aldogor-style. Claude's own view stays out of the brief.
3. When the answer arrives, set it next to Claude's view as described under "What the user sees", and wait for the user's choice.

## GPT and Gemini: the packet path

The helper is `scripts/second_opinion.py` in this skill's folder; it holds no key, since each tool keeps its own sign-in.

### 1. Tools

Run `python scripts/second_opinion.py check --reviewers gpt,gemini` (only the external ones named). A tool that is missing or signed out is reported with its install line. Installing and signing in are the user's steps, once, in their own terminal: `codex login` (with a winget install on Windows, `codex-x86_64-pc-windows-msvc login`, a name the script also finds), and `agy`, which opens the browser. A tool installed while the desktop app was open is found by Claude's sessions after the app restarts. When one tool is unavailable, the user chooses whether to go ahead without it or with fable in its place.

### 2. The packet

`python scripts/second_opinion.py new <scratchpad> <slug>` creates the run folder in the session's scratchpad and prints its path. The run folder holds `packet/`, which is what the reviewers see and their working folder, and `out/`, which they never see. Into `packet/`:

- `files/`: copies of the material, never the project's files themselves, and only what the review needs (the text, and what it cites or depends on). The script sends GPT and Gemini the whole packet as one message, with the text of every file in it, because both tools block the commands they would use to read files when they run unattended; a Word, PowerPoint or PDF file therefore goes in as a Markdown extract, and an original that is not text stays out of the message and is reported as not sent. Personal data the review does not need (names of patients, colleagues, private addresses) is replaced in the copies by a role.
- `context.md`: who the material is for and what it must achieve; the genre and the register (for prose, the register profile of aldogor-style for the genre, and the user's rewrites of the same genre from `~/.claude/style-inbox.md` as examples of the user's voice); what is settled and not to be reopened; and the user's writing rules that bear on the material, copied in full, since the reviewers read none of Claude's instructions.
- `prompt.md`: the template of the mode from [references/prompts.md](references/prompts.md), filled in for this material and written in the language of the text.

### 3. The user approves

Before anything runs, show the user the reviewers, the mode and every file in `packet/` with its size, and say that GPT's and Gemini's copies go to OpenAI and Google under the data settings of the user's own accounts. One approval covers this packet; a packet that changes is approved again. A document of the user's health-authority role (institutional correspondence, internal reports, anything with patient or staff data) goes out only when the user has named it for outside review in this session.

### 4. Claude's own view

Before any reviewer runs, write `out/own-view.md`: in review mode, Claude's findings in the shape the prompt asks of the reviewers; in draft mode, Claude's own draft with its idea in one line. Written now, it cannot borrow from the others, and `out/` sits outside the packet, so no reviewer sees it.

### 5. The run

Start `python scripts/second_opinion.py run <run> --reviewers gpt,gemini` in the background, since a long text takes minutes per reviewer. The two run in parallel; each answer lands in `out/<reviewer>.md` with its log next to it, and `out/run.json` records each status, the files left out of the message, and any packet file that changed during the run (Antigravity may write inside its working folder). An answer that says the reviewer could not see the material counts as a failed run, whatever its status. `--model gemini=<slug>` picks another Gemini model (`agy models` lists them), `--effort gpt=<level>` another reasoning effort, and `--dry-run` prints the commands without running them.

When Fable joins, launch the aldogor-second-opinion-fable agent at the same time with a brief that points to `packet/` (prompt.md, context.md, files/) and not to `out/`, and save its answer as `out/fable.md`.

A reviewer that fails or times out is reported with its log, and the others go ahead.

## What the user sees

**Review.** One table of the points raised: the point, where in the material, who raised it (Claude, GPT, Gemini, Fable), and Claude's assessment of it (agree, or disagree with the reason). Points on which the reviewers contradict each other or Claude come first. A reviewer's claim of fact (a citation, a figure, a regulation) that the material does not confirm is marked as a fact to check. A packet file changed during the run is reported here.

**Alternative draft.** The drafts one after another, Claude's included, each headed by its reviewer and its idea in one line, then one line on what sets each apart.

On the packet path the answers stay in `out/` for the user to open. The user then chooses: which points to take, which draft, or a combination they describe. Only then does Claude change the project's files.

## Quota

Each packet run counts against the user's plans (Codex usage on ChatGPT, Antigravity requests on Google AI). One run per packet; a follow-up question goes to Claude in the session rather than to a new run, and a long deck can go out a section at a time.
