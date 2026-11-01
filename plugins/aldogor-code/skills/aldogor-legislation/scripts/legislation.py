#!/usr/bin/env python3
"""Reads Italian state law, EU law and Piedmont's regional acts from their official sources.

The helper of the aldogor-legislation skill. It uses the standard library only, so it runs wherever Python 3.10 or
later does, and it prints plain text: the act's heading, the dates that say which version is shown, a link to cite,
and the text or the list asked for.

Sources:
  Normattiva  IPZS's OpenData API: search of state acts, and one article as in force on a date.
  EUR-Lex     the EU Publications Office: CELLAR SPARQL for metadata, consolidated versions and national
              transpositions; the Cellar content API for the text, in Italian by default.
  Arianna     the Consiglio regionale del Piemonte's database: regional laws and regulations in consolidated text,
              every version with its validity, and search. CSI Piemonte's normacat service gives the current text as
              plain text when Arianna's page cannot be read.
  BURP        the Bollettino Ufficiale della Regione Piemonte: free-text search, and the PDFs of DGR, DD and DPGR.

The EUR-Lex queries are adapted from Honeyfield-Org/eurlex-mcp-server (MIT), and Normattiva's endpoints and the
field that selects an article's version by date from adellorto/normattiva-mcp (MIT), as upstream/UPSTREAM.md records.

Usage (each command has --help):
  python legislation.py it-search --type DLGS --year 2003 --number 196
  python legislation.py it-article --type DLGS --year 2003 --number 196 --article 2-septies --date 2019-01-01
  python legislation.py eu-lookup "Regolamento (UE) 2016/679"
  python legislation.py eu-text 32016R0679 --article 9 --date 2019-01-01
  python legislation.py eu-transpositions "Direttiva (UE) 2022/2555"
  python legislation.py eu-search "dispositivi medici" --type REG
  python legislation.py pie-law --year 2007 --number 18 --date 2010-01-01 --article 3
  python legislation.py pie-search vaccinazioni --in text
  python legislation.py bur-search "piano regionale della prevenzione"
  python legislation.py bur-act <act page URL> --out <folder>
  python legislation.py smoke

Exit codes: 0 done, 1 a source failed or has no such act, 2 a wrong argument.
"""

import argparse
import datetime as dt
import json
import pathlib
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from http.cookiejar import CookieJar

USER_AGENT = "aldogor-legislation/1.0 (+https://github.com/aldogor/aldogor-claude-plugins)"
TIMEOUT = 45
# Seconds to wait before the second and the third attempt of a request that failed for a reason worth retrying.
RETRY_WAITS = (1.5, 4.0)


class SourceError(Exception):
    """A source answered with an error, or not at all, or holds no such act; the message says which."""


# --------------------------------------------------------------------------------------------------------------------
# HTTP and text


def http(url: str, data: bytes | None = None, headers: dict | None = None, opener=None) -> tuple[bytes, str, str]:
    """GET url, or POST data to it, and return (body, content type, final URL after redirects).

    Retries twice on network errors, timeouts, HTTP 5xx, and HTTP 202 or an empty body (Cellar answers so while it
    is still rendering a document). An HTTP 4xx is never retried: it says the request itself is wrong. Tests replace
    this function, so every network call of the module goes through it.
    """
    request = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, **(headers or {})})
    open_url = (opener or urllib.request.build_opener()).open
    last = ""
    for wait in (0, *RETRY_WAITS):
        if wait:
            time.sleep(wait)
        try:
            with open_url(request, timeout=TIMEOUT) as response:
                body = response.read()
                if response.status == 202 or not body.strip():
                    last = f"HTTP {response.status} with no content yet"
                    continue
                return body, response.headers.get("Content-Type", ""), response.geturl()
        except urllib.error.HTTPError as error:
            detail = error.read()[:300].decode("utf-8", "replace")
            if error.code < 500:
                raise SourceError(f"{url}: HTTP {error.code} {detail}".strip()) from None
            last = f"HTTP {error.code}"
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            last = str(getattr(error, "reason", error))
    raise SourceError(f"{url}: {last}")


def decode(body: bytes, content_type: str = "") -> str:
    """The body as text.

    A declared charset other than UTF-8 is used as declared. Otherwise valid UTF-8 sequences are read as UTF-8 and
    any other byte as Windows-1252: the BURP's search engine declares no charset and writes Windows-1252, and
    Arianna's UTF-8 pages carry notes in Windows-1252.
    """
    charset = re.search(r"charset=([\w-]+)", content_type or "")
    if charset and charset.group(1).lower().replace("_", "-") not in ("utf-8", "utf8"):
        return body.decode(charset.group(1), "replace")
    text = body.decode("utf-8", "surrogateescape")
    return re.sub(r"[\udc80-\udcff]",
                  lambda stray: bytes([ord(stray.group()) - 0xDC00]).decode("cp1252", "replace"), text)


# Tags after which a line ends, so that paragraphs, list items and table rows stay apart in the text.
BLOCK_TAGS = {"p", "div", "br", "li", "tr", "table", "ul", "ol", "dt", "dd", "h1", "h2", "h3", "h4", "h5", "h6",
              "section", "article", "blockquote"}
SKIPPED_TAGS = {"script", "style", "head", "noscript"}


