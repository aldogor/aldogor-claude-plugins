---
name: aldogor-legislation
description: >-
  Reads Italian state law (Normattiva), EU law (EUR-Lex) and Piedmont's regional laws, regulations and bulletin acts (Arianna, BURP) from their official sources, as in force on a given date, with the link to cite. Use when the user asks what a law, decree, regulation or deliberation says, whether an article is in force or was amended or repealed, which version applied on a date, how a directive was transposed into Italian law, or to check the legal references of a document ("aldogor-legislation", "cosa dice la legge", "è ancora in vigore", "testo vigente", "verifica i riferimenti normativi", "cita il decreto", "D.Lgs.", "DPR", "legge regionale", "DGR", "BUR Piemonte", "recepimento della direttiva", "Normattiva", "EUR-Lex").
---

# Aldogor-legislation

Legal text is read at its source and at the date that matters, and quoted from what was read: the article as in force on the document's date, or today for current advice, with the link that opens the same version. The helper is `scripts/legislation.py` in this skill's folder; it needs only Python and the network, and `python scripts/legislation.py <command> --help` describes each command.

## What the sources cover

| Source | Acts | Version by date | Commands |
|---|---|---|---|
| Normattiva | State acts published in the Gazzetta Ufficiale: laws, legislative decrees, decree-laws, DPR, DPCM, ministerial decrees | any article as in force on a date | `it-search`, `it-article` |
| EUR-Lex | Regulations, directives, decisions; the national measures that transpose a directive | the consolidated version that applies on a date | `eu-lookup`, `eu-text`, `eu-transpositions`, `eu-search` |
| Arianna, the Consiglio regionale del Piemonte's database | Piedmont's regional laws since 1970 and its regional regulations | every version with its validity, and the notes recording each amendment | `pie-law`, `pie-search` |
| BURP, the Bollettino Ufficiale della Regione Piemonte | DGR, DD and DPGR as published | as published | `bur-search`, `bur-act` |

Other regions' laws, ministerial circulars and notes, the agreements of the Conferenza Stato-Regioni, a health authority's own deliberations and case law are in none of them. For such an act, name where it is published (the region's bulletin, the ministry's site, statoregioni.it) and say that it was not read.

## Commands

- `it-search --type DLGS --year 2003 --number 196`, or words with `--title` and `--text`; `it-article` with the same act and `--article 2-septies --date YYYY-MM-DD`. Types: L, DLGS, DL, DPR, DPCM, RD, DM, or Normattiva's full label.
- `eu-lookup "Regolamento (UE) 2016/679"`, or a CELEX or ELI; `eu-text <act> --article 9 --date YYYY-MM-DD`, with `--original` for the Official Journal text and `--toc` for the list of articles; `eu-transpositions <directive>`; `eu-search "parole del titolo" --type REG`.
- `pie-law --year 2007 --number 18 --date YYYY-MM-DD --article 3`, with `--regulation`, `--toc` and `--versions`; `pie-search parole --in text`.
- `bur-search "parole"`; `bur-act <act page URL> --out <scratchpad folder>` saves the act's PDF, which Claude then reads.
- `smoke` makes one live request to each source, for when one of them seems to fail.

## Checking the legal references of a document

1. List each reference with the date it must hold on: the document's date, a deadline, or today.
2. Read each article at that date with `it-article`, `eu-text` or `pie-law`. Check that it says what the document makes it say, that the version shown covers the date, and whether it was amended or repealed: Normattiva marks inserted or replaced text with `(( ))` and writes ARTICOLO ABROGATO, and Arianna lists its amendment notes after the text.
3. For a directive, `eu-transpositions` names the Italian measures, and `it-search` finds them on Normattiva.
4. Report each reference with what it says, the source and the date it was read at, and any mismatch, then cite it in the form of [references/citing.md](references/citing.md).

## Pitfalls

- Normattiva's resolver ignores the region in a regional URN and returns the state act with the same number, so a regional act is read and linked through Arianna only; the helper refuses a regional URN for Normattiva.
- EUR-Lex title search matches words of the title in Italian, and broad words time out: search by number when it is known, or add `--type` and dates.
- An in-force flag that CELLAR does not record means unknown, not repealed: read the end of validity and the consolidated versions.
- Arianna's consolidated text is an aid; the text as published in the BURP is the official one, and a formal document cites that.
- A BURP address may change, so a bulletin act is cited by its type, date and number together with its URL.
- A structured code may return no article at the default group; `--group 1`, `--group 2` and so on reach it.
