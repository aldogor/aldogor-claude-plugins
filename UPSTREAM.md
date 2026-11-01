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
- Date reviewed: 2026-08-13; re-reviewed 2026-09-14 at 3cca18b368ae95cdbdebbff572ccafa662551015 (34 commits: em-dash removal, horizontal rules between grill questions, the invocation invariant now in CLAUDE.md conventions; no backport to the skills); re-reviewed 2026-10-09 at 49dd158d1076134a641b33efb035946536778336 (release 1.3.1: questions worded so that a plain yes accepts the recommendation, from its #706, taken; its case against a native question tool, .out-of-scope/native-question-tool.md, met by keeping open questions as text)
- Also drawn on, 2026-10-09, for the question dialog: RobMitt/grill-me-skill @ 31d61d68fc406f8cc2a944b4b10e6f23877720f1 (no licence, idea only: grilling through the client's question tool) and andrewroxby/claude-style-patch @ 9073af0533c2f97be4ff83b53fe9a21af3a4feeb (CC0: options explained where the decision is asked).
- What was taken (workflow shapes re-authored in our own words, no verbatim text):
  - For aldogor-grill (from its `grilling` primitive and `grill-me` wrapper, merged into one skill): the design-tree model of a decision session; rounds over the frontier of currently-answerable questions; numbered questions each carrying a recommended answer; facts looked up by the agent (subagent dispatch for environment facts) while decisions go to the user; completion defined as an empty frontier plus explicit user confirmation before acting.
  - For aldogor-questionnaire (from its `to-questionnaire`): the grill-the-send-not-the-subject principle (interview the user only about recipient and needed outcomes); questions aimed at the recipient/user knowledge gap; the document shape (purpose, context paragraph, how-to-answer with deadline and partial-answers-welcome, one idea per question with an answer stub, "why this matters" lines only where a question could be misread, closing catch-all); most-important-first ordering for async sends.
- What was deliberately dropped: the emoji question format (❓/➡️) in grilling; the software-only framing (both skills generalized to research protocols, institutional documents, teaching and personal projects); to-questionnaire's fixed English-only template (replaced with recipient-language selection, Italian default for institutional recipients); the downstream to-spec/to-tickets capture pipeline (replaced with an end-of-session offer to record resolved decisions in the document that owns them); the rest of the package (tdd, code-review, diagnosing-bugs, handoff, research, domain-modeling and others) as overlapping superpowers, built-ins, or existing aldogor skills.
- License notes: MIT (adaptation permitted with attribution; attribution kept here).

## aldogor-research
- Distilled from: Imbad0202/academic-research-skills @ 01cb1d5a998c99b1eb8499b5a5449b9804f89bfa; K-Dense-AI/scientific-agent-skills (formerly K-Dense-AI/claude-scientific-skills, same history; the old URL redirects) @ d767725c6e93b1d02a220e6be75b261a9833ede5; kthorn/research-superpower @ 2affbfea08b584465207680b906e208de52c4669; franklee16/academic-research-skills @ 2b711a6cdcb12b3a353619954bed2af9271c6aa1
- Date reviewed: 2026-08-05; re-reviewed 2026-09-14: ARS at b06ceafb6c6b2c83455301e14c0751094478a8cd (retraction check corrected to Crossref `updated-by` plus OpenAlex `is_retracted`, from its #651; "hedging is not a downgrade" from its #825), K-Dense at 330c8e764435a731eff571e3efdda70b363d0792 (only change to the fed skills is a citation footer asking that Kassis et al. 2026, arXiv:2609.00065, be cited when a skill contributes to a manuscript: recorded here as the package's own citation, no obligation for shapes taken under MIT), research-superpower unchanged, franklee16 unchanged since 2026-04-26 (dormant); K-Dense re-reviewed 2026-09-26 at 49c6e97775eaa18ba791bebe23162a70ae601c18 (one commit since 330c8e76, a regenerated security-scan report; no skill changed, no backport); re-reviewed 2026-10-09 (report in audit/backport-review-2026-10.md): ARS at e614b322297ba5b072a106942177e218cbe2d48f (from its sr-screener, #919: seed studies, no missed include in the hand labels, one ordered exclusion code, failed calls left pending; limitations named by design choice and condition, #916; a contradicted citation kept out of later drafts, #936), K-Dense at 92ace75ac21efe19a620434e0ca4e356081fe807 (OpenAlex's API keys in place of the polite pool; DOIs registered with DataCite or mEDRA, absence from Crossref never fabrication evidence), research-superpower unchanged and dormant since 2025-10-22, franklee16 at 9a4b2db21fc4b217136ae4a0e6faad42d179ca03 (reorganised into workflow folders, its fact-checker unchanged)
- What was taken (workflow shapes re-authored in our own words, no verbatim text):
  - From ARS: three-class citation verdict with asymmetric evidence rules (ID-keyed miss = fabrication evidence, title-only miss = coverage gap); DOI-first resolution with title cross-check; claim verdict taxonomy separating distortion from inaccessibility (paywall never blocks); risk-stratified sampling with recorded tiers; the silent-upgrade audit axes; the deictic time-reference sweep.
  - From K-Dense (MIT): the "APIs fail with HTTP 200" failure catalog; intent-to-database routing; identifier-conversion traps; untrusted-API-response and credential-in-URL rules; "never present metadata as full text"; "search snippets are discovery aids, not verified support"; OpenAlex integration approach.
  - From research-superpower (MIT): test-driven screening rubric with hand-labelled ground-truth set and cached re-screening; parallel batch screening with shared-rate-limit arithmetic and main-agent write ownership; mandatory Unpaywall fallback with real-email rule; always-hyperlinked identifiers; retrofitted methodology/reproducibility block.
  - From franklee16 (its MIT-licensed fact-checker skill): UNVERIFIABLE as a first-class verdict.
- What was deliberately dropped: ARS's 39-agent ensemble, 10-stage pipeline, reviewer panel (its "pressure is not evidence" clause is earmarked for home/rules/ instead), Material Passport machinery and the one-file evidence ledger derived from it (removed 2026-09-22, never used in any project), contract-paraphrase blocks (Fable reasoning-echo risk), self-preflight loops (Opus over-verification), firm-rule ID namespaces, byte-locks; K-Dense's vendor-upsell footers and mandatory AI-figure rule; all keyed third-party wrappers (Paperclip, Parallel, Exa); research-superpower's ChEMBL skill and emoji progress reporting; franklee16's web-search deep-research family and its unlicensed skills (ideas from those reimplemented conceptually only: the Crossref confidence-table output shape).
- License notes: ARS is CC-BY-NC-4.0 (shapes only, nothing verbatim; attribution kept here; personal noncommercial use). K-Dense and research-superpower are MIT (adaptation permitted with attribution). franklee16 has no repo license; only its MIT-marked skills were used as sources of ideas.

## aldogor-style, prose pass
- Distilled from: cursor/plugins @ e8d856f0273b42ebafe0ec3546bd645709e7c1b0 (pstack/skills/unslop/SKILL.md, file dated 2026-09-07); the skill's first form was a fork of the humanize skill built on Wikipedia's "Signs of AI writing".
- Date reviewed: 2026-09-14; re-reviewed 2026-10-09 at ccb5507cec1546dc88135c1139c811e6c59115ba (unslop last changed in 70b2dc8, 2026-09-22, which removes its self-audit step; no backport)
- What survives (ideas re-authored in Italian, no verbatim text): the sentence that says the thing instead of how it sounds, and words chosen plainly, folded into the third and fifth of the five points of the prose pass. The Wikipedia-derived catalogue of AI tells was removed from the skill on 2026-09-22. The colon that introduces what its clause announced, never a label hung on its content, comes from andrewroxby/claude-style-patch @ 9073af0533c2f97be4ff83b53fe9a21af3a4feeb (CC0), in the fourth point and in home/rules/writing-style.md.
- What was deliberately dropped: the tell catalogue as a whole, its ban on parentheses as dash replacements, its mandatory always-on activation.
- License notes: pstack/LICENSE is MIT (copyright 2026 Lauren Tan) and covers the unslop skill; the repository root carries no licence. Attribution kept here.

## aldogor-style, structural pass (figures and reporting guidelines)
- Distilled from: cathrynlavery/diagram-design @ dc1ace47b99a419e42d01a03cb6ace5346efa8ae (v2.6.33); K-Dense-AI/scientific-agent-skills @ 49c6e97775eaa18ba791bebe23162a70ae601c18 (skills/scientific-writing, skills/scientific-visualization)
- Date reviewed: 2026-09-26 (report in audit/repo-review-2026-09.md); diagram-design re-reviewed 2026-10-09 at f4547ee95f88e5b28a52517feff6b6c11cc657f9 (v2.6.68: changes to the drawing system only, no backport)
- What was taken (ideas re-authored in Italian, no verbatim text): from diagram-design, the figure test (a figure earns its place only where a table or a paragraph would not do; remove any element the reader does not use; above about ten elements, split into an overview and a detail); from scientific-writing, the check of a paper or protocol against the reporting guideline of its design, AI extensions included, read on EQUATOR, with adherence never claimed from a partial check (PRISMA-ScR and DECIDE-AI added on our side; STARD-AI and TRIPOD-LLM checked on EQUATOR and Nature Medicine on 2026-09-26); from scientific-visualization, the figure-integrity checks (uncertainty named with n, bars from zero, colour never the only cue, the figure viewed at print size).
- What was deliberately dropped: diagram-design's drawing system (41 visual types, design tokens, connector rules, templates, animation, brand profiles, draw.io, Mermaid and Excalidraw import, SVG and PNG export, six slash commands); K-Dense's evidence-ID manifests, validators and intake gates, its Python toolchains and publisher profiles, its AI-image figure and slide generation, and the citation footer asking that its paper be cited.
- License notes: diagram-design is MIT (copyright 2025 Cathryn Lavery). scientific-agent-skills is MIT at repository level (copyright 2025 K-Dense Inc.) and both skills used declare MIT. Adaptation permitted with attribution; attribution kept here.

## aldogor-research (retraction, quotations, independence)
- Distilled from: jordan-gibbs/hyperresearch @ 75b1ecfb2891184fad2cc1a2ddf9abe476f5b54c (v0.11.1, 2026-09-12)
- Date reviewed: 2026-09-14; re-reviewed 2026-10-09 at 7790041c8705568effea2b018048160c89f848f4 (after v0.12.0: an unknown retraction result never erases a known one, its #146, taken as "an unanswered lookup is reported as unknown")
- What was taken (rules only): retraction and corrections re-read at delivery time; quotations located verbatim or marked contradicted; evidence weighed by independent studies, not papers. The chimeric-citation line (right title, wrong authors) comes from PHY041/claude-skill-citation-checker (no licence, idea only).
- What was deliberately dropped: the 16-step pipeline, the 16-agent roster, the source vault, Crawl4AI, the cite-check tooling; a sandbox test was judged not worth its cost (web-first, no PubMed, hours of Opus subagents per run).
- License notes: MIT (adaptation permitted with attribution; attribution kept here).

## aldogor-style-learn (counting rule)
- Distilled from: TravinDSO/myvoice-skill @ cad3bd5011d2c0e219e45ab18ec26f21e859f4a5
- Date reviewed: 2026-10-09
- What was taken (ideas re-authored in Italian, no verbatim text): a pattern counted by distinct texts, proposed at three, offered at two, kept as an observation at one; only the user's own changes count as evidence; a revert of Claude's change teaches what to leave alone.
- What was deliberately dropped: the per-folder MYVOICE.md, the "final piece" trigger, the single-file profile.
- License notes: MIT (adaptation permitted with attribution; attribution kept here).

## aldogor-legislation (scripts/legislation.py)
- Distilled from: Honeyfield-Org/eurlex-mcp-server @ 78e0dbde6fa11fa4b88b7ebac6bee52bbb5ba9a9; adellorto/normattiva-mcp @ abfee4d7e10647096156caf60ba2eea5aa85eb75 (tag v0.1.4) and @ 81e447ff426d2c174d00056eec8225004a501803 (main, the 0.2 line)
- Date reviewed: 2026-11-01
- What was taken (query patterns and request shapes, rewritten in Python with the standard library; no code copied):
  - From eurlex-mcp-server's cellarClient.ts: the SPARQL patterns for an act's metadata in one language (title, document date, entry-into-force dates, end of validity, in-force flag, transposition deadline); the consolidated versions as the CELEX numbers matching 0YYYYTNNNN with an optional -YYYYMMDD, newest first; the national implementing measures through the implements relation, the NIM CELEX prefix 7 and the country filter; title search with no ORDER BY and an oversampled limit; the Cellar content request by CELEX with Accept and Accept-Language, retrying HTTP 202 and empty bodies.
  - From normattiva-mcp v0.1.4: the OpenData API base, the advanced search and article detail endpoints with their headers, and the article suffix index (1 for the base article, 2 for bis). From its main branch: the tipoDettaglio "singolavigenza" field, without which the article detail ignores dataVigenza and returns the current text.
- Read for comparison and not used: cyanheads/eur-lex-mcp-server (Apache-2.0). The Piedmont sources (Arianna, CSI Piemonte's normacat service, the BURP search) come from research on 2026-11-01, with no code behind them.
- What was deliberately dropped: the MCP server layer; CJEU case law, EuroVoc, the citation graph, LEGISSUM summaries and the raw SPARQL tool of eurlex-mcp-server; normattiva-mcp's article enumeration by probing, its recent-updates search and its 0.2 portal and AKN reading.
- License notes: both MIT (adaptation permitted with attribution; attribution kept here and in the script's docstring).

## aldogor-pseudonymize (scripts/vendor/rizzo_pii, scripts/pz_engine.py, scripts/data/comuni_it.txt)
- Vendored from: Rizzo-AI-Academy/rizzo-pii @ 30d6f9c675e245bc8494df959adaeaa9d8de35c7: `src/app/detectors.py` unchanged (sha256 9b80026806911d3836ab7baaa553f36a3309314c18c66a0a4009c4133f6e0135) in `scripts/vendor/rizzo_pii/`, with its `LICENSE` and four of its tests (`test_carta_scadenza`, `test_detector_formats`, `test_docid_e_date`, `test_iban_formato_stampa`), whose only change is the path to the module.
- Adapted from the same commit: `chunk_text`, the model call and `_merge` of `src/app/app.py`, rewritten in `scripts/pz_engine.py` (`chunk_text`, `RizzoDetector`, `merge`), with this plugin's rules, project table and filters around them.
- Model: rizzoaiacademy/rizzo-pii-0.3B at revision a1c3c83827eca22e9675e30c1111c4641caf5901 (tag v1.5.0), MIT, on jhu-clsp/mmBERT-base (MIT); downloaded by `setup` into the plugin's data folder, JSON and safetensors files only.
- Data: `scripts/data/comuni_it.txt`, the active municipalities of the ANPR archive (italia/anpr, `src/archivi/ANPR_archivio_comuni.csv`, downloaded 2026-10-22), CC BY 4.0, attribution in the file's header.
- Ideas only, no code: EU-ECDC/Medical-Redactor (EUPL-1.2, read 2026-10-22): dates kept in clear in lab tables, corrections at review fed back into the lists. noirdoc-ai/mask-claude-plugin (MIT, read 2026-10-21): the guard on a folder of originals and the threat-model table of what a plugin can and cannot stop.
- Date reviewed: 2026-10-22, shipped 2026-11-01.
- What was deliberately dropped: rizzo-pii's web app and API layer; the GLiNER and Presidio detectors compared during the evaluation.
- License notes: MIT (code and model), CC BY 4.0 (municipalities); nothing from redact-restore (AGPL-3.0) or Medical-Redactor (EUPL-1.2) is copied.

## Superpowers (reference package, tuning record)
- Package: superpowers@claude-plugins-official (obra/superpowers), installed from the official marketplace at project scope, never vendored: 7.0.0 (bb92a77741419a4ab5f06e711a283343f1ada0c3) or 6.4.1 according to the folder; 7.0.1 (2026-10-21) waits for the marketplace.
- Date reviewed: 2026-11-01, every skill of 7.0.0 and its SessionStart hook, with its use in the transcripts over 90 days (27 skill calls, 16 of them in August) and what its users, its maintainer and Anthropic have said of it; earlier review 2026-08-05 at 6.2.0.
- Tuning applied on our side only: never enabled at user scope; enabled at project scope in the app repositories, where aldogor-project-setup installs it for development projects, and disabled in the research, teaching and infra repositories, this one included, whose `false` entries are inert. skillOverrides cannot target plugin skills (documented limitation), so no per-skill downgrades exist to break on upstream updates.
- Re-check at the quarterly backport review: in each app repository the first feature planned decides whether plan mode replaces it; once no project enables it, one uninstall removes every record.

## This repository's rules for writing skills (the form of a line; a line answers a failure on record)
- Distilled from: obra/superpowers @ bb92a77741419a4ab5f06e711a283343f1ada0c3, skills/writing-skills/SKILL.md ("Match the Form to the Failure"; the baseline run before a skill is written)
- Date reviewed: 2026-11-01
- What was taken: the form of a guidance line chosen by the failure it fixes (an element that goes missing gets a slot in the template, conditional behaviour gets an observable condition, an exception becomes a condition of its own rather than a clause appended to the rule); a line that shapes behaviour answers a failure on record, which Anthropic's skill authoring guide also asks through evaluations built against a baseline.
- What was deliberately dropped: the rest of writing-skills (descriptions limited to triggering conditions, bulletproofing with rationalisation tables and persuasion principles, the iron law that deletes an untested skill) and the package's other skills.
- License notes: MIT, Copyright (c) 2025 Jesse Vincent; ideas reworded, no text copied.