class _TextExtractor(HTMLParser):
    """Collects an HTML page's text, ending a line at each block element and leaving scripts and styles out."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skipping = 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIPPED_TAGS:
            self.skipping += 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")
        elif tag == "td":
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in SKIPPED_TAGS:
            self.skipping = max(0, self.skipping - 1)
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skipping:
            self.parts.append(data)


def html_to_text(markup: str) -> str:
    """Plain text of an HTML fragment: one line per block, spaces collapsed, at most one empty line in a row."""
    parser = _TextExtractor()
    parser.feed(markup)
    parser.close()
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def join_paragraphs(text: str) -> str:
    """Rejoin the lines of each paragraph, for pages whose markup breaks a sentence around links and references.

    Paragraphs stay apart, at their empty lines; a space left before closing punctuation or after an opening
    bracket by the rejoining is removed.
    """
    paragraphs = (" ".join(block.split()) for block in re.split(r"\n\s*\n", text))
    joined = "\n\n".join(p for p in paragraphs if p)
    return re.sub(r"\(\s+", "(", re.sub(r"\s+([).,;:])", r"\1", joined))


def iso_date(value: str | None) -> str:
    """A date given as YYYY-MM-DD, checked; today when none is given."""
    if not value:
        return dt.date.today().isoformat()
    try:
        return dt.date.fromisoformat(value).isoformat()
    except ValueError:
        raise SystemExit(f"Not a date in the form YYYY-MM-DD: {value}") from None


# --------------------------------------------------------------------------------------------------------------------
# Normattiva: Italian state law

NORMATTIVA_API = "https://api.normattiva.it/t/normattiva.api/bff-opendata/v1/api/v1"
NORMATTIVA_HEADERS = {"Content-Type": "application/json", "Accept": "application/json",
                      "Origin": "https://dati.normattiva.it"}
# Short forms accepted by --type, mapped to Normattiva's own act-type labels (its denominazioneAtto). Any other value
# is passed on in capitals, so a label such as "DECRETO-LEGGE" works as written.
IT_TYPES = {"L": "LEGGE", "LEGGE": "LEGGE", "DLGS": "DECRETO LEGISLATIVO", "DL": "DECRETO-LEGGE",
            "DPR": "DECRETO DEL PRESIDENTE DELLA REPUBBLICA", "DPCM": "DECRETO DEL PRESIDENTE DEL CONSIGLIO DEI MINISTRI",
            "RD": "REGIO DECRETO", "DM": "DECRETO", "COST": "COSTITUZIONE"}
# The NIR name of the act types whose URN has the form urn:nir:stato:<name>:<date>;<number>. Other types (ministerial
# decrees name their ministry) are linked through Normattiva's act page instead.
URN_TYPES = {"LEGGE": "legge", "DECRETO LEGISLATIVO": "decreto.legislativo", "DECRETO-LEGGE": "decreto.legge",
             "DECRETO DEL PRESIDENTE DELLA REPUBBLICA": "decreto.del.presidente.della.repubblica",
             "DECRETO DEL PRESIDENTE DEL CONSIGLIO DEI MINISTRI": "decreto.del.presidente.del.consiglio.dei.ministri",
             "REGIO DECRETO": "regio.decreto"}
# Latin suffixes of inserted articles, in order: the API numbers them from 1 (the base article), so bis is 2.
SUFFIXES = ("", "bis", "ter", "quater", "quinquies", "sexies", "septies", "octies", "novies", "decies", "undecies",
            "duodecies", "terdecies", "quaterdecies", "quinquiesdecies", "sexiesdecies", "septiesdecies",
            "octiesdecies")


def it_type(value: str) -> str:
    """Normattiva's label for an act type given in short form (DLGS, D.Lgs., DPR...) or in full."""
    return IT_TYPES.get(re.sub(r"[\s.\-]", "", value.upper()), value.upper().strip())


def parse_article(spec: str) -> tuple[int, int, str]:
    """An article reference such as "2-septies", "art. 5 bis" or "13" as (number, suffix index, suffix).

    The suffix index is the API's sottoArticolo: 1 for the base article, 2 for bis, 3 for ter, and so on.
    """
    match = re.fullmatch(r"\s*(?:art(?:icolo)?\.?\s*)?(\d+)\s*[-\s]?\s*([a-z]*)\s*", spec.lower())
    if not match or match.group(2) not in SUFFIXES:
        raise SystemExit(f"Not an article reference: {spec} (examples: 13, 2-bis, 2-septies)")
    return int(match.group(1)), SUFFIXES.index(match.group(2)) + 1, match.group(2)


def normattiva_link(urn: str) -> str:
    """The Normattiva resolver's URL for a state URN.

    Normattiva's resolver ignores the region in a regional URN and answers with the state act of the same number,
    with HTTP 200 (urn:nir:regione.piemonte:legge:2007;18 returns DPR 12 gennaio 2007, n. 18), so a regional URN
    is refused here rather than turned into a wrong link.
    """
    if not urn.startswith("urn:nir:stato:"):
        raise ValueError(f"Normattiva resolves state acts only, never a regional URN: {urn}")
    return "https://www.normattiva.it/uri-res/N2Ls?" + urn


def it_link(act: dict, article: tuple[int, int, str] | None = None, date: str | None = None) -> str:
    """The link to cite a state act, or one of its articles as in force on a date.

    The URN form is used for the act types that have one; otherwise Normattiva's act page, keyed by the Gazzetta date
    and the codice redazionale.
    """
    label = act.get("denominazioneAtto", "")
    issued = (act.get("dataEmanazione") or "")[:10]
    if label in URN_TYPES and issued and act.get("numeroProvvedimento"):
        urn = f"urn:nir:stato:{URN_TYPES[label]}:{issued};{act['numeroProvvedimento']}"
        if article:
            urn += f"~art{article[0]}{article[2]}"
        if date:
            urn += f"!vig={date}"
        return normattiva_link(urn)
    return ("https://www.normattiva.it/atto/caricaDettaglioAtto?atto.dataPubblicazioneGazzetta="
            f"{act.get('dataGU', '')}&atto.codiceRedazionale={act.get('codiceRedazionale', '')}")


def normattiva_post(path: str, payload: dict) -> dict:
    """POST a JSON payload to the OpenData API and return its JSON answer."""
    body, content_type, _ = http(NORMATTIVA_API + path, json.dumps(payload).encode(), NORMATTIVA_HEADERS)
    answer = json.loads(decode(body, content_type))
    if answer.get("status") == "KO":
        # The Poligrafico's firewall answers with a JSON "KO" in place of the data.
        raise SourceError(f"Normattiva refused the request: {answer.get('message')}")
    return answer


