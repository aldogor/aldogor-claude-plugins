# Upstream provenance

One entry per external source that anything in this repo was distilled or adapted from.
Record source, commit hash, and license **before** committing the derived content. Clones for review go in upstream/clones/ (gitignored); the review itself is step 5 of the aldogor-setup-loop skill.

Entry template:

```markdown
## <skill or file name>
- Distilled from: <owner>/<repo> @ <commit>
- Date reviewed: YYYY-MM-DD
- What was taken:
- What was deliberately dropped:
- License notes:
```

Referenced-not-vendored packages (installed from their own marketplace, nothing copied here)
do not need an entry: Superpowers, skill-creator.

## Entries

## aldogor-grill (grilling and questionnaire modes; the questionnaire skill merged into it 2026-09-14)
- Distilled from: mattpocock/skills @ 8b78b531ab965735c5dc74f6f7a219e1e37326df
- Date reviewed: 2026-08-13; re-reviewed 2026-09-14 at 3cca18b368ae95cdbdebbff572ccafa662551015 (34 commits: em-dash removal, horizontal rules between grill questions, the invocation invariant now in CLAUDE.md conventions; no backport to the skills)
- What was taken (workflow shapes re-authored in our own words, no verbatim text):
  - For aldogor-grill (from its `grilling` primitive and `grill-me` wrapper, merged into one skill): the design-tree model of a decision session; rounds over the frontier of currently-answerable questions; numbered questions each carrying a recommended answer; facts looked up by the agent (subagent dispatch for environment facts) while decisions go to the user; completion defined as an empty frontier plus explicit user confirmation before acting.
  - For aldogor-questionnaire (from its `to-questionnaire`): the grill-the-send-not-the-subject principle (interview the user only about recipient and needed outcomes); questions aimed at the recipient/user knowledge gap; the document shape (purpose, context paragraph, how-to-answer with deadline and partial-answers-welcome, one idea per question with an answer stub, "why this matters" lines only where a question could be misread, closing catch-all); most-important-first ordering for async sends.
- What was deliberately dropped: the emoji question format (❓/➡️) in grilling; the software-only framing (both skills generalized to research protocols, institutional documents, teaching and personal projects); to-questionnaire's fixed English-only template (replaced with recipient-language selection, Italian default for institutional recipients); the downstream to-spec/to-tickets capture pipeline (replaced with an end-of-session offer to record resolved decisions in the document that owns them); the rest of the package (tdd, code-review, diagnosing-bugs, handoff, research, domain-modeling and others) as overlapping superpowers, built-ins, or existing aldogor skills.
- License notes: MIT (adaptation permitted with attribution; attribution kept here).

