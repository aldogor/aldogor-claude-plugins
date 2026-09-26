# Screening: test-driven rubrics and parallel batches

## Build the rubric test-first

1. Draft explicit scoring components from the eligibility criteria, each with a point range and anchors, e.g.: topic match 0-3, population 0-3, design eligibility 0-2, setting/scope 0-2; include threshold (e.g. ≥7 = include, 5-6 = borderline for human review).
2. The user hand-labels 5-10 abstracts (mix of clear includes, clear excludes, borderlines) as the ground-truth set.
3. Score the rubric against the set. For every disagreement show the per-component breakdown so the user sees WHY the rubric misjudged.
4. Iterate components/weights until the rubric reproduces the user's labels (target ≥80% before bulk screening; borderlines routed to human review do not count as errors).
5. Freeze the rubric with a version label. Cache all fetched abstracts locally (one JSON per corpus): a later rubric revision re-screens the cache for free, and the report lists exactly which papers changed status and why.

## Parallel batches (corpora over ~50 papers)

- Split identifiers into batches of 15-25; dispatch up to 5 parallel screening subagents in a single message.
- Each subagent prompt contains: the frozen rubric verbatim, its batch of IDs, the rate-limit spacing to apply (delay per request = number of parallel agents / endpoint rate limit, plus margin: e.g. 5 agents on a 2 req/s endpoint = 2.5 s + margin), and the instruction to return ONLY a JSON array of {id, per-component scores, total, verdict, one-line reason}.
- Subagents never write tracking files; the main session owns all files and merges results into one table.
- After merging: reconcile counts (dispatched = returned; expected corpus = screened corpus) and re-dispatch gaps before reporting.

## Reporting (PRISMA-ready)

The screening report always states: the exact query strings per database (verbatim, credentials stripped); dates of the searches; counts at each stage (retrieved → deduplicated → screened → included, with exclusion reasons tallied); rubric version and threshold; the ground-truth accuracy achieved before bulk screening; and any papers whose status changed across rubric revisions. This is the PRISMA flow's raw material; produce the numbers even when no formal PRISMA diagram was requested.