def it_search(act_type=None, year=None, number=None, title=None, text=None, limit=10) -> list[dict]:
    """State acts matching the filters, newest first, as Normattiva's search returns them."""
    payload = {"orderType": "recente", "paginazione": {"paginaCorrente": 1, "numeroElementiPerPagina": limit}}
    for key, value in (("denominazioneAtto", act_type and it_type(act_type)), ("annoProvvedimento", year),
                       ("numeroProvvedimento", number), ("titoloRicerca", title), ("testoRicerca", text)):
        if value:
            payload[key] = str(value)
    return normattiva_post("/ricerca/avanzata", payload).get("listaAtti") or []


def it_find(act_type: str, year: int, number: str) -> dict:
    """The one state act of that type, year and number; an error listing the candidates when there are several."""
    acts = [a for a in it_search(act_type, year, number, limit=20)
            if str(a.get("numeroProvvedimento")) == str(number) and str(a.get("annoProvvedimento")) == str(year)]
    if not acts:
        raise SourceError(f"Normattiva has no {it_type(act_type)} n. {number} of {year}")
    if len(acts) > 1:
        names = "; ".join(f"{a.get('descrizioneAtto')} (--code {a.get('codiceRedazionale')} --gu-date "
                          f"{a.get('dataGU')})" for a in acts)
        raise SourceError(f"Several acts match, name one with --code and --gu-date: {names}")
    return acts[0]


def it_article(act: dict, article: tuple[int, int, str], date: str, group: int = 0) -> dict:
    """One article of a state act as in force on date: its text and the dates of that version.

    Without tipoDettaglio "singolavigenza" the API ignores dataVigenza and always returns the current text; the
    field comes from normattiva-mcp's 0.2 line (MIT).
    """
    payload = {"dataGU": act["dataGU"], "codiceRedazionale": act["codiceRedazionale"], "idArticolo": article[0],
               "sottoArticolo": article[1], "sottoArticolo1": 0, "dataVigenza": date, "idGruppo": group,
               "progressivo": 0, "versione": 0, "tipoDettaglio": "singolavigenza"}
    try:
        answer = normattiva_post("/atto/dettaglio-atto", payload)
    except SourceError as error:
        if "trovat" in str(error).lower():  # "non trovato": no such article, or not at that index
            raise SourceError(f"Normattiva has no article {article[0]}{article[2] and '-' + article[2]} in this act; "
                              "structured codes may need --group 1, 2...") from None
        raise
    atto = (answer.get("data") or {}).get("atto") or {}
    if not atto.get("articoloHtml"):
        raise SourceError(f"Normattiva returned no text for article {article[0]}{article[2] and '-' + article[2]}")

    def day(value):  # the API writes dates as YYYYMMDD, and 99999999 for "no end"
        return None if not value or value.startswith("9999") else f"{value[:4]}-{value[4:6]}-{value[6:8]}"

    return {"text": html_to_text(atto["articoloHtml"]), "from": day(atto.get("articoloDataInizioVigenza")),
            "to": day(atto.get("articoloDataFineVigenza"))}


# --------------------------------------------------------------------------------------------------------------------
# EUR-Lex: EU law (queries adapted from Honeyfield-Org/eurlex-mcp-server, MIT)

SPARQL = "https://publications.europa.eu/webapi/rdf/sparql"
CELLAR = "https://publications.europa.eu/resource/celex/"
CDM = "PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>\nPREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n"
LANGUAGE_AUTHORITY = "http://publications.europa.eu/resource/authority/language/"
# Cellar's three-letter language codes, with the HTTP language tag and the word that heads an article.
LANGUAGES = {"ITA": ("it", "Articolo"), "ENG": ("en", "Article"), "FRA": ("fr", "Article"), "DEU": ("de", "Artikel"),
             "SPA": ("es", "Artículo")}
# The CELEX type letter of each act family, from the words that name it in Italian and in English.
EU_TYPES = {"regolamento": "R", "regulation": "R", "reg": "R", "direttiva": "L", "directive": "L", "dir": "L",
            "decisione": "D", "decision": "D", "dec": "D"}
ELI_TYPES = {"R": "reg", "L": "dir", "D": "dec"}


def parse_eu_ref(ref: str) -> str:
    """The CELEX number of an EU act given as a CELEX number, an ELI, or a citation in Italian or English.

    Citations follow two numbering styles. From 2015 every act is "(UE) year/number"; before, directives and
    decisions were "year/number" (two-digit years then) and regulations "n. number/year". So a regulation whose
    second figure is a four-digit year before 2015 is read number first, and everything else year first.
    """
    text = ref.strip()
    if re.fullmatch(r"[0-9][0-9]{4}[A-Z]{1,2}[0-9]{4}(\(\d+\))?(-\d{8})?", text.upper()):
        return text.upper()
    eli = re.search(r"eli/(reg|dir|dec)\w*/(\d{4})/(\d+)", text)
    if eli:
        letter = {v: k for k, v in ELI_TYPES.items()}[eli.group(1)]
        return f"3{eli.group(2)}{letter}{int(eli.group(3)):04d}"
    kind = re.search(r"\b(regolamento|regulation|direttiva|directive|decisione|decision|reg|dir|dec)\b", text.lower())
    figures = re.search(r"(\d{1,4})\s*/\s*(\d{1,4})", text)
    if not kind or not figures:
        raise SystemExit(f"Not an EU act reference: {ref} (examples: 32016R0679, Regolamento (UE) 2016/679, "
                         "Direttiva 95/46/CE)")
    letter = EU_TYPES[kind.group(1)]
    first, second = figures.group(1), figures.group(2)
    if letter == "R" and len(second) == 4 and int(second) < 2015:
        number, year = int(first), int(second)
    else:
        year, number = int(first), int(second)
        if year < 100:
            year += 2000 if year < 50 else 1900
    return f"3{year}{letter}{number:04d}"


def sparql(query: str) -> list[dict]:
    """The rows of a SPARQL SELECT on CELLAR, each a dict of variable name to string value."""
    body, content_type, _ = http(SPARQL, query.encode(), {"Content-Type": "application/sparql-query",
                                                          "Accept": "application/sparql-results+json"})
    rows = json.loads(decode(body, content_type))["results"]["bindings"]
    return [{key: cell["value"] for key, cell in row.items()} for row in rows]