## aldogor-research
- Distilled from: Imbad0202/academic-research-skills @ 01cb1d5a998c99b1eb8499b5a5449b9804f89bfa; K-Dense-AI/scientific-agent-skills (formerly K-Dense-AI/claude-scientific-skills, same history; the old URL redirects) @ d767725c6e93b1d02a220e6be75b261a9833ede5; kthorn/research-superpower @ 2affbfea08b584465207680b906e208de52c4669; franklee16/academic-research-skills @ 2b711a6cdcb12b3a353619954bed2af9271c6aa1
- Date reviewed: 2026-08-05; re-reviewed 2026-09-14: ARS at b06ceafb6c6b2c83455301e14c0751094478a8cd (retraction check corrected to Crossref `updated-by` plus OpenAlex `is_retracted`, from its #651; "hedging is not a downgrade" from its #825), K-Dense at 330c8e764435a731eff571e3efdda70b363d0792 (only change to the fed skills is a citation footer asking that Kassis et al. 2026, arXiv:2609.00065, be cited when a skill contributes to a manuscript: recorded here as the package's own citation, no obligation for shapes taken under MIT), research-superpower unchanged, franklee16 unchanged since 2026-04-26 (dormant); K-Dense re-reviewed 2026-09-26 at 49c6e97775eaa18ba791bebe23162a70ae601c18 (one commit since 330c8e76, a regenerated security-scan report; no skill changed, no backport)
- What was taken (workflow shapes re-authored in our own words, no verbatim text):
  - From ARS: three-class citation verdict with asymmetric evidence rules (ID-keyed miss = fabrication evidence, title-only miss = coverage gap); DOI-first resolution with title cross-check; claim verdict taxonomy separating distortion from inaccessibility (paywall never blocks); risk-stratified sampling with recorded tiers; the silent-upgrade audit axes; the deictic time-reference sweep.
  - From K-Dense (MIT): the "APIs fail with HTTP 200" failure catalog; intent-to-database routing; identifier-conversion traps; untrusted-API-response and credential-in-URL rules; "never present metadata as full text"; "search snippets are discovery aids, not verified support"; OpenAlex integration approach.
  - From research-superpower (MIT): test-driven screening rubric with hand-labelled ground-truth set and cached re-screening; parallel batch screening with shared-rate-limit arithmetic and main-agent write ownership; mandatory Unpaywall fallback with real-email rule; always-hyperlinked identifiers; retrofitted methodology/reproducibility block.
  - From franklee16 (its MIT-licensed fact-checker skill): UNVERIFIABLE as a first-class verdict.
- What was deliberately dropped: ARS's 39-agent ensemble, 10-stage pipeline, reviewer panel (its "pressure is not evidence" clause is earmarked for home/rules/ instead), Material Passport machinery and the one-file evidence ledger derived from it (removed 2026-09-22, never used in any project), contract-paraphrase blocks (Fable reasoning-echo risk), self-preflight loops (Opus over-verification), firm-rule ID namespaces, byte-locks; K-Dense's vendor-upsell footers and mandatory AI-figure rule; all keyed third-party wrappers (Paperclip, Parallel, Exa); research-superpower's ChEMBL skill and emoji progress reporting; franklee16's web-search deep-research family and its unlicensed skills (ideas from those reimplemented conceptually only: the Crossref confidence-table output shape).
- License notes: ARS is CC-BY-NC-4.0 (shapes only, nothing verbatim; attribution kept here; personal noncommercial use). K-Dense and research-superpower are MIT (adaptation permitted with attribution). franklee16 has no repo license; only its MIT-marked skills were used as sources of ideas.

## aldogor-style, prose pass
- Distilled from: cursor/plugins @ e8d856f0273b42ebafe0ec3546bd645709e7c1b0 (pstack/skills/unslop/SKILL.md, file dated 2026-09-07); the skill's first form was a fork of the humanize skill built on Wikipedia's "Signs of AI writing".
- Date reviewed: 2026-09-14
- What survives (ideas re-authored in Italian, no verbatim text): the sentence that says the thing instead of how it sounds, and words chosen plainly, folded into the third and fifth of the five points of the prose pass. The Wikipedia-derived catalogue of AI tells was removed from the skill on 2026-09-22.
- What was deliberately dropped: the tell catalogue as a whole, its ban on parentheses as dash replacements, its mandatory always-on activation.
- License notes: pstack/LICENSE is MIT (copyright 2026 Lauren Tan) and covers the unslop skill; the repository root carries no licence. Attribution kept here.

## aldogor-style, structural pass (figures and reporting guidelines)
- Distilled from: cathrynlavery/diagram-design @ dc1ace47b99a419e42d01a03cb6ace5346efa8ae (v2.6.33); K-Dense-AI/scientific-agent-skills @ 49c6e97775eaa18ba791bebe23162a70ae601c18 (skills/scientific-writing, skills/scientific-visualization)
- Date reviewed: 2026-09-26 (report in audit/repo-review-2026-09.md)
- What was taken (ideas re-authored in Italian, no verbatim text): from diagram-design, the figure test (a figure earns its place only where a table or a paragraph would not do; remove any element the reader does not use; above about ten elements, split into an overview and a detail); from scientific-writing, the check of a paper or protocol against the reporting guideline of its design, AI extensions included, read on EQUATOR, with adherence never claimed from a partial check (PRISMA-ScR and DECIDE-AI added on our side; STARD-AI and TRIPOD-LLM checked on EQUATOR and Nature Medicine on 2026-09-26); from scientific-visualization, the figure-integrity checks (uncertainty named with n, bars from zero, colour never the only cue, the figure viewed at print size).
- What was deliberately dropped: diagram-design's drawing system (41 visual types, design tokens, connector rules, templates, animation, brand profiles, draw.io, Mermaid and Excalidraw import, SVG and PNG export, six slash commands); K-Dense's evidence-ID manifests, validators and intake gates, its Python toolchains and publisher profiles, its AI-image figure and slide generation, and the citation footer asking that its paper be cited.
- License notes: diagram-design is MIT (copyright 2025 Cathryn Lavery). scientific-agent-skills is MIT at repository level (copyright 2025 K-Dense Inc.) and both skills used declare MIT. Adaptation permitted with attribution; attribution kept here.

## aldogor-research (retraction, quotations, independence)
- Distilled from: jordan-gibbs/hyperresearch @ 75b1ecfb2891184fad2cc1a2ddf9abe476f5b54c (v0.11.1, 2026-09-12)
- Date reviewed: 2026-09-14
- What was taken (rules only): retraction and corrections re-read at delivery time; quotations located verbatim or marked contradicted; evidence weighed by independent studies, not papers. The chimeric-citation line (right title, wrong authors) comes from PHY041/claude-skill-citation-checker (no licence, idea only).
- What was deliberately dropped: the 16-step pipeline, the 16-agent roster, the source vault, Crawl4AI, the cite-check tooling; a sandbox test was judged not worth its cost (web-first, no PubMed, hours of Opus subagents per run).
- License notes: MIT (adaptation permitted with attribution; attribution kept here).

## Superpowers (reference package, tuning record)
- Package: superpowers@claude-plugins-official 6.3.0 since 2026-09-14 (obra/superpowers; 6.2.0 from 2026-08-05), installed from the official marketplace, never vendored.
- Date reviewed: 2026-08-05 (full 14-skill analysis in the session record; upstream v6.2.0 notes describe an ongoing "compression campaign" reducing prescriptiveness).
- Tuning applied on our side only: never enabled at user scope; enabled per project in this repo and in the development projects (installed by aldogor-project-setup), so research projects load none of it. The `false` entries left in the settings of older research repos are inert. Counter-pressure for its verification-heavy skills lands in the "How to work" section of home/CLAUDE.md. skillOverrides cannot target plugin skills (documented limitation), so no per-skill downgrades exist to break on upstream updates.
- Re-check at the quarterly backport review: which projects still use it, from the invocation counts in the transcripts.
