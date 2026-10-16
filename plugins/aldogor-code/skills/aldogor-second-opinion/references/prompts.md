# Prompt templates

Each template becomes the packet's `prompt.md`, filled in for the material and written in the language of the text (an Italian letter gets an Italian prompt). Square brackets mark what to fill in; a line that does not apply is dropped. The same `prompt.md` serves every reviewer, Fable included, so that the answers can be compared.

## Review

```
# Review

You are reviewing [what: a research protocol, a 25-slide deck, a Python analysis, an institutional letter] for [whom: a public health researcher, writing for ...]. Read context.md first: it says who the material is for, what it must achieve, and what is already settled. The material is in the files folder.

Review it as a senior [field] reviewer would, and rank what you find by consequence:

1. The strongest objection: what would most likely make this fail with its reader, and why.
2. What holds and should stay as it is.
3. Each further problem: where it is (file, and section, slide or line), what is wrong, what to change, and why.
4. What you could not judge from the material, and what would let you judge it.

Locate each point with a few words of the text rather than long quotations, and propose the change instead of only naming the problem. Do not rewrite the whole material, and do not reopen what context.md lists as settled. [Focus the user asked for, if any.]

Answer in [language], in plain prose and short lists. Give your whole answer as your reply; do not create or edit any file.
```

## Alternative draft

```
# Alternative draft

Read context.md first: it says who the reader is, what the text must achieve, its register, and the writing rules to follow. The source text is in the files folder.

Write your own version of [what: the letter to the scientific societies, the abstract, the email to the supervisor] in [language].

- Start from the one idea the reader must take away, and build the text around it. Do not correct the source line by line: this is a second draft, not an edit.
- Keep every fact, figure, name, date and commitment of the source, and add none.
- Follow the register and the writing rules in context.md.
- Keep to about [n] words, as the source does.

Reply with three parts: one line stating the idea your draft is built on; the draft; at most three lines on how it differs from the source. Give everything as your reply; do not create or edit any file.
```