def eu_metadata(celex: str, lang: str = "ITA") -> dict:
    """Title and dates of an EU act. A field CELLAR does not record is absent, which is not the same as false."""
    query = CDM + f"""SELECT (SAMPLE(?t) AS ?title) (MIN(?d) AS ?date)
  (GROUP_CONCAT(DISTINCT STR(?f); separator=", ") AS ?force) (MAX(?e) AS ?end) (SAMPLE(?i) AS ?inForce)
  (MIN(?tr) AS ?transposition) WHERE {{
  ?work cdm:resource_legal_id_celex ?c . FILTER(STR(?c) = "{celex}")
  ?expr cdm:expression_belongs_to_work ?work ; cdm:expression_uses_language <{LANGUAGE_AUTHORITY}{lang}> ;
        cdm:expression_title ?t .
  OPTIONAL {{ ?work cdm:work_date_document ?d . }}
  OPTIONAL {{ ?work cdm:resource_legal_date_entry-into-force ?f . }}
  OPTIONAL {{ ?work cdm:resource_legal_date_end-of-validity ?e . }}
  OPTIONAL {{ ?work cdm:resource_legal_in-force ?i . }}
  OPTIONAL {{ ?work cdm:resource_legal_date_transposition ?tr . }}
}} GROUP BY ?work"""
    rows = sparql(query)
    if not rows or not rows[0].get("title"):
        raise SourceError(f"CELLAR has no act {celex} with a title in {lang}")
    return {key: value for key, value in rows[0].items() if value}


def eu_consolidations(celex: str) -> list[str]:
    """The CELEX numbers of an act's consolidated versions, newest first (0YYYYTNNNN-YYYYMMDD)."""
    body = "0" + celex[1:].split("-")[0]
    pattern = "^" + re.escape(body).replace("\\", "\\\\") + "(-[0-9]{8})?$"
    rows = sparql(CDM + f"""SELECT DISTINCT ?celex WHERE {{
  ?work cdm:resource_legal_id_celex ?celex . FILTER(REGEX(STR(?celex), "{pattern}"))
}} ORDER BY DESC(?celex)""")
    return [row["celex"] for row in rows]


def version_on(consolidations: list[str], date: str) -> str | None:
    """The consolidated version that applies on date: the newest one dated on or before it, or None."""
    for celex in sorted(consolidations, reverse=True):
        stamp = celex.rsplit("-", 1)[-1] if "-" in celex else ""
        if len(stamp) == 8 and f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}" <= date:
            return celex
    return None


def eu_text(celex: str, lang: str = "ITA") -> str:
    """The text of an EU act or consolidated version, in lang, from the Cellar content API."""
    tag = LANGUAGES.get(lang, ("it", ""))[0]
    body, content_type, _ = http(CELLAR + urllib.parse.quote(celex), headers={
        "Accept": "application/xhtml+xml, text/html", "Accept-Language": tag})
    return html_to_text(decode(body, content_type))


def eu_article(text: str, number: str, lang: str = "ITA") -> str:
    """One article of an EU text: from its heading line to the next article's or annex's heading."""
    word = LANGUAGES.get(lang, ("", "Articolo"))[1]
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines)
                  if re.fullmatch(rf"{word}\s+{re.escape(number)}", line.strip(), re.I)), None)
    if start is None:
        raise SourceError(f"No {word} {number} in this text")
    end = next((i for i in range(start + 1, len(lines))
                if re.match(rf"({word}\s+\d+\S*|ALLEGATO|ANNEX|ANNEXE|ANHANG)\s*$", lines[i].strip(), re.I)),
               len(lines))
    return "\n".join(lines[start:end]).strip()


def eu_toc(text: str, lang: str = "ITA") -> list[str]:
    """The article headings of an EU text with the title line that follows each."""
    word = LANGUAGES.get(lang, ("", "Articolo"))[1]
    lines = [line for line in text.splitlines() if line.strip()]
    return [f"{line}: {lines[i + 1] if i + 1 < len(lines) else ''}" for i, line in enumerate(lines)
            if re.fullmatch(rf"{word}\s+\d+\S*", line.strip(), re.I)]


def eu_transpositions(celex: str, country: str = "ITA") -> list[dict]:
    """The national measures a member state notified as transposing a directive, newest first."""
    nim = "^7" + re.escape(celex[1:]).replace("\\", "\\\\") + "[A-Z]{3}_"
    rows = sparql(CDM + f"""SELECT DISTINCT ?celex ?title ?date WHERE {{
  ?dir cdm:resource_legal_id_celex ?d . FILTER(STR(?d) = "{celex}")
  ?nim cdm:measure_national_implementing_implements_resource_legal ?dir ;
       cdm:resource_legal_id_celex ?celex ;
       cdm:measure_national_implementing_implemented_by_country <http://publications.europa.eu/resource/authority/country/{country}> .
  FILTER(REGEX(STR(?celex), "{nim}"))
  OPTIONAL {{ ?nim cdm:work_title ?title . }}
  OPTIONAL {{ ?nim cdm:work_date_document ?date . }}
}} ORDER BY DESC(?date) LIMIT 200""")
    return rows


