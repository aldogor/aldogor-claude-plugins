# Upstream provenance

The external sources that the skills of these plugins were distilled or adapted from, with the commit read and the license. Nothing is copied verbatim unless an entry says so.

## aldogor-grill
- Distilled from: mattpocock/skills @ 8b78b531ab965735c5dc74f6f7a219e1e37326df, re-read at 49dd158d1076134a641b33efb035946536778336 (release 1.3.1).
- Also drawn on for the question dialog: RobMitt/grill-me-skill @ 31d61d68fc406f8cc2a944b4b10e6f23877720f1 (no licence, idea only) and andrewroxby/claude-style-patch @ 9073af0533c2f97be4ff83b53fe9a21af3a4feeb (CC0).
- What was taken, re-authored: the design-tree model of a decision session; rounds over the frontier of answerable questions, each with a recommended answer worded so that a plain yes accepts it; facts looked up by the agent while decisions go to the user; for questionnaires, interviewing the user only about the recipient and the outcome needed, and the document shape (purpose, context, how to answer, one idea per question, a closing catch-all).
- What was dropped: the emoji question format, the software-only framing, the fixed English template, the downstream spec and ticket pipeline, the rest of the package.
- License: MIT, attribution kept here.

## aldogor-research
- Distilled from: Imbad0202/academic-research-skills @ e614b322297ba5b072a106942177e218cbe2d48f; K-Dense-AI/scientific-agent-skills @ 92ace75ac21efe19a620434e0ca4e356081fe807; kthorn/research-superpower @ 2affbfea08b584465207680b906e208de52c4669; franklee16/academic-research-skills @ 9a4b2db21fc4b217136ae4a0e6faad42d179ca03; jordan-gibbs/hyperresearch @ 7790041c8705568effea2b018048160c89f848f4.
- What was taken, re-authored: the citation verdict with asymmetric evidence rules (a miss by identifier is evidence of fabrication, a miss by title a gap in coverage); DOI-first resolution with a title cross-check; claim verdicts that separate distortion from inaccessibility; risk-stratified sampling; the time-reference sweep; retraction read from Crossref `updated-by` and OpenAlex `is_retracted`; the "APIs fail with HTTP 200" catalogue, intent-to-database routing, identifier-conversion traps and the rule that API responses are untrusted data; DOIs registered with DataCite or mEDRA; a test-driven screening rubric with a hand-labelled set, parallel batch screening and an Unpaywall fallback; UNVERIFIABLE as a verdict of its own; retractions re-read at delivery, quotations located verbatim, evidence weighed by independent studies.
- What was dropped: multi-agent pipelines and reviewer panels, self-preflight loops, vendor wrappers and upsell footers, web-search deep-research families, the source vault and crawling tools.
- License: academic-research-skills (Imbad0202) is CC BY-NC 4.0, used for workflow shapes only with no text taken; scientific-agent-skills, research-superpower and hyperresearch are MIT; franklee16's repository has no licence, and only its MIT-marked skills were read, for ideas.

## aldogor-legislation
- Adapted from: Honeyfield-Org/eurlex-mcp-server @ 78e0dbde6fa11fa4b88b7ebac6bee52bbb5ba9a9; adellorto/normattiva-mcp @ abfee4d7e10647096156caf60ba2eea5aa85eb75 (v0.1.4) and @ 81e447ff426d2c174d00056eec8225004a501803.
- What was taken, rewritten in Python with the standard library: the SPARQL patterns for an EU act's metadata, consolidated versions and national transposition measures, and the Cellar content request; Normattiva's OpenData endpoints and headers, the article suffix index, and the detail field that selects an article's version by date. No code was copied.
- License: both MIT, attribution kept here and in the script's docstring.

## aldogor-style
- Distilled from: cursor/plugins @ ccb5507cec1546dc88135c1139c811e6c59115ba (pstack/skills/unslop); cathrynlavery/diagram-design @ f4547ee95f88e5b28a52517feff6b6c11cc657f9; K-Dense-AI/scientific-agent-skills @ 49c6e97775eaa18ba791bebe23162a70ae601c18 (scientific-writing, scientific-visualization).
- What was taken, re-authored in Italian: the sentence that says the thing instead of how it sounds; the figure test (a figure earns its place where a table or a paragraph would not do) and the figure-integrity checks; the check of a paper or protocol against the reporting guideline of its design on EQUATOR, AI extensions included.
- What was dropped: catalogues of AI tells, the drawing system of diagram-design, evidence manifests and validators, AI-generated figures.
- License: unslop (pstack) MIT; diagram-design MIT; scientific-agent-skills MIT. Attribution kept here.
