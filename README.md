# aldogor-claude-plugins

Claude plugins by Aldo Gorga, a public health researcher working on digital health and AI. They carry a way of working: sources verified before they are cited, documents reviewed for structure before prose, projects that keep a dated journal, and sessions that close with the project in order. Most of the writing guidance is for Italian and English scientific and institutional prose.

## Plugins

**aldogor-core**, for Claude Code and claude.ai:

- `aldogor-research`: literature grounding, source selection and citation verification (PubMed, Consensus, OpenAlex, Crossref), with a verdict for every reference.
- `aldogor-style`: a two-pass review, structure then prose, with voice profiles by genre (scientific prose, email, messages, slides) and a check against the reporting guideline of the study design.
- `aldogor-handoff`: closes a working session, brings the journal and the project's documents up to date and writes a continuation prompt.
- `aldogor-grill`: resolves open decisions by rounds of questions with a recommended answer, or turns them into a questionnaire for someone else.

**aldogor-code**, for Claude Code only:

- `aldogor-project-setup`: scaffolds a project (research or development) and keeps an existing one in order.
- `aldogor-share`: run by hand (`/aldogor-code:aldogor-share`) before inviting collaborators; checks what git will not send, what the history holds, and writes the project conventions into `AGENTS.md`.
- `aldogor-counsel`: an agent on Fable that the main session consults for a second perspective on decisions, plans, visual ideas and drafts.

## Install

In Claude Code:

```
/plugin marketplace add aldogor/aldogor-claude-plugins
/plugin install aldogor-core@aldogor-claude-plugins
/plugin install aldogor-code@aldogor-claude-plugins
```

On claude.ai: Customize, Plugins, add the marketplace `aldogor/aldogor-claude-plugins`, then install aldogor-core.

In a shared project, `.claude/settings.json` can declare the marketplace and the plugins, so that each collaborator gets them after accepting the trust prompt:

```json
{
  "extraKnownMarketplaces": {
    "aldogor-claude-plugins": {
      "source": { "source": "github", "repo": "aldogor/aldogor-claude-plugins" }
    }
  },
  "enabledPlugins": {
    "aldogor-core@aldogor-claude-plugins": true
  }
}
```

## Conventions the skills assume

A project keeps a `JOURNAL.md` of dated entries whose last "Open as of" list is the state of the work; citations are inline (author and year) and link to the DOI; dashes are never used as punctuation; a value with no source is written [n/d]. The skills work without these conventions, but they are written around them.

## Provenance and licence

MIT licence. The skills are maintained in the author's private configuration repository and published here. Ideas adapted from other packages are listed, with source, commit and licence, in [UPSTREAM.md](UPSTREAM.md).