def eu_search(words: str, family: str | None = None, lang: str = "ITA", date_from=None, date_to=None,
              limit: int = 15) -> list[dict]:
    """EU acts whose title in lang contains every word, newest first within what CELLAR returns.

    There is no ORDER BY in the query: sorting forces the endpoint to gather every match and broad words then time
    out, so the query asks for three times the limit and sorts here, as Honeyfield's server does.
    """
    filters = "".join(f'  FILTER(CONTAINS(LCASE(STR(?title)), "{w}"))\n'
                      for w in re.findall(r"[\w'’]+", words.lower()))
    if not filters:
        raise SystemExit("eu-search needs at least one word")
    letter = family and EU_TYPES.get(family.lower(), family.upper()[:1])
    sector = f"3[0-9]{{4}}{letter}" if letter else "3[0-9]{4}[RLD]"
    dates = (f'  FILTER(?date >= "{date_from}"^^xsd:date)\n' if date_from else "") + (
        f'  FILTER(?date <= "{date_to}"^^xsd:date)\n' if date_to else "")
    rows = sparql(CDM + f"""SELECT DISTINCT ?celex ?title ?date WHERE {{
  ?work cdm:resource_legal_id_celex ?celex . FILTER(REGEX(STR(?celex), "^{sector}"))
  ?expr cdm:expression_belongs_to_work ?work ; cdm:expression_uses_language <{LANGUAGE_AUTHORITY}{lang}> ;
        cdm:expression_title ?title .
  OPTIONAL {{ ?work cdm:work_date_document ?date . }}
{filters}{dates}}} LIMIT {limit * 3}""")
    unique = {row["celex"]: row for row in rows}
    return sorted(unique.values(), key=lambda row: row.get("date", ""), reverse=True)[:limit]


def eu_links(celex: str) -> list[str]:
    """The ELI of an act (for regulations, directives and decisions) and its EUR-Lex page."""
    links = []
    match = re.fullmatch(r"3(\d{4})([RLD])(\d{4})", celex)
    if match:
        links.append(f"http://data.europa.eu/eli/{ELI_TYPES[match.group(2)]}/{match.group(1)}/"
                     f"{int(match.group(3))}/oj")
    links.append(f"https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:{celex}")
    return links


# --------------------------------------------------------------------------------------------------------------------
# Piedmont: Arianna, CSI Piemonte and the BURP

ARIANNA_LAW = "https://arianna.cr.piemonte.it/iterlegcoordweb/dettaglioLegge.do?urnLegge="
ARIANNA_REGULATIONS = "http://arianna.consiglioregionale.piemonte.it/regolafo/"
ARIANNA_SEARCH = "http://arianna.consiglioregionale.piemonte.it/iterlegfo/cercaAtti.do"
# CSI Piemonte's service answers over http only; https fails on that host.
CSI_TEXT = "http://serviziweb.csi.it/normacatsrvrest/rest/normacat/testo"
BUR_SEARCH = "http://search.regione.piemonte.it/mrceli/searchrpbur"


def regional_urn(kind: str, issued: str, number: int | str) -> str:
    """A Piedmont NIR URN: kind is legge or regolamento, issued the year or the full date of the act."""
    return f"urn:nir:regione.piemonte:{kind}:{issued};{number}"


def arianna_url(urn: str, date: str | None = None, article: str | None = None) -> str:
    """The Arianna page of a regional act, as in force on date when one is given, at an article when one is."""
    base = ARIANNA_LAW if ":legge:" in urn else ARIANNA_REGULATIONS + "dettaglioRegolamento.do?urnRegolamento="
    return base + urn + (f"@{date}" if date else "") + (f"#art{article}" if article else "")


def parse_arianna(page: str) -> dict:
    """An Arianna act page as its heading, its versions and its articles.

    Versions come from the page's datiTimeline script: each with its label (V0, V1...), its validity note
    ("dal 24/08/2007 al 28/03/2012"), whether it is the one shown, and its URN. Articles are the blocks after each
    `<a id="artN">` anchor, up to the coordinated notes; a structural heading (Titolo, Capo, Sezione) that closes a
    block belongs to the next article and is cut. A page may repeat an article's anchor for a heading, so each
    article is kept once, with its text. The note markers in an article ("[19]") are replaced by the notes they
    point to, which record each amendment ("L'articolo 23 è stato sostituito dal comma 1...").
    """
    lead = re.search(r'<span class="lead">(.*?)(?:&nbsp;|\(|</span>)', page, re.S)
    versions = []
    for block in re.findall(r"times:\s*\[\s*\{(.*?)\}\s*\]", page, re.S):
        fields = dict(re.findall(r'"(\w+)"\s*:\s*"([^"]*)"', block))
        versions.append({"label": fields.get("label", ""), "validity": fields.get("nota", ""),
                         "shown": fields.get("selezionato") == "true",
                         "urn": fields.get("urn", "").split("urnLegge=")[-1].split("urnRegolamento=")[-1]})
    body, _, notes_html = page.partition('<div class="notecoordinate">')
    notes = {key: join_paragraphs(html_to_text(text))
             for key, text in re.findall(r'<span id="(ndr\w+)">(.*?)</span>\s*</p>', notes_html, re.S)}
    anchors = list(re.finditer(r'<a id="art([0-9a-z]+)" name="art\1"></a>', body))
    articles: dict[str, dict] = {}
    for i, anchor in enumerate(anchors):
        chunk = body[anchor.end(): anchors[i + 1].start() if i + 1 < len(anchors) else len(body)]
        heading = re.search(r'<div class="num">\s*(Titolo|Capo|Sezione|Parte)\b', chunk)
        if heading:
            chunk = chunk[:heading.start()]
        markers = re.findall(r'<sup><a class="rifnota" href="#(ndr\w+)">\[(\d+)\]</a>', chunk)
        chunk = re.sub(r"<sup>.*?</sup>", "", chunk, flags=re.S)
        # Keep a paragraph's number on the line of its text: "1. La presente legge...".
        chunk = re.sub(r'</div>\s*<div class="(corpo|rubrica)">', " ", chunk)
        text = join_paragraphs(html_to_text(chunk))
        if text or anchor.group(1) not in articles:
            articles.setdefault(anchor.group(1), {"id": anchor.group(1), "text": "", "notes": []})
            if text and not articles[anchor.group(1)]["text"]:
                articles[anchor.group(1)].update(
                    text=text, notes=[f"[{number}] {notes[key]}" for key, number in markers if key in notes])
    return {"heading": html_to_text(lead.group(1)) if lead else "", "versions": versions,
            "articles": list(articles.values())}


