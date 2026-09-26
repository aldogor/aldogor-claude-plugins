# Verification: procedures and verdicts

## Existence check (per citation)

1. Resolve the identifier first (DOI via Crossref or OpenAlex; PMID via PubMed). Then confirm the returned title matches the cited work (allowing minor formatting differences). A resolving DOI whose title belongs to a different paper is a **mismatch failure**: the citation is wrong even though the DOI "works". So is a chimeric citation: the right title with the wrong authors or year.
2. No identifier given: search by title + first author + year (OpenAlex, then PubMed for biomedical).
3. Retraction and corrections, at delivery time: read `updated-by` on the Crossref record (retraction, correction, expression_of_concern, each dated) and `is_retracted` on the OpenAlex record. A retracted source is dropped or cited as retracted in the text; a correction or expression of concern that touches the claim is mentioned in the text.
4. Classify the evidence asymmetrically:
   - Any confirmed match → exists (even if another database misses it).
   - An **identifier that provably fails to resolve** → fabrication evidence (contradicted). A transient outage does not cancel this; note both.
   - **Title-only miss** (no identifier to test) → coverage gap → unverifiable, never contradicted. Grey literature, institutional reports, and non-English sources are routinely unindexed.

## Support check (per claim-citation pair)

Open the source, best available depth: full text (PMC, Unpaywall PDF) > abstract > metadata. Confirm the claim as written matches the source on all six axes:

| Axis | Silent-upgrade failure to catch |
| --- | --- |
| Direction/strength | "associated with" cited as "prevents"/"causes" |
| Design ceiling | cross-sectional or cohort cited as causal evidence |
| Population | source studied nurses; draft says "health workers" |
| Exposure/intervention | narrower or different intervention than claimed |
| Outcome and timeframe | different endpoint, or short-term result cited as long-term |
| Hedges | source's "may", "in this sample", confounder caveats dropped |

Verified at abstract depth only: say so ("verified against abstract; full text inaccessible").

Quotations: a span of five or more words taken from the source is marked as a quotation and located; a summary is reworded. A quotation that cannot be found verbatim in the source is a contradicted citation.

## Verdicts

Citation-level: **verified / unverifiable / contradicted** (three classes, never two).

Claim-level, when auditing a document:

| Verdict | Meaning | Blocks delivery? |
| --- | --- | --- |
| VERIFIED | source found, supports as written | no |
| MINOR_DISTORTION | supported but overstated/imprecise | fix wording |
| MAJOR_DISTORTION | source says something materially different | yes: fix or remove |
| UNVERIFIABLE | cannot confirm or deny | mark in text |
| UNVERIFIABLE_ACCESS | source exists but is paywalled/unreachable | no: mark, do not treat as wrong |

Marking in text: either the explicit tag ("...reduces incidence [unverified]") or the safer rewrite: downgrade the claim to what IS verifiable ("two studies report an association..." instead of an unverifiable causal claim). Prefer the safer rewrite in deliverables, the tag in drafts. Hedging is not a downgrade: "may", "some evidence suggests" or "it is reported that" in front of an unverified claim leaves it unverified; the rewrite states only what a verified source states, or carries the tag.

## Sampling for long documents

Verify 100% of high-impact claims: numeric, causal, headline/conclusion-bearing, methods-critical, and anything contested or surprising. Sample the rest (about 10%, minimum 3). Record for every claim which tier it fell in, including "not selected", so coverage is inspectable. Never report "all citations verified" after sampling; report the actual counts per verdict and tier.

## Time-reference sweep

Before delivery, search the text for undated deictics: "currently", "recently", "the latest", "to date", "emerging", "nowadays", "in recent years". Replace with dated forms ("as of mid-2026", "since 2023") or delete. Undated time references silently expire and are a distinct failure class from wrong citations.
