---
name: aldogor-grill
description: >-
  Resolves open decisions by structured questions, each with a recommended answer: interviewing the user in rounds until a plan, protocol or design holds ("grill me", "grigliami", "aldogor-grill", "stress-test this", "challenge this design"), or turning what the user cannot answer alone into a questionnaire for a named recipient such as IT, the DPO, administration or a collaborator ("aldogor-questionnaire", "prepara le domande per", "turn this into a questionnaire", an email that is mostly questions).
---

# Aldogor-grill

Two modes, one mechanism: questions numbered, one decision each, with a recommended answer. Grill the user when the decisions are theirs; write a questionnaire when the answers sit with someone else. Run either in the language of the conversation.

## Grilling the user

Interview the user until shared understanding is reached. The subject can be anything with open decisions: a study design, a protocol, a project note, an institutional document, a teaching plan, a technical or architectural choice.

**The design tree.** Map the plan as a design tree: every decision branches into the decisions that hang off it. Work the tree in rounds. The frontier is every decision whose prerequisites are already settled, the questions that can be asked now without guessing at answers not yet heard. Ask the whole frontier in one round, then wait for the user's answers before the next round. Number questions continuously across the session so answers can reference them. Each question:

**Q1. Question title.** Question body, one decision only, with the realistic options where they exist.
*Recommendation:* the answer you would give, in one or two lines.

A question whose answer depends on another question still open in this round belongs to a later round, not this one. Each answered round reshapes the tree: settled decisions push the frontier outward and unblock what depended on them. Recompute the frontier and ask the next round.

**Facts are yours, decisions are the user's.** Never ask the user for a fact you can find yourself. Environment facts (files, data, configurations) go to a subagent or a direct lookup; domain facts (which validated instruments exist, what a guideline requires, what a norm says) go through your own research, using aldogor-research when the answer must rest on verified sources. A running lookup is an unsettled prerequisite: only the questions downstream of it wait, the rest of the frontier goes out now. Decisions (trade-offs, priorities, appetite for risk, institutional constraints only the user knows) are put to the user, one per question, and you wait.

**Closure.** The session is done when the frontier is empty: every branch visited, nothing left silently assumed. Confirm with the user that shared understanding is reached before acting on it. The rounds themselves write nothing; the conversation carries the tree. At closure, record the resolved decisions in the document that owns them: update the plan or protocol that was grilled, or the project's state document, following its conventions. In a project with `JOURNAL.md`, the reasoning behind each decision and the alternatives discarded go in the journal under today's date, and the nodes change state in its open list (`## Open`, at the end). If no such document exists, offer to create the smallest one that fits. The outcome never lives only in the chat.

## Questionnaire for a recipient

Turn something the user cannot answer alone into a questionnaire: a document one person fills in async, or that structures a meeting. The recipient holds knowledge the user lacks; the questionnaire pulls it out. The questions target the gap between what the recipient knows and what the user needs.

**Interview the send, not the subject.** The user cannot answer the subject, but can always answer the send. Two exchanges, skipping whatever the conversation has already established: who is it going to (role, expertise, relationship to the user, language; this fixes the tone, the output language and how much context the document must carry; Italian is the default for institutional recipients), and what do you need back (the specific decisions or facts the user cannot resolve alone, done when there is a concrete list of what the user must walk away able to decide, plus the deadline and how the answers will be used).

**Vehicle.** An email when the recipient is one person reached by mail (the usual case for IT, DPO, amministrazione, collaborators); the formal register of aldogor-style applies. A standalone Markdown file when the questionnaire accompanies a project or more than one person will answer; save it in the project's documentation folder with the project's naming conventions and report the path.

**Structure.** Frame it as discovery: the user lacks context the recipient holds. Order questions most-important-first, async means one pass may be all you get, and group them under headings by theme once there are more than a handful. If one early answer could settle everything (an approved tool already exists, the authorization is impossible), put that question first and mark the rest as conditional on it. Elements, carried lighter in an email than in a document: the purpose (why this exists and the decision riding on it, with how the answers will be used); one paragraph of context orienting a recipient who was not in the user's head; how to answer (deadline, rough effort, partial answers and "I don't know" welcome, uncertainty flagged rather than skipped); the questions, one idea each, never compound, with an answer stub under each in a document and a one-line "why this matters" only where a question could be misread; a closing catch-all (anything not asked that the user should know?). Every item named in the what-you-need-back list must be covered by a question before the questionnaire goes out.