def arianna_regulation_urn(year: int, number: int) -> str:
    """The URN of a Piedmont regulation, which carries its full date, from Arianna's list of that year."""
    body, content_type, _ = http(ARIANNA_REGULATIONS + f"elencoRegolamenti.do?anno={year}")
    for issued, found in re.findall(r"urn:nir:regione\.piemonte:regolamento:(\d{4}-\d{2}-\d{2});(\d+)",
                                    decode(body, content_type)):
        if int(found) == number and issued.startswith(str(year)):
            return regional_urn("regolamento", issued, number)
    raise SourceError(f"Arianna lists no regolamento regionale n. {number} of {year}")


def csi_text(year: int, number: int, regulation: bool = False) -> str:
    """The current consolidated text of a Piedmont law or regulation, as plain text, from CSI Piemonte."""
    query = urllib.parse.urlencode({"anno": year, "numero": number, "tipo": "regolamento" if regulation else "legge"})
    body, content_type, _ = http(f"{CSI_TEXT}?{query}")
    text = decode(body, content_type).strip()
    if len(text) < 40:
        raise SourceError(f"CSI Piemonte has no text for {'regolamento' if regulation else 'legge'} {number}/{year}")
    return text


def parse_arianna_search(page: str) -> list[dict]:
    """The rows of Arianna's search results: URN, act heading, date and title."""
    rows = []
    for cell in page.split('<td class="atto">')[1:]:
        urn = re.search(r"urn:nir:regione\.piemonte:[a-z]+:[\d-]+;\d+", cell)
        if not urn:
            continue
        date = re.search(r"del\s*<strong>([\d/]+)</strong>", cell)
        title = re.search(r"</td>\s*<td>(.*?)</td>", cell, re.S)
        rows.append({"urn": urn.group(0), "date": date.group(1) if date else "",
                     "title": html_to_text(title.group(1)) if title else ""})
    return rows


def arianna_search(words: str, scope: str = "titolo", date: str | None = None) -> list[dict]:
    """Regional laws whose title (scope titolo) or text (scope documento) holds all the words, in force on date.

    The search form keeps its state in a session, so the form page is read first for the cookie.
    """
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    http(ARIANNA_SEARCH, opener=opener)
    fields = {"criteri.tipoAtto": "L", "criteri.ambitoRicerca": scope, "criteri.testoRicerca": words,
              "criteri.tipoRicerca": "1",
              "criteri.dataVigenza": dt.date.fromisoformat(date).strftime("%d-%m-%Y") if date else "",
              "searchBtn": "searchBtn"}
    body, content_type, _ = http(ARIANNA_SEARCH, urllib.parse.urlencode(fields).encode(),
                                 {"Content-Type": "application/x-www-form-urlencoded"}, opener=opener)
    return parse_arianna_search(decode(body, content_type))


def parse_bur_search(page: str) -> list[dict]:
    """The hits of the BURP search: each act page's URL with the text the engine shows for it.

    A hit's text opens with the bulletin it belongs to ("2022 - B.U. n. 48", "2022 - Supp. n. 1 al B.U. n. 03"),
    so whatever precedes that marker (the page header, the previous hit's link) is dropped.
    """
    hits, previous = [], 0
    for link in re.finditer(r'<a class="linkto" href="([^"]+)"', page):
        snippet = " ".join(html_to_text(page[previous:link.start()]).split())
        start = re.search(r"\d{4} - (?:Supp\.|B\.U\.)", snippet)
        snippet = snippet[start.start():] if start else snippet
        snippet = re.sub(r"\s*(Torna al Sommario Indice Sistematico|Testo del documento|Testo)\s*$", "",
                         snippet.replace("Torna al Sommario Indice Sistematico", " "))
        hits.append({"url": link.group(1), "text": " ".join(snippet.split())[:400]})
        previous = link.end()
    return hits


def bur_search(words: str, start: int = 0, limit: int = 10) -> list[dict]:
    """Acts in the BURP matching the words, as the Region's search engine ranks them."""
    query = urllib.parse.urlencode({"collection": "bur", "type": "search", "term_query": words, "start": start,
                                    "end": start + limit, "language": "it", "enc": "utf-8"})
    body, content_type, _ = http(f"{BUR_SEARCH}?{query}")
    return parse_bur_search(decode(body, content_type))


def bur_act(url: str, out_dir: pathlib.Path) -> tuple[str, list[pathlib.Path]]:
    """An act page of the BURP: its text, and its PDFs downloaded into out_dir for Claude to read."""
    body, content_type, final = http(url)
    page = decode(body, content_type)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for href in dict.fromkeys(re.findall(r'href\s*=\s*"([^"]+\.pdf)"', page, re.I)):
        pdf_url = urllib.parse.urljoin(final, href)
        pdf, _, _ = http(pdf_url)
        target = out_dir / pathlib.PurePosixPath(urllib.parse.urlparse(pdf_url).path).name
        target.write_bytes(pdf)
        saved.append(target)
    return html_to_text(page), saved


# --------------------------------------------------------------------------------------------------------------------
# Commands


def show(*lines) -> None:
    """Print the lines, skipping the optional ones that came out None or False; an empty string is a blank line."""
    print("\n".join(line for line in lines if line is not None and line is not False))


def cmd_it_search(args) -> None:
    acts = it_search(args.type, args.year, args.number, args.title, args.text, args.limit)
    if not acts:
        raise SourceError("Normattiva found no act with these filters")
    for act in acts:
        title = (act.get("titoloAtto") or "").strip().strip("[]")
        show(f"{act.get('descrizioneAtto')}: {title}",
             f"  GU n. {act.get('numeroGU')} del {act.get('dataGU')}, codice redazionale {act.get('codiceRedazionale')}",
             f"  {it_link(act)}", "")


def cmd_it_article(args) -> None:
    date = iso_date(args.date)
    if args.code and args.gu_date:
        act = {"codiceRedazionale": args.code, "dataGU": iso_date(args.gu_date)}
    elif args.type and args.year and args.number:
        act = it_find(args.type, args.year, args.number)
    else:
        raise SystemExit("Name the act by --type, --year and --number, or by --code and --gu-date")
    article = parse_article(args.article)
    found = it_article(act, article, date, args.group)
    label = f"art. {article[0]}" + (f"-{article[2]}" if article[2] else "")
    show(f"{act.get('descrizioneAtto', act['codiceRedazionale'])}, {label}",
         f"Version in force on {date}: from {found['from'] or 'not stated'}"
         f"{' to ' + found['to'] if found['to'] else ', no end recorded'}",
         f"Link: {it_link(act, article, date)}", "", found["text"])


def cmd_eu_lookup(args) -> None:
    celex = parse_eu_ref(args.ref)
    meta = eu_metadata(celex, args.lang)
    in_force = {"true": "yes", "1": "yes", "false": "no", "0": "no"}.get(meta.get("inForce", "").lower(),
                                                                           "not recorded in CELLAR")
    consolidations = eu_consolidations(celex)
    end = meta.get("end", "not recorded")
    show(meta["title"], f"CELEX {celex}", f"Date of the act: {meta.get('date', 'not recorded')}",
         f"Entry into force or application: {meta.get('force', 'not recorded')}",
         f"End of validity: {'none (open-ended)' if end.startswith('9999') else end}", f"In force: {in_force}",
         meta.get("transposition") and f"Transposition deadline: {meta['transposition']}",
         *(f"Link: {link}" for link in eu_links(celex)),
         "Consolidated versions: " + (", ".join(consolidations) if consolidations else "none in CELLAR"))


def cmd_eu_text(args) -> None:
    celex = parse_eu_ref(args.ref)
    date = iso_date(args.date)
    shown = celex if args.original else (version_on(eu_consolidations(celex), date) or celex)
    note = ("the act as published in the Official Journal" if shown == celex
            else f"consolidated version {shown}, the one that applies on {date}")
    if shown == celex and not args.original:
        note += f" (no consolidated version dated on or before {date})"
    text = eu_text(shown, args.lang)
    body = ("\n".join(eu_toc(text, args.lang)) if args.toc
            else eu_article(text, args.article, args.lang) if args.article else text)
    show(f"CELEX {celex}: {note}", f"Link: https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:{shown}", "",
         body)


def cmd_eu_transpositions(args) -> None:
    celex = parse_eu_ref(args.ref)
    rows = eu_transpositions(celex, args.country)
    show(f"National measures notified by {args.country} for {celex}: {len(rows)}",
         f"Link: https://eur-lex.europa.eu/legal-content/IT/NIM/?uri=CELEX:{celex}", "",
         *(f"{row.get('date', '')}  {row.get('title', '(no title)')}  [{row['celex']}]" for row in rows))


def cmd_eu_search(args) -> None:
    rows = eu_search(args.words, args.type, args.lang, args.date_from, args.date_to, args.limit)
    if not rows:
        raise SourceError("CELLAR found no act with all these words in its title")
    for row in rows:
        show(f"{row.get('date', '')}  {row['celex']}  {row['title']}")


def cmd_pie_law(args) -> None:
    date = args.date and iso_date(args.date)
    regulation = args.regulation
    urn = (arianna_regulation_urn(args.year, args.number) if regulation
           else regional_urn("legge", args.year, args.number))
    kind = "Regolamento regionale" if regulation else "Legge regionale"
    try:
        body, content_type, _ = http(arianna_url(urn, date))
        act = parse_arianna(decode(body, content_type))
        if not act["articles"]:
            raise SourceError(f"Arianna shows no articles for {urn}")
    except SourceError as error:
        if date or args.article:
            raise
        # The current text is also at CSI Piemonte, as plain text, without versions or article anchors.
        show(f"{kind} n. {args.number} of {args.year}: Arianna failed ({error}); current text from CSI Piemonte",
             f"Link: {arianna_url(urn)}", "", csi_text(args.year, args.number, regulation))
        return
    shown = next((v for v in act["versions"] if v["shown"]), None)
    lines = [act["heading"] or f"{kind} n. {args.number} of {args.year}",
             f"Version shown: {shown['label']}, {shown['validity']}" if shown else "Version shown: the only one",
             f"Link: {arianna_url(urn, date, args.article)}"]
    if args.versions or not (args.article or args.toc):
        lines.append("Versions: " + "; ".join(f"{v['label']} {v['validity']}" for v in act["versions"]))
    def with_notes(article):  # an article's text followed by the amendment notes its markers point to
        return article["text"] + ("\n\nNotes:\n" + "\n".join(article["notes"]) if article["notes"] else "")

    if args.toc:
        body = "\n".join((a["text"].splitlines() or [f"art{a['id']}: no text in this version"])[0]
                         for a in act["articles"])
    elif args.article:
        found = next((a for a in act["articles"] if a["id"] == args.article.lower().replace("-", "")), None)
        if found is None:
            raise SourceError(f"No article {args.article} in this version of {urn}")
        body = with_notes(found)
    else:
        body = "\n\n".join(with_notes(a) for a in act["articles"])
    show(*lines, "", body)


def cmd_pie_search(args) -> None:
    rows = arianna_search(args.words, "documento" if args.within == "text" else "titolo",
                          args.date and iso_date(args.date))
    if not rows:
        raise SourceError("Arianna found no regional law matching these words")
    for row in rows:
        show(f"{row['urn']}  del {row['date']}  {row['title']}", f"  {arianna_url(row['urn'])}")


def cmd_bur_search(args) -> None:
    hits = bur_search(args.words, args.start, args.limit)
    if not hits:
        raise SourceError("The BURP search found nothing for these words")
    for hit in hits:
        show(hit["text"], f"  {hit['url']}", "")


def cmd_bur_act(args) -> None:
    out = pathlib.Path(args.out) if args.out else pathlib.Path(tempfile.gettempdir()) / "aldogor-legislation"
    text, saved = bur_act(args.url, out)
    pdfs = [f"PDF saved: {path}" for path in saved] or ["No PDF linked from this page"]
    show(f"Page: {args.url}", *pdfs, "", text)


def cmd_smoke(args) -> None:
    """Live check: one real request to each source, compared with a known answer."""
    checks = [
        ("Normattiva search", lambda: it_find("DLGS", 2003, "196")["codiceRedazionale"] == "003G0218"),
        ("Normattiva article", lambda: "2-septies" in it_article(
            it_find("DLGS", 2003, "196"), parse_article("2-septies"), dt.date.today().isoformat())["text"]),
        ("EUR-Lex metadata", lambda: "2016/679" in eu_metadata("32016R0679")["title"]),
        ("EUR-Lex consolidations", lambda: "02016R0679-20160504" in eu_consolidations("32016R0679")),
        ("EUR-Lex text", lambda: "Articolo 9" in eu_text("32016R0679")),
        ("Arianna law at a date", lambda: any(v["shown"] and v["label"] == "V0" for v in parse_arianna(decode(
            *http(arianna_url(regional_urn("legge", 2007, 18), "2010-01-01"))[:2]))["versions"])),
        ("Arianna search", lambda: any(r["urn"].endswith("2007;18") for r in arianna_search("socio-sanitaria"))),
        ("CSI text", lambda: "programmazione socio-sanitaria" in csi_text(2007, 18)),
        ("BURP search", lambda: bool(bur_search("piano regionale della prevenzione", limit=3))),
    ]
    failed = 0
    for name, check in checks:
        try:
            ok = check()
            reason = "" if ok else "unexpected answer"
        except (SourceError, KeyError, ValueError, json.JSONDecodeError) as error:
            ok, reason = False, str(error)[:200]
        failed += not ok
        print(f"{'OK  ' if ok else 'FAIL'}  {name}{'  ' + reason if reason else ''}")
    if failed:
        raise SourceError(f"{failed} of {len(checks)} live checks failed")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)

    def add(name, function, help_text):
        sub = commands.add_parser(name, help=help_text, description=help_text)
        sub.set_defaults(run=function)
        return sub

    sub = add("it-search", cmd_it_search, "Search Italian state acts on Normattiva")
    sub.add_argument("--type", help="L, DLGS, DL, DPR, DPCM, RD, DM, COST, or Normattiva's full label")
    sub.add_argument("--year", type=int)
    sub.add_argument("--number")
    sub.add_argument("--title", help="words in the title")
    sub.add_argument("--text", help="words in the text")
    sub.add_argument("--limit", type=int, default=10)

    sub = add("it-article", cmd_it_article, "One article of a state act as in force on a date (Normattiva)")
    sub.add_argument("--type")
    sub.add_argument("--year", type=int)
    sub.add_argument("--number")
    sub.add_argument("--code", help="codice redazionale, from it-search, when type, year and number are ambiguous")
    sub.add_argument("--gu-date", help="Gazzetta Ufficiale date that goes with --code")
    sub.add_argument("--article", required=True, help="e.g. 13, 2-bis, 2-septies")
    sub.add_argument("--date", help="in-force date, YYYY-MM-DD (default today)")
    sub.add_argument("--group", type=int, default=0, help="idGruppo, for structured codes that need it")

    sub = add("eu-lookup", cmd_eu_lookup, "Identify an EU act: CELEX, title, dates, in force, consolidations")
    sub.add_argument("ref", help="CELEX, ELI, or a citation such as 'Regolamento (UE) 2016/679'")
    sub.add_argument("--lang", default="ITA", choices=sorted(LANGUAGES))

    sub = add("eu-text", cmd_eu_text, "Text of an EU act, consolidated as on a date, or one article of it")
    sub.add_argument("ref")
    sub.add_argument("--article", help="article number, e.g. 9")
    sub.add_argument("--date", help="the consolidated version applying on this date (default today)")
    sub.add_argument("--original", action="store_true", help="the act as published, not consolidated")
    sub.add_argument("--toc", action="store_true", help="list the articles only")
    sub.add_argument("--lang", default="ITA", choices=sorted(LANGUAGES))

    sub = add("eu-transpositions", cmd_eu_transpositions, "National measures transposing a directive")
    sub.add_argument("ref")
    sub.add_argument("--country", default="ITA", help="three-letter code (default ITA)")

    sub = add("eu-search", cmd_eu_search, "EU acts whose title contains all the words")
    sub.add_argument("words")
    sub.add_argument("--type", help="REG, DIR or DEC")
    sub.add_argument("--lang", default="ITA", choices=sorted(LANGUAGES))
    sub.add_argument("--date-from")
    sub.add_argument("--date-to")
    sub.add_argument("--limit", type=int, default=15)

    sub = add("pie-law", cmd_pie_law, "A Piedmont regional law or regulation as in force on a date (Arianna)")
    sub.add_argument("--year", type=int, required=True)
    sub.add_argument("--number", type=int, required=True)
    sub.add_argument("--regulation", action="store_true", help="a regolamento regionale, not a law")
    sub.add_argument("--date", help="in-force date, YYYY-MM-DD (default: the current version)")
    sub.add_argument("--article", help="article number, e.g. 3 or 3bis")
    sub.add_argument("--toc", action="store_true", help="list the articles only")
    sub.add_argument("--versions", action="store_true", help="list the versions also with --article or --toc")

    sub = add("pie-search", cmd_pie_search, "Search Piedmont regional laws on Arianna")
    sub.add_argument("words")
    sub.add_argument("--in", dest="within", choices=("title", "text"), default="title")
    sub.add_argument("--date", help="laws in force on this date")

    sub = add("bur-search", cmd_bur_search, "Search the Bollettino Ufficiale della Regione Piemonte")
    sub.add_argument("words")
    sub.add_argument("--start", type=int, default=0)
    sub.add_argument("--limit", type=int, default=10)

    sub = add("bur-act", cmd_bur_act, "Read a BURP act page and download its PDFs")
    sub.add_argument("url")
    sub.add_argument("--out", help="folder for the PDFs (default: the system's temp folder)")

    add("smoke", cmd_smoke, "Live check of every source")
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        args.run(args)
    except SourceError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except SystemExit as error:
        if isinstance(error.code, str):
            print(error.code, file=sys.stderr)
            return 2
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
