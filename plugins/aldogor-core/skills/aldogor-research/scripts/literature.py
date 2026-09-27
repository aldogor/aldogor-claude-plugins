#!/usr/bin/env python3
"""A project's literature library: add works, retrieve their text, keep the record consistent.

The library is one flat folder of the project, literature/ at the root (docs/literature/ where a development
repository keeps its research side in docs/), holding
    bibliography.csv   the master record, tracked by git: one row per cited item, UTF-8 with BOM, sorted by
                       first author
    <key>.pdf          the full text of a work, when a legal copy was obtained (local, ignored by git)
    <key>.md           the text of a work for reading and searching (local, ignored by git); its YAML header
                       says (text_source) whether it holds the full text, the abstract only or the metadata only
The key is the name of both files and the work's citation key. A new library uses Surname_Year keys
(Iyamu_2021, DelReyPuech_2026, WHO_2025; a second work of the same author and year gets b, then c); a library
whose keys are mostly citation keys in the form author, year, first title word (alonzo2021interplay) keeps
that form for the works it adds. The files are rebuilt from the CSV with fetch, collect and md, so a clone
that has only the CSV can get its open-access texts back.

Subcommands (run from anywhere inside the project: the library is the literature/ or docs/literature/ folder
holding bibliography.csv, found from the working directory up to the repository root, or given with --lib)
    add DOI [--key K] [--title T] [--cited-in T] [--note T] [--pdf PATH]
                        add a work: metadata from Crossref, abstract, legal open-access full text,
                        Markdown, new row in the CSV. In a project without a library, the first add creates
                        literature/ at the repository root and the .gitignore lines that keep its files local
    fetch [KEY ...]     try the legal open-access sources again for works whose full text is not in the
                        folder (in a fresh clone, every work with a DOI)
    collect [--from DIR]
                        file the PDFs downloaded by hand (default: the Downloads folder) under their keys
    md [KEY ...] [--force]
                        write <key>.md again from <key>.pdf, or from the abstract, or from the metadata
    check               consistency report between the CSV and the files; exit code 1 on problems
    bib [--out PATH]    BibTeX of the whole library with the same keys (printed unless --out is given), for
                        pandoc and LaTeX
A work without a DOI (a report, a web page) is added as a row written by hand, with its url; md then writes
its Markdown from a PDF placed in the library as <key>.pdf.

Retrieval rules:
  - only legal free copies are fetched: the PMC open-access set, Europe PMC, the publisher and repository
    copies that OpenAlex and Semantic Scholar list as open, and a local archive folder given with --archive;
  - never through an institutional login: requests carry no credentials and no cookies of the user, and the
    hosts of library proxies and login services are refused;
  - never a scripted download from ScienceDirect or Wiley: their hosts are refused, also as redirect targets;
  - a page that answers with an anti-bot check (Cloudflare, Anubis, AWS WAF, captcha, the checks PMC applies)
    is not pursued: the attempt is reported and the copy is left to the user's own browser, from which
    collect files it;
  - an honest User-Agent, at most one request per second per host (one every three seconds for
    Semantic Scholar), one retry after a 429 or 5xx answer;
  - a PDF is kept only if the work's title is printed on its first pages.

Requirements: Python 3.10 or later on Windows, macOS or Linux, and the packages requests, lxml, pymupdf and
pymupdf4llm (`python -m pip install requests lxml pymupdf pymupdf4llm`); markitdown only to convert an article
web page saved from the browser (collect). Adapted from the library script of stilme-qe-app (199fb2a).
"""
import argparse
import csv
import glob
import html
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import urllib.parse

try:
    import pymupdf
    import requests
    from lxml import etree
except ImportError as _missing:       # a clear message instead of a traceback on a machine without them
    sys.exit(f'literature.py needs {_missing.name}: python -m pip install requests lxml pymupdf pymupdf4llm')

# ====================================================================== paths
# The library folder and the optional local archive are set by main() from --lib and --archive, or found
# from the working directory; tests set them directly.
LIT = None
ARCHIVE = None
CSV_NAME = 'bibliography.csv'
DOWNLOADS = os.path.join(os.path.expanduser('~'), 'Downloads')

# Columns of bibliography.csv, in their order in the file. authors_full holds every author as
# "Family, Given" separated by "; " (from Crossref); it feeds the BibTeX export and new Markdown headers.
COLUMNS = ['key', 'authors', 'year', 'title', 'source', 'kind', 'abstract_or_summary', 'text_type',
           'text_source', 'cited_in', 'full_text', 'access', 'doi', 'url', 'md', 'pdf', 'volume', 'issue',
           'pages', 'pmid', 'pmcid', 'license', 'update_notice', 'authors_full']

# Crossref work types as they are written in the kind column.
KIND = {'journal-article': 'journal article', 'book': 'book', 'monograph': 'book', 'edited-book': 'book',
        'book-chapter': 'book chapter', 'proceedings-article': 'conference paper', 'report': 'report',
        'posted-content': 'preprint', 'dataset': 'dataset', 'reference-entry': 'reference entry'}
# OpenAlex open-access statuses meaning that a free copy exists somewhere.
OPEN = {'gold', 'hybrid', 'bronze', 'green', 'diamond'}


# ====================================================================== the CSV (master record)
def read_rows(path=None):
    """Read bibliography.csv. Returns (column names in file order, list of rows as dicts of strings)."""
    path = path or os.path.join(LIT, CSV_NAME)
    with open(path, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def sort_key(row):
    """Row order of the CSV: first author (ASCII-folded, lower case), then year, then key."""
    return fold(row.get('authors')), row.get('year') or '', row.get('key') or ''


def write_rows(rows, fields, path=None):
    """Write bibliography.csv: UTF-8 with BOM, columns in the order read (any column of COLUMNS missing
    from the file is appended), rows sorted by sort_key. Written to a temporary file and then renamed,
    so an interruption never leaves a half-written CSV."""
    path = path or os.path.join(LIT, CSV_NAME)
    fields = list(fields) + [c for c in COLUMNS if c not in fields]
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, restval='')
        writer.writeheader()
        writer.writerows(sorted(rows, key=sort_key))
    os.replace(tmp, path)


def normalise_license(s):
    """One spelling per Creative Commons licence ('cc-by', 'cc by', 'CC BY' all become 'CC BY';
    'cc by-nc-nd' becomes 'CC BY-NC-ND'). Any other value (TDM, public-domain, other-oa) is kept as is."""
    t = (s or '').strip()
    m = re.fullmatch(r'cc[-\s]?(by(?:[-\s](?:nc|nd|sa))*)', t, re.I)
    return 'CC ' + re.sub(r'\s', '-', m.group(1)).upper() if m else t


# ====================================================================== text helpers
DOI_RE = re.compile(r'10\.\d{4,9}/[^\s"<>\]]+', re.I)


def clean_doi(d):
    """Normalise a DOI: lower case, no URL or 'doi:' prefix, no trailing punctuation or page suffix.
    Returns None when the string is not a DOI."""
    if not d:
        return None
    d = d.strip()
    d = re.sub(r'^(https?://)?(dx\.)?doi\.org/', '', d, flags=re.I)
    d = re.sub(r'^doi:\s*', '', d, flags=re.I)
    d = d.rstrip('.,;:)]}>\'"')
    d = re.sub(r'/(full|abstract|pdf|epdf|fulltext|html)$', '', d, flags=re.I)   # publisher page suffixes
    return d.lower() if d.startswith('10.') else None


def find_doi(text):
    """The first DOI written in a text (for example on the first page of a PDF), normalised."""
    m = DOI_RE.search(text or '')
    return clean_doi(m.group(0)) if m else None


def fold(s):
    """ASCII-fold and lower-case a string (for keys and fuzzy matching): 'Plöderl' becomes 'ploderl'."""
    s = unicodedata.normalize('NFKD', s or '')
    return ''.join(c for c in s if not unicodedata.combining(c)).lower()


def tokens(s):
    """Word tokens for matching. Hyphens are removed (meta-analysis = metaanalysis), British -our
    becomes -or (behaviour = behavior) and a final plural s is dropped, on both sides alike."""
    out = []
    for t in re.findall(r'[a-z0-9]+', re.sub('[-‐‑]', '', fold(s))):
        if len(t) > 4:
            t = t.replace('our', 'or')
        if len(t) > 3 and t.endswith('s') and not t.endswith('ss'):
            t = t[:-1]
        if len(t) > 1:
            out.append(t)
    return out


def containment(title, text):
    """Share of the title's tokens that appear in text (0 to 1)."""
    t = tokens(title)
    if not t:
        return 0.0
    bag = set(tokens(text))
    return sum(1 for w in t if w in bag) / len(t)


def pair_containment(title, text):
    """Share of the title's consecutive word pairs that appear in text (0 to 1). Stricter than
    containment(): a different paper built from the same words fails it."""
    t, x = tokens(title), tokens(text)
    tb = set(zip(t, t[1:]))
    if not tb:
        return 0.0
    return len(tb & set(zip(x, x[1:]))) / len(tb)


def pairs_found(title, text):
    """Share of the title's consecutive word pairs found in a page text, with words split at line-end
    hyphens joined again. Used to recognise a PDF downloaded by hand."""
    tt = [w for w in re.findall(r'[a-z0-9]+', fold(title)) if len(w) > 1]
    xt = re.findall(r'[a-z0-9]+', fold(text.replace('-\n', '')))
    tb = set(zip(tt, tt[1:]))
    return len(tb & set(zip(xt, xt[1:]))) / len(tb) if tb else 0.0


def title_ok(main, text, full, min_c):
    """The cited text must contain the full title (title and subtitle), or the main title alone when
    that has at least three words (citations often drop the subtitle)."""
    if full and len(tokens(full)) >= 2 and containment(full, text) >= min_c:
        return True
    return len(tokens(main)) >= 3 and containment(main, text) >= min_c


def title_accepted(meta, cited_title):
    """The title check applied when the library was built to a DOI written in a citation: the DOI is
    accepted if its registered title matches the title as cited (token containment of at least 0.7),
    or if a short main title of two words or more ('The PHQ-9') is contained in full."""
    main = title_of(meta)
    return (title_ok(main, cited_title, full_title(meta), 0.7)
            or (len(tokens(main)) >= 2 and containment(main, cited_title) == 1.0))


def ws(s):
    """Collapse runs of whitespace into single spaces."""
    return re.sub(r'\s+', ' ', s or '')


def u(s):
    """Unescape HTML entities in a metadata string (Crossref titles may carry &amp; and similar)."""
    return html.unescape(s or '').strip()


# ====================================================================== network
# An honest User-Agent: some open-access hosts refuse the python-requests default.
UA = {'User-Agent': 'Mozilla/5.0 (compatible; aldogor-literature/1.0; research library build)'}

# Hosts that are never requested by this script, also when a redirect points to them.
# ScienceDirect and Wiley protect themselves against systematic downloading: their papers are
# downloaded by hand in the browser. linkinghub.elsevier.com is the Elsevier resolver in front of
# ScienceDirect. wiley.com covers onlinelibrary.wiley.com and the journals of societies hosted there.
REFUSED_HOSTS = ('sciencedirect.com', 'sciencedirectassets.com', 'linkinghub.elsevier.com', 'wiley.com')
# Library proxies and login services: an institutional login is never used by a script.
LOGIN_MARKERS = ('idm.oclc.org', 'ezproxy', 'shibboleth', 'wayf', 'openathens', 'login.unito.it', 'idp.unito.it')


def refused(url):
    """True if the URL points to a host this script must not request."""
    host = (urllib.parse.urlparse(url or '').hostname or '').lower()
    return (any(host == h or host.endswith('.' + h) for h in REFUSED_HOSTS)
            or any(m in host for m in LOGIN_MARKERS))


class RefusedHost(Exception):
    """Raised when a request, or one of its redirects, would reach a refused host."""


class Throttle:
    """At most one call per `gap` seconds per endpoint name."""

    def __init__(self, gap=1.0):
        self.gap, self.last = gap, {}

    def wait(self, name):
        dt = time.time() - self.last.get(name, 0)
        if dt < self.gap:
            time.sleep(self.gap - dt)
        self.last[name] = time.time()


T = Throttle(1.0)       # every host: one request per second
T_S2 = Throttle(3.0)    # Semantic Scholar asks clients without a key to go slower
T_S3 = Throttle(0.2)    # listing and metadata of the PMC open-data bucket on AWS


def _get_following(url, headers, timeout, allow_redirects, **kw):
    """GET that follows redirects one hop at a time, so that no request ever reaches a refused host.
    A fresh session per call: cookies set along the redirect chain are kept, none of the user's are sent."""
    with requests.Session() as s:
        r = None
        for _ in range(10):
            if refused(url):
                raise RefusedHost(urllib.parse.urlparse(url).netloc)
            r = s.get(url, headers=headers, timeout=timeout, allow_redirects=False, **kw)
            if not (allow_redirects and r.is_redirect):
                return r
            url = urllib.parse.urljoin(r.url, r.headers['location'])
        return r


def get(url, name, throttle, timeout=40, allow_redirects=True, **kw):
    """GET with throttling and one retry on 429 or 5xx. Returns a Response, or None on failure or when
    the URL (or a redirect) points to a refused host."""
    headers = kw.pop('headers', UA)
    r = None
    for attempt in range(2):
        throttle.wait(name)
        try:
            r = _get_following(url, headers, timeout, allow_redirects, **kw)
        except RefusedHost as e:
            print(f'    not requested: {e} (ScienceDirect, Wiley or an institutional login)')
            return None
        except requests.RequestException:
            r = None
        if r is not None and r.status_code not in (429, 500, 502, 503, 504):
            return r
        time.sleep(5 * (attempt + 1))
    return r


# Phrases of the anti-bot pages met while building the library: Cloudflare ('just a moment', cf-chl,
# challenge-platform), Anubis ('oh noes'), captchas, and the JavaScript checks PMC and others apply.
CHALLENGE = ('just a moment', 'cf-chl', 'challenge-platform', 'anubis', 'oh noes', 'captcha',
             'are you a robot', 'making sure you', 'enable javascript and cookies')


def challenged(r):
    """True if the response is an anti-bot check rather than content."""
    if r is None:
        return False
    if r.status_code == 202 and not r.content:                       # AWS WAF challenge
        return True
    if 'html' in (r.headers.get('content-type') or ''):
        t = r.text[:5000].lower()
        return any(s in t for s in CHALLENGE)
    return False


def download(url, name=None, throttle=T):
    """(content, status) of a URL; content is None when the host is refused, when the answer is an
    anti-bot check ('bot protection') or when the request fails (status code or 'error')."""
    if refused(url):
        return None, 'not scripted (ScienceDirect, Wiley or institutional login)'
    r = get(url, name or urllib.parse.urlparse(url).netloc, throttle, timeout=90, allow_redirects=True)
    if challenged(r):
        return None, 'bot protection'
    if r is None or not r.ok:
        return None, (r.status_code if r is not None else 'error')
    return r.content, r.status_code


# ====================================================================== metadata
_CROSSREF = {}      # doi -> Crossref message (or None), for the duration of one run


def crossref(doi):
    """The Crossref record of a DOI, or None when Crossref does not know it."""
    if doi not in _CROSSREF:
        r = get('https://api.crossref.org/works/' + urllib.parse.quote(doi, safe='/'), 'crossref', T)
        _CROSSREF[doi] = r.json()['message'] if (r is not None and r.status_code == 200) else None
    return _CROSSREF[doi]


_EPMC = {}          # doi -> Europe PMC core record ({} when not found)


def europepmc(doi):
    """The Europe PMC core record of a DOI (PMID, PMCID, licence, abstract), or {}."""
    if doi not in _EPMC:
        q = urllib.parse.quote(f'DOI:"{doi}"')
        r = get(f'https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={q}&resultType=core&format=json',
                'epmc', T)
        res = []
        if r is not None and r.ok and 'errCode' not in r.text:
            res = r.json().get('resultList', {}).get('result', [])
        _EPMC[doi] = res[0] if res else {}
    return _EPMC[doi]


def epmc_meta(doi):
    """Crossref-shaped metadata from Europe PMC, for DOIs registered outside Crossref."""
    x = europepmc(doi)
    if not x:
        return None
    authors = [{'family': a.get('lastName') or a.get('collectiveName', ''), 'given': a.get('firstName', '')}
               for a in (x.get('authorList') or {}).get('author', [])]
    ji = x.get('journalInfo') or {}
    return {'DOI': doi, 'title': [re.sub(r'\.$', '', x.get('title') or '')], 'author': authors,
            'container-title': [(ji.get('journal') or {}).get('title', '')],
            'issued': {'date-parts': [[int(x['pubYear'])]]} if x.get('pubYear') else None,
            'volume': ji.get('volume'), 'issue': ji.get('issue'), 'page': x.get('pageInfo'),
            'type': 'journal-article', 'source': 'europepmc'}


def title_of(meta):
    """Main title of a Crossref record."""
    return (meta.get('title') or [''])[0]


def full_title(meta):
    """Title and subtitle of a Crossref record."""
    sub = meta.get('subtitle') or ['']
    return title_of(meta) + ((': ' + sub[0]) if sub and sub[0] else '')


def year_of(meta):
    try:
        return str(meta['issued']['date-parts'][0][0])
    except (KeyError, TypeError, IndexError):
        return ''


# Words skipped when the key takes the first significant word of the title (English and Italian).
STOP = set('a an the of in on and for to with from by at as is are its their between among during '
           'il lo la le gli i un una di da del della dei delle per con su tra fra e ed'.split())


def make_citekey(meta, taken):
    """Citation-key rule: first author's family name + year + first significant title word,
    ASCII-folded, at most 40 characters (luo2021determination). Without an author the editor, then the
    publisher, stands in; without a year 'nd'. A key already taken gets a letter: b, c, and so on."""
    au = (meta.get('author') or meta.get('editor') or [{}])[0]
    fam = au.get('family') or au.get('name') or (meta.get('publisher') or 'anon')
    fam = re.sub(r'[^a-z]', '', fold(fam.split()[-1] if ' ' in fam and not au.get('family') else fam)) or 'anon'
    yr = year_of(meta) or 'nd'
    words = [w for w in re.findall(r'[a-z0-9]+', fold(title_of(meta))) if w not in STOP]
    base = f'{fam}{yr}{words[0] if words else ""}'[:40]
    key, n = base, 1
    while key in taken:
        n += 1
        key = f'{base}{chr(ord("a") + n - 1)}'
    return key


def fold_keep_case(s):
    """ASCII-fold a string keeping its case: 'Plöderl' becomes 'Ploderl'."""
    s = unicodedata.normalize('NFKD', s or '')
    return ''.join(c for c in s if not unicodedata.combining(c))


def key_name(meta):
    """The name part of a Surname_Year key. A person: the family name with its words joined and each
    capitalised, hyphens kept (Del Rey Puech -> DelReyPuech, Abi-Jaoude, O'Brien -> OBrien). An organisation
    as author, or the publisher when there is no author: the initials of its significant words when it has
    two or more (World Health Organization -> WHO), else the single word."""
    au = (meta.get('author') or meta.get('editor') or [{}])[0]
    fam = au.get('family')
    if fam:
        parts = re.split(r"[\s'’]+", re.sub(r"[^A-Za-z\s'’-]", '', fold_keep_case(fam)))
        return ''.join(p[:1].upper() + p[1:] for p in parts if p) or 'Anon'
    name = fold_keep_case(au.get('name') or u(meta.get('publisher')) or 'Anon')
    words = [w for w in re.findall(r'[A-Za-z]+', name) if w.lower() not in STOP]
    if len(words) >= 2:
        return ''.join(w[0].upper() for w in words)
    return words[0][:1].upper() + words[0][1:] if words else 'Anon'


def make_surname_year(meta, taken):
    """Surname_Year key (Iyamu_2021; without a year, Iyamu_nd). A key already taken gets a letter: b, c."""
    base = f'{key_name(meta)}_{year_of(meta) or "nd"}'
    key, n = base, 1
    while key in taken:
        n += 1
        key = f'{base}{chr(ord("a") + n - 1)}'
    return key


SURNAME_YEAR = re.compile(r'^[A-Z][A-Za-z-]*_(\d{4}|nd)[a-z]?$')


def key_style(rows):
    """The key form of a library: 'surname_year' when it is empty or when at least half of its keys have
    that form, otherwise 'citekey'. The keys already in the library are never renamed."""
    keys = [r.get('key') or '' for r in rows if r.get('key')]
    if not keys or 2 * sum(bool(SURNAME_YEAR.match(k)) for k in keys) >= len(keys):
        return 'surname_year'
    return 'citekey'


def make_key(meta, taken, style='surname_year'):
    """A new key in the library's form (see key_style)."""
    return make_citekey(meta, taken) if style == 'citekey' else make_surname_year(meta, taken)


def authors_short(meta, n=3):
    """The authors column: 'Family Initials' of the first three authors, then 'et al.'; the publisher
    when there is no author."""
    names = []
    for a in meta.get('author') or []:
        fam = a.get('family') or a.get('name') or ''
        ini = ''.join(p[0] for p in re.split(r'[\s\-.]+', a.get('given') or '') if p)
        names.append((fam + ' ' + ini).strip())
    if not names:
        return u(meta.get('publisher'))
    return ', '.join(names[:n]) + (', et al.' if len(names) > n else '')


def authors_full(meta):
    """The authors_full column: every author as 'Family, Given' (or the single name Crossref has),
    separated by '; '."""
    out = []
    for a in meta.get('author') or []:
        fam, given, name = (ws(a.get(k)).strip() for k in ('family', 'given', 'name'))
        out.append(f'{fam}, {given}' if fam and given else (fam or name))
    return '; '.join(x for x in out if x)


def retraction(meta):
    """Kinds of update notice Crossref records for a work (correction, erratum, retraction)."""
    kinds = [x.get('type') for x in (meta.get('updated-by') or [])]
    return ', '.join(sorted(set(k for k in kinds if k)))


def row_from_meta(key, doi, meta):
    """A new CSV row for a work with a DOI, filled from its Crossref (or Europe PMC) record."""
    row = {c: '' for c in COLUMNS}
    row.update(key=key, authors=authors_short(meta), year=year_of(meta), title=u(title_of(meta)),
               source=u((meta.get('container-title') or [''])[0]) or u(meta.get('publisher')),
               kind=KIND.get(meta.get('type'), meta.get('type') or ''), full_text='no', doi=doi,
               url=f'https://doi.org/{doi}', volume=str(meta.get('volume') or ''),
               issue=str(meta.get('issue') or ''), pages=str(meta.get('page') or ''),
               update_notice=retraction(meta), authors_full=authors_full(meta))
    return row


def first_family(row):
    """Family name of the first author of a row (for matching other versions of the work)."""
    first = (row.get('authors_full') or '').split('; ')[0]
    return first.split(', ')[0] if first else ''


# ====================================================================== abstracts
PARSER = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, recover=True)


def clean_abstract(s):
    """Plain text of an abstract: markup removed, whitespace collapsed, a leading 'Abstract' dropped."""
    s = re.sub(r'<[^>]+>', ' ', s or '')
    s = re.sub(r'\s+', ' ', s).strip()
    return re.sub(r'^(Abstract|ABSTRACT|Summary)[:.]?\s+', '', s)


def jats_abstract(content):
    """Plain-text abstract from JATS XML (bytes), keeping the headings of a structured abstract."""
    root = etree.fromstring(content, PARSER)
    for ab in root.iter('{*}abstract', 'abstract'):
        if ab.get('abstract-type') not in (None, 'abstract', 'structured'):
            continue
        secs = [s for s in ab if etree.QName(s).localname == 'sec']
        if secs:
            parts = []
            for s in secs:
                title = ''.join(s.findtext('{*}title') or s.findtext('title') or '').strip()
                body = ' '.join(''.join(p.itertext()) for p in s if etree.QName(p).localname == 'p')
                parts.append((title + ': ' if title else '') + clean_abstract(body))
            return ' '.join(parts)
        return clean_abstract(' '.join(''.join(p.itertext()) for p in ab if etree.QName(p).localname == 'p')
                              or ''.join(ab.itertext()))
    return None


def crossref_abstract(doi):
    """The abstract deposited with Crossref, JATS markup stripped."""
    msg = crossref(doi) or {}
    return clean_abstract(msg.get('abstract')) or None


def s2_abstract(doi):
    """The abstract on Semantic Scholar (some publishers withhold it there)."""
    r = get(f'https://api.semanticscholar.org/graph/v1/paper/DOI:{urllib.parse.quote(doi, safe="/")}?fields=abstract',
            's2', T_S2)
    if r is None or not r.ok:
        return None
    return clean_abstract(r.json().get('abstract')) or None


def abstract_from_markdown(text):
    """The abstract paragraph of a full-text Markdown (from a PDF or a saved web page): the text after an
    'Abstract' marker, up to the keywords or the introduction. None for abstract-only files."""
    if 'text_source: "full text' not in (text or '')[:1500]:
        return None
    t = text.split('---', 2)[-1]
    for m in re.finditer(r'(?is)\ba\s?b\s?s\s?t\s?r\s?a\s?c\s?t\b[\s:*_#]*(.{200,3500}?)'
                         r'(?=\n#+\s|\bkey\s?words?\b|\n\s*\**\s*(?:1\.?\s*)?introduction\b)', t):
        s = m.group(1)
        if '](' in s[:300]:                     # a page's table of contents, not the abstract
            continue
        return clean_abstract(re.sub(r'[*_#>|]', ' ', s))
    return None


def choose_abstract(doi, rec, md_text=None):
    """(abstract, source) in the order of preference used to build the library: the JATS full text,
    Europe PMC or OpenAlex, Crossref, Semantic Scholar, and last the full-text Markdown. (None, None)
    when none has one."""
    if rec.get('jats'):
        a = jats_abstract(rec['jats'])
        if a:
            return a, 'full text (JATS)'
    if rec.get('abstract'):
        return clean_abstract(rec['abstract']), 'Europe PMC / OpenAlex'
    a = crossref_abstract(doi)
    if a:
        return a, 'Crossref'
    a = s2_abstract(doi)
    if a:
        return a, 'Semantic Scholar'
    a = abstract_from_markdown(md_text) if md_text else None
    if a:
        return a, 'full text (PDF or web page)'
    return None, None


# ====================================================================== PDFs
def pdf_text(source, pages):
    """(text of the first `pages` pages, page count) of a PDF given as bytes or as a path."""
    if isinstance(source, (bytes, bytearray)):
        doc = pymupdf.open(stream=source, filetype='pdf')
    else:
        doc = pymupdf.open(source)
    with doc:
        return ' '.join(doc[i].get_text() for i in range(min(pages, doc.page_count))), doc.page_count


def pdf_matches(source, title):
    """True if the first two pages of the PDF (bytes or path) contain the title.

    Word pairs are compared rather than single words, which common words would satisfy on any page:
    at least 60 % of the title's consecutive word pairs must occur in the text. Very short titles fall
    back to all significant words being present."""
    try:
        text, _ = pdf_text(source, 2)
    except Exception:
        return False
    tt = [w for w in re.findall(r'[a-z0-9]+', fold(title)) if len(w) > 1]
    xt = re.findall(r'[a-z0-9]+', fold(text.replace('-\n', '')))
    if len(tt) < 3:
        return containment(title, text) >= 0.9
    tb = {(a, b) for a, b in zip(tt, tt[1:])}
    xb = {(a, b) for a, b in zip(xt, xt[1:])}
    return len(tb & xb) / len(tb) >= 0.6


def save_pdf(content, key, title, source, rec, lit=None):
    """Keep a candidate PDF as <key>.pdf only if it is a real PDF (at least 10 kB) of this work.
    The check runs in memory, so a rejected download never touches the library; the attempt and its
    outcome go to rec['tried']."""
    if not content or content[:5] != b'%PDF-' or len(content) < 10_000:
        rec['tried'].append([source, 'not a pdf'])
        return False
    if not pdf_matches(content, title):
        rec['tried'].append([source, 'title not found in pdf'])
        return False
    with open(os.path.join(lit or LIT, key + '.pdf'), 'wb') as f:
        f.write(content)
    rec['pdf'] = source
    rec['tried'].append([source, 'ok'])
    return True


def keep_jats(content, source, rec):
    """Keep JATS XML in memory only if it carries a <body> (otherwise it is metadata only). The XML is
    not stored: it is converted to Markdown."""
    if content and b'<body' in content:
        rec['jats'], rec['xml'] = content, source
        return True
    rec['tried'].append([source, 'xml without body'])
    return False


# ====================================================================== open-access sources
S3 = 'https://pmc-oa-opendata.s3.amazonaws.com'


def s3_meta(pmcid):
    """Metadata of the latest version of a PMC article in the PMC open-data bucket, or None."""
    r = get(f'{S3}/?list-type=2&prefix=metadata/{pmcid}.&max-keys=10', 's3', T_S3)
    if r is None or not r.ok:
        return None
    keys = re.findall(r'<Key>(metadata/PMC\d+\.(\d+)\.json)</Key>', r.text)
    if not keys:
        return None
    k = max(keys, key=lambda x: int(x[1]))[0]
    m = get(f'{S3}/{k}', 's3', T_S3)
    return m.json() if (m is not None and m.ok) else None


def s3_url(uri):
    """HTTPS address of an s3://pmc-oa-opendata/ object."""
    return S3 + '/' + uri[len('s3://pmc-oa-opendata/'):].split('?')[0]


def openalex(doi):
    """OpenAlex record of a DOI: open-access status, copies, abstract (as an inverted index)."""
    r = get(f'https://api.openalex.org/works/doi:{urllib.parse.quote(doi, safe="/")}'
            '?select=id,open_access,best_oa_location,locations,ids,abstract_inverted_index', 'openalex', T)
    return r.json() if (r is not None and r.ok) else {}


def s2(doi):
    """Semantic Scholar record of a DOI (its openAccessPdf)."""
    r = get(f'https://api.semanticscholar.org/graph/v1/paper/DOI:{urllib.parse.quote(doi, safe="/")}'
            '?fields=openAccessPdf,externalIds', 's2', T_S2)
    return r.json() if (r is not None and r.ok) else {}


_ARCHIVE_INDEX = None


def archive_index():
    """DOI -> path of the paper PDFs in the local archive folder given with --archive (a team's shared
    folder, for example), by the DOI printed on their first two pages. Built once per run, and only when a
    work reaches this source; empty without --archive."""
    global _ARCHIVE_INDEX
    if _ARCHIVE_INDEX is None:
        _ARCHIVE_INDEX = {}
        for p in (glob.glob(os.path.join(ARCHIVE, '**', '*.pdf'), recursive=True) if ARCHIVE else []):
            try:
                text, _ = pdf_text(p, 2)
            except Exception:
                continue
            d = find_doi(text)
            if d:
                _ARCHIVE_INDEX.setdefault(d, p)
    return _ARCHIVE_INDEX


def repo_api_files(url):
    """PDF download URLs from a repository's public API, for figshare, Zenodo and OSF records."""
    m = re.search(r'figshare\.com/.*/(\d+)(?:/\d+)?/?$', url)
    if m:
        r = get(f'https://api.figshare.com/v2/articles/{m.group(1)}', 'figshare', T)
        if r is not None and r.ok:
            return [f['download_url'] for f in r.json().get('files', []) if f['name'].lower().endswith('.pdf')]
    m = re.search(r'zenodo\.org/(?:records|record)/(\d+)', url)
    if m:
        r = get(f'https://zenodo.org/api/records/{m.group(1)}', 'zenodo', T)
        if r is not None and r.ok:
            return [f['links']['self'] for f in r.json().get('files', []) if f['key'].lower().endswith('.pdf')]
    m = re.search(r'osf\.io/([a-z0-9]{5})', url)
    if m:
        return [f'https://osf.io/{m.group(1)}/download']
    return []


def declared_pdf(r):
    """The PDF address a landing page declares for machines (<meta name="citation_pdf_url">), or None."""
    if r is None or not r.ok or 'html' not in (r.headers.get('content-type') or ''):
        return None
    m = re.search(r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)', r.text, re.I) \
        or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']citation_pdf_url', r.text, re.I)
    return urllib.parse.urljoin(r.url, m.group(1)) if m else None


def other_versions(title, family):
    """Free-copy URLs of other OpenAlex records (a preprint, an accepted manuscript in a repository)
    with the same title and the same first author."""
    fam = fold(family)
    q = urllib.parse.quote(re.sub(r'[^\w\s]', ' ', title)[:200])
    r = get(f'https://api.openalex.org/works?search={q}&per-page=10'
            '&select=id,doi,display_name,authorships,best_oa_location,locations,open_access', 'openalex', T)
    if r is None or not r.ok:
        return []
    urls = []
    for w in r.json().get('results', []):
        t = w.get('display_name') or ''
        if containment(title, t) < 0.9 or containment(t, title) < 0.9:
            continue
        first = fold(((w.get('authorships') or [{}])[0].get('author') or {}).get('display_name') or '')
        if fam and fam not in first:
            continue
        for loc in [w.get('best_oa_location') or {}] + (w.get('locations') or []):
            for x in (loc.get('pdf_url'), loc.get('landing_page_url')):
                if x and 'doi.org' not in x and x not in urls:
                    urls.append(x)
    return urls


def try_url(url, key, title, rec, label):
    """Download a URL, or the PDF its page declares, and keep it if it is this work. Stops at refused
    hosts and at anti-bot checks, recording why."""
    if refused(url):
        rec['tried'].append([f'{label}: {url}', 'not scripted (ScienceDirect, Wiley or institutional login)'])
        return False
    r = get(url, urllib.parse.urlparse(url).netloc, T, timeout=90, allow_redirects=True)
    if challenged(r):
        rec['tried'].append([f'{label}: {url}', 'bot protection'])
        return False
    if r is not None and r.ok and r.content[:5] == b'%PDF-':
        return save_pdf(r.content, key, title, f'{label}: {url}', rec)
    pdf = declared_pdf(r)
    if pdf:
        if refused(pdf):
            rec['tried'].append([f'{label}: {pdf}', 'not scripted (ScienceDirect, Wiley or institutional login)'])
            return False
        r2 = get(pdf, urllib.parse.urlparse(pdf).netloc, T, timeout=90, allow_redirects=True)
        if challenged(r2):
            rec['tried'].append([f'{label}: {pdf}', 'bot protection'])
            return False
        if r2 is not None and r2.ok:
            return save_pdf(r2.content, key, title, f'{label}: {pdf}', rec)
    rec['tried'].append([f'{label}: {url}', r.status_code if r is not None else 'error'])
    return False


def other_copies(key, title, family, rec):
    """Free copies the direct sources could not take, through interfaces meant for programs:
    1. repository APIs (figshare, Zenodo, OSF) for the URLs already tried;
    2. the PDF link a landing page declares for machines;
    3. other versions of the same work indexed by OpenAlex."""
    recorded = [t[0] for t in rec['tried'] if str(t[0]).startswith('http')]
    for url in dict.fromkeys(recorded):                                  # 1. repository APIs
        for f in repo_api_files(url):
            if try_url(f, key, title, rec, 'repository API'):
                return True
    for url in dict.fromkeys(recorded):                                  # 2. declared PDF
        if 'pdf' in url.lower() and not url.lower().endswith('/'):
            continue                                                     # a direct PDF link already refused
        if try_url(url, key, title, rec, 'landing page'):
            return True
    for url in other_versions(title, family)[:4]:                        # 3. other versions
        if url in recorded:
            continue
        if try_url(url, key, title, rec, 'other version'):
            return True
    return False


def new_record():
    """What one retrieval attempt found: PDF source, JATS XML (bytes) and its source, identifiers,
    licence, OpenAlex access status, abstract, and the list of [what was tried, outcome]."""
    return dict(tried=[], pdf=None, jats=None, xml=None, pmid=None, pmcid=None, license=None,
                oa_status=None, abstract=None)


def retrieve(doi, key, title, family, rec):
    """Try the legal open-access sources for one work, in order, stopping at the first valid PDF:
      1. the PMC open-data bucket on AWS (PDF and JATS XML of the PMC open-access subset and of author
         manuscripts, with licence), the PMCID coming from Europe PMC;
      2. Europe PMC full-text XML (JATS) when the bucket has no XML;
      3. the open-access locations listed by OpenAlex (publisher gold, hybrid or bronze; repositories);
      4. Semantic Scholar's openAccessPdf;
      5. the PDFs of the local archive (--archive), by the DOI printed in them;
      6. for a work still without text, other_copies().
    A PDF found is written as <key>.pdf; JATS XML stays in rec['jats']. Returns rec."""
    ep = europepmc(doi)
    rec['pmid'], rec['pmcid'] = ep.get('pmid'), ep.get('pmcid')
    if ep.get('license'):
        rec['license'] = ep['license']
    rec['abstract'] = re.sub(r'<[^>]+>', ' ', ep.get('abstractText') or '').strip() or None

    if rec['pmcid']:                                                     # 1. PMC open-data bucket
        m = s3_meta(rec['pmcid'])
        if m:
            rec['license'] = m.get('license_code') or rec['license']
            if m.get('xml_url'):
                c, _ = download(s3_url(m['xml_url']), 's3')
                keep_jats(c, 'pmc-oa-opendata', rec)
            if m.get('pdf_url') and not rec['pdf']:
                c, st = download(s3_url(m['pdf_url']), 's3')
                if not save_pdf(c, key, title, 'pmc-oa-opendata', rec) and c is None:
                    rec['tried'].append(['pmc-oa-opendata pdf', st])
        else:
            rec['tried'].append(['pmc-oa-opendata', 'not in bucket'])
        if not rec['jats']:                                              # 2. Europe PMC JATS
            r = get(f'https://www.ebi.ac.uk/europepmc/webservices/rest/{rec["pmcid"]}/fullTextXML', 'epmc', T)
            if r is not None and r.ok:
                keep_jats(r.content, 'europepmc', rec)

    if not rec['pdf']:                                                   # 3. OpenAlex
        oa = openalex(doi)
        rec['oa_status'] = (oa.get('open_access') or {}).get('oa_status')
        inv = oa.get('abstract_inverted_index')
        if not rec['abstract'] and inv:                                  # word order from the inverted index
            pos = sorted((p, w) for w, ps in inv.items() for p in ps)
            rec['abstract'] = ' '.join(w for _, w in pos)
        urls = []
        for loc in [oa.get('best_oa_location') or {}] + (oa.get('locations') or []):
            if loc.get('pdf_url') and loc['pdf_url'] not in urls:
                urls.append(loc['pdf_url'])
                rec['license'] = rec['license'] or loc.get('license')
        for url in urls[:4]:
            c, st = download(url)
            if c is None:
                rec['tried'].append([url, st])
                continue
            if save_pdf(c, key, title, url, rec):
                break

    if not rec['pdf']:                                                   # 4. Semantic Scholar
        url = ((s2(doi) or {}).get('openAccessPdf') or {}).get('url')
        if url:
            c, st = download(url)
            if c is None:
                rec['tried'].append([url, st])
            else:
                save_pdf(c, key, title, url, rec)

    if not rec['pdf'] and doi in archive_index():                        # 5. local archive
        path = archive_index()[doi]
        with open(path, 'rb') as f:
            save_pdf(f.read(), key, title, 'archive:' + os.path.relpath(path, ARCHIVE), rec)

    if not rec['pdf'] and not rec['jats']:                               # 6. other copies
        other_copies(key, title, family, rec)
    return rec


# ====================================================================== JATS XML -> Markdown
def local(tag):
    return tag.split('}')[-1] if isinstance(tag, str) else ''


def inline(el):
    """Flatten an element with inline markup into Markdown text (text runs collapse whitespace;
    nested tables and figures keep their own line breaks)."""
    out = [ws(el.text)]
    for ch in el:
        t = local(ch.tag)
        inner = inline(ch)
        if t == 'italic':
            out.append(f'*{inner.strip()}*' if inner.strip() else inner)
        elif t == 'bold':
            out.append(f'**{inner.strip()}**' if inner.strip() else inner)
        elif t == 'sup':
            out.append(f'^{inner}^')
        elif t == 'sub':
            out.append(f'~{inner}~')
        elif t in ('table-wrap', 'fig', 'disp-formula'):   # block elements nested in a paragraph
            out.append('\n\n' + block(ch, 0).strip() + '\n\n')
        else:
            out.append(inner)
        out.append(ws(ch.tail))
    return ''.join(out)


def table_md(tw):
    """A JATS table as a Markdown pipe table (first row as header)."""
    rows = []
    for tr in tw.iter('{*}tr', 'tr'):
        cells = [inline(c).strip().replace('|', '\\|') for c in tr if local(c.tag) in ('td', 'th')]
        if cells:
            rows.append(cells)
    if not rows:
        return ''
    width = max(len(r) for r in rows)
    rows = [r + [''] * (width - len(r)) for r in rows]
    lines = ['| ' + ' | '.join(rows[0]) + ' |', '|' + '---|' * width]
    lines += ['| ' + ' | '.join(r) + ' |' for r in rows[1:]]
    return '\n'.join(lines)


def block(el, depth):
    """Render a block-level JATS element (and its children) as Markdown."""
    t = local(el.tag)
    if t in ('sec', 'abstract', 'ack', 'app'):
        parts = []
        title = el.find('{*}title') if el.find('{*}title') is not None else el.find('title')
        if title is not None and inline(title).strip():
            parts.append('#' * min(depth + 2, 6) + ' ' + inline(title).strip())
        elif t == 'abstract':
            parts.append('## Abstract')
        elif t == 'ack':
            parts.append('## Acknowledgements')
        for ch in el:
            if local(ch.tag) != 'title':
                parts.append(block(ch, depth + 1))
        return '\n\n'.join(p for p in parts if p.strip())
    if t == 'p':
        return inline(el).strip()
    if t == 'list':
        marker = '1.' if el.get('list-type') in ('order', 'arabic', 'alpha-lower', 'roman-lower') else '-'
        return '\n'.join(f'{marker} ' + ' '.join(block(c, depth) for c in li).strip()
                         for li in el if local(li.tag) == 'list-item')
    if t == 'table-wrap':
        label = inline(el.find('{*}label') if el.find('{*}label') is not None else etree.Element('x')).strip()
        cap = el.find('{*}caption')
        head = f'**{label}** ' if label else ''
        head += inline(cap).strip() if cap is not None else ''
        return (head + '\n\n' if head else '') + table_md(el)
    if t == 'fig':
        label = el.find('{*}label')
        cap = el.find('{*}caption')
        return ('**' + inline(label).strip() + '** ' if label is not None else '') + \
               (inline(cap).strip() if cap is not None else '')
    if t in ('disp-quote', 'boxed-text'):
        return '\n'.join('> ' + line for line in '\n\n'.join(block(c, depth) for c in el).splitlines())
    if t in ('title', 'label', 'object-id', 'graphic', 'media', 'alternatives'):
        return ''
    if len(el):
        return '\n\n'.join(block(c, depth) for c in el)
    return inline(el).strip()


def jats_to_md(content):
    """Markdown of a JATS article (bytes): abstract, body sections, lists, tables, figure captions,
    back matter and the reference list. Parsed with entity resolution and network access off."""
    root = etree.fromstring(content, PARSER)
    parts = []
    for ab in root.iter('{*}abstract', 'abstract'):
        if ab.get('abstract-type') in (None, 'abstract', 'structured'):
            parts.append(block(ab, 0))
            break
    body = root.find('.//{*}body') if root.find('.//{*}body') is not None else root.find('.//body')
    if body is not None:
        parts.append('\n\n'.join(block(c, 0) for c in body))
    back = root.find('.//{*}back') if root.find('.//{*}back') is not None else root.find('.//back')
    if back is not None:
        for ch in back:
            if local(ch.tag) == 'ref-list':
                refs = [inline(r).strip() for r in ch.iter('{*}ref', 'ref')]
                parts.append('## References\n\n' + '\n'.join(f'{i + 1}. {r}' for i, r in enumerate(refs)))
            elif local(ch.tag) in ('ack', 'app-group', 'sec', 'fn-group', 'notes'):
                parts.append(block(ch, 0))
    return '\n\n'.join(p for p in parts if p.strip())


# ====================================================================== Markdown files
def pdf_to_md(path):
    """Markdown of a PDF, converted with pymupdf4llm (imported here: it is slow to load)."""
    import pymupdf4llm
    return pymupdf4llm.to_markdown(path)


def html_to_md(path):
    """Markdown of an article web page saved from the browser, converted with markitdown."""
    from markitdown import MarkItDown
    return MarkItDown().convert(path).text_content


def yaml_str(s):
    """A double-quoted YAML string."""
    return '"' + str(s or '').replace('\\', '\\\\').replace('"', '\\"') + '"'


HEADER_RE = re.compile(r'\A---\n.*?\n---\n', re.S)


def header_value(text, field):
    """Value of one field of a Markdown file's YAML header ('' when absent), quotes removed."""
    m = HEADER_RE.match(text or '')
    v = re.search(rf'^{field}: (.*)$', m.group(0), re.M) if m else None
    if not v:
        return ''
    s = v.group(1).strip()
    if len(s) >= 2 and s[0] == s[-1] == '"':
        s = s[1:-1].replace('\\"', '"').replace('\\\\', '\\')
    return s


def set_header_fields(header, values):
    """Replace (or add, before the closing ---) fields of a YAML header block. Values are written as given."""
    for field, value in values.items():
        line = f'{field}: {value}'
        if re.search(rf'^{field}: .*$', header, re.M):
            header = re.sub(rf'^{field}: .*$', lambda _m: line, header, count=1, flags=re.M)
        else:
            header = header[:-len('---\n')] + line + '\n---\n'
    return header


def authors_for_header(row):
    """Author names for a new Markdown header: 'Given Family' from authors_full, else the authors column."""
    if row.get('authors_full'):
        return [' '.join(reversed(a.split(', ', 1))) for a in row['authors_full'].split('; ')]
    return [a.strip() for a in (row.get('authors') or '').split(',') if a.strip()]


def front_matter(row, source):
    """YAML header of a new Markdown file, so that the file can be read without the index."""
    authors = authors_for_header(row)
    lines = ['---', f'key: {row["key"]}', f'title: {yaml_str(row["title"])}',
             'authors: [' + ', '.join(yaml_str(a) for a in authors[:30]) + (', "et al."' if len(authors) > 30 else '') + ']',
             f'year: {row["year"]}', f'journal: {yaml_str(row["source"])}', f'doi: {row["doi"]}',
             f'pmid: {row["pmid"]}', f'pmcid: {row["pmcid"]}', f'license: {yaml_str(row["license"])}',
             f'text_source: {yaml_str(source)}', '---', '']
    return '\n'.join(lines)


def read_text(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def write_markdown(row, body, source, lit=None):
    """Write <key>.md: YAML header, '# title', body. An existing file keeps its header and title line,
    with text_source, pmid, pmcid and license brought up to date from the row; a new file gets a header
    built from the row. Sets the row's md column."""
    path = os.path.join(lit or LIT, row['key'] + '.md')
    old = read_text(path) if os.path.exists(path) else ''
    m = HEADER_RE.match(old)
    if m:
        head = set_header_fields(m.group(0), {'pmid': row['pmid'], 'pmcid': row['pmcid'],
                                              'license': yaml_str(row['license']), 'text_source': yaml_str(source)})
        first = old[m.end():].split('\n', 1)[0]
        title_line = first if first.startswith('# ') else '# ' + row['title']
    else:
        head, title_line = front_matter(row, source), '# ' + row['title']
    with open(path, 'w', encoding='utf-8') as f:
        f.write(head + title_line + '\n\n' + body.strip() + '\n')
    row['md'] = row['key'] + '.md'


def summary_body(row):
    """(body, text_source) of a Markdown without full text: the abstract when the row has one,
    otherwise the metadata only."""
    if row.get('text_type') == 'abstract' and row.get('abstract_or_summary'):
        return '## Abstract\n\n' + row['abstract_or_summary'], 'abstract only (full text not retrieved)'
    return '', 'metadata only (full text and abstract not retrieved)'


# Markdown made from a source the library no longer stores (JATS XML, a saved web page): rewriting it
# from the PDF or the abstract would lose text, so it is kept unless md --force is given.
IRREPLACEABLE = ('full text, JATS XML', 'full text, article web page')


def full_text_here(key, lit=None):
    """True if the library folder holds the full text of a work: <key>.pdf, or a <key>.md whose header says
    it holds the full text (one made from JATS XML or a web page has no PDF). Decided from the files, never
    from the full_text column: a fresh clone receives the CSV as the owner's machine wrote it, without the files."""
    lit = lit or LIT
    if os.path.exists(os.path.join(lit, key + '.pdf')):
        return True
    md = os.path.join(lit, key + '.md')
    return os.path.exists(md) and header_value(read_text(md), 'text_source').startswith('full text')


def mark_full_text(row, lit=None):
    """Full text is here: set full_text, access and the pdf column."""
    row['full_text'], row['access'] = 'yes', 'open'
    row['pdf'] = row['key'] + '.pdf' if os.path.exists(os.path.join(lit or LIT, row['key'] + '.pdf')) else ''


def apply_retrieval(row, rec, note=None):
    """Bring a row, and its Markdown, up to date with what retrieve() found."""
    key = row['key']
    for col in ('pmid', 'pmcid'):
        if rec.get(col) and not row[col]:
            row[col] = str(rec[col])
    if rec.get('license') and not row['license']:
        row['license'] = normalise_license(rec['license'])
    full = bool(rec['pdf'] or rec['jats'])
    md_text = None
    if full:                                    # full text: JATS preferred, the PDF when the XML is thin
        pdf = os.path.join(LIT, key + '.pdf')
        if rec['jats']:
            body, source = jats_to_md(rec['jats']), f'full text, JATS XML ({rec["xml"]})'
            if len(body) < 2000 and os.path.exists(pdf):
                body, source = pdf_to_md(pdf), f'full text, PDF ({rec["pdf"]})'
        else:
            body, source = pdf_to_md(pdf), f'full text, PDF ({rec["pdf"]})'
        write_markdown(row, body, source)
        mark_full_text(row)
        md_text = read_text(os.path.join(LIT, key + '.md'))
    else:
        # no full text here: a row copied from another machine (a fresh clone) may still say yes and name a PDF
        row['full_text'], row['pdf'] = 'no', ''
        oa = rec.get('oa_status')
        if oa:
            row['access'] = 'open, host blocks download' if oa in OPEN else 'closed'
    if row['doi'] and row['text_type'] != 'abstract':          # abstract, when the row has none yet
        found, src = choose_abstract(row['doi'], rec, md_text)
        if found:
            row.update(abstract_or_summary=found, text_type='abstract', text_source=src)
        elif not row['abstract_or_summary']:
            if note:
                row.update(abstract_or_summary=note, text_type='description', text_source='written by hand')
            else:
                row['text_source'] = 'no abstract in open sources'
    if note and row['abstract_or_summary'] != note:
        print(f'  --note not used: {key} has an abstract')
    if not full:                                # abstract-only or metadata-only Markdown
        path = os.path.join(LIT, key + '.md')
        src = header_value(read_text(path), 'text_source') if os.path.exists(path) else ''
        if not src or (src.startswith('metadata only') and row['text_type'] == 'abstract'):
            write_markdown(row, *summary_body(row))


def print_tried(rec):
    for what, outcome in rec['tried']:
        print(f'    {what}: {outcome}')


# ====================================================================== add
def cmd_add(args):
    """Add one work by its DOI."""
    fields, rows = read_rows()
    doi = clean_doi(args.doi)
    if not doi:
        sys.exit(f'not a DOI: {args.doi}')
    same = [r['key'] for r in rows if r['doi'] == doi]
    if same:
        sys.exit(f'{doi} is already in the library as {same[0]}')
    if args.pdf and not os.path.isfile(args.pdf):
        sys.exit(f'no such file: {args.pdf}')
    meta = crossref(doi) or epmc_meta(doi)
    if not meta:
        sys.exit(f'{doi}: not found on Crossref or Europe PMC')
    if args.title and not title_accepted(meta, args.title):
        sys.exit(f'{doi}: the registered title does not match the one given\n'
                 f'  registered: {full_title(meta)}\n  given:      {args.title}')
    taken = {r['key'] for r in rows}
    if args.key and args.key in taken:
        sys.exit(f'the key {args.key} is already in the library')
    key = args.key or make_key(meta, taken, key_style(rows))
    row = row_from_meta(key, doi, meta)
    row['cited_in'] = args.cited_in or ''
    print(f'{key}: {row["title"]} ({row["authors"]}, {row["year"]})')

    rec = new_record()
    if args.pdf:                                # a PDF supplied by hand wins over every other source
        with open(args.pdf, 'rb') as f:
            if not save_pdf(f.read(), key, row['title'], 'supplied by hand', rec):
                print(f'  {args.pdf} not filed ({rec["tried"][-1][1]}); if it is this paper, copy it as '
                      f'{key}.pdf into the library and run: literature.py md {key}')
    retrieve(doi, key, row['title'], first_family(row), rec)
    apply_retrieval(row, rec, note=args.note)
    rows.append(row)
    write_rows(rows, fields)
    print_tried(rec)
    print(f'{key}: added; full text {row["full_text"]}, access "{row["access"]}", '
          f'text "{row["text_type"] or "none"}" ({row["text_source"]})')


# ====================================================================== fetch
def cmd_fetch(args):
    """Retry the open-access sources for works whose full text is not in the folder (all of them, or the
    keys given). The folder decides, not the full_text column, so that in a fresh clone, which has the CSV
    and none of the files, fetch downloads the open-access copies again and writes their Markdown."""
    fields, rows = read_rows()
    by_key = {r['key']: r for r in rows}
    unknown = [k for k in args.keys if k not in by_key]
    if unknown:
        sys.exit('unknown keys: ' + ', '.join(unknown))
    targets = [by_key[k] for k in args.keys] if args.keys else \
        [r for r in rows if r['doi'] and not full_text_here(r['key'])]
    found = []
    for i, row in enumerate(targets, 1):
        key = row['key']
        if not row['doi']:
            print(f'{key}: no DOI, nothing to search')
            continue
        if full_text_here(key):
            print(f'{key}: already has its full text')
            continue
        rec = retrieve(row['doi'], key, row['title'], first_family(row), new_record())
        apply_retrieval(row, rec)
        write_rows(rows, fields)                # after every work, so an interruption loses nothing
        ok = bool(rec['pdf'] or rec['jats'])
        print(f'{i}/{len(targets)} {key}: {"full text found" if ok else "no free copy"}', flush=True)
        if not ok:
            print_tried(rec)
        else:
            found.append(key)
    print(f'done: {len(found)} new full texts', found)


# ====================================================================== collect
def cmd_collect(args):
    """File the PDFs saved by hand in a folder (default: Downloads).

    A file named after a key (<key>.pdf, or <key>.html for an article page saved from the browser) is
    taken as that work. Any other PDF is identified by the DOI printed on its first pages or, when no DOI
    of the library is printed there (older PDFs), by its title: it is taken only when exactly one work
    without a PDF, with a title of five words or more, has 80 % of its word pairs on those pages.
    A PDF is filed only if it contains the work's title on its first pages (60 % of the word pairs) and
    has more than two pages (a publisher preview usually has one or two); it is then moved into the
    library as <key>.pdf and its Markdown written. An HTML page is converted to <key>.md and left where
    it is. Files that fail stay where they are and are reported."""
    fields, rows = read_rows()
    by_key = {r['key']: r for r in rows}
    by_doi = {r['doi']: r['key'] for r in rows if r['doi']}

    def has_pdf(k):
        return os.path.exists(os.path.join(LIT, k + '.pdf'))

    # candidates for identification by title: works without a PDF whose title is long enough to be distinctive
    missing = [k for k, r in by_key.items() if not has_pdf(k) and len(re.findall(r'[a-z0-9]+', fold(r['title']))) >= 5]
    moved, rejected = [], []
    for name in sorted(os.listdir(args.src)):
        key, ext = os.path.splitext(name)
        ext = ext.lower()
        if ext not in ('.pdf', '.html') or (ext == '.html' and key not in by_key):
            continue
        src = os.path.join(args.src, name)
        if ext == '.html':                      # article page saved from the browser
            row = by_key[key]
            if row['full_text'] == 'yes':
                continue
            text = read_text_lenient(src)
            score = pairs_found(row['title'], re.sub(r'<[^>]+>', ' ', text))
            if score < 0.6:
                rejected.append((name, f'title match {score:.2f}'))
                continue
            write_markdown(row, html_to_md(src), 'full text, article web page (browser)')
            mark_full_text(row)
            moved.append(f'{name} -> {key}.md (the page can now be deleted)')
            continue
        try:
            text, pages = pdf_text(src, 3)
        except Exception as e:
            if key in by_key:
                rejected.append((name, f'unreadable: {e}'))
            continue
        if key not in by_key:                   # a file downloaded by hand: identify it by DOI
            doi = find_doi(text)
            if doi in by_doi:
                key = by_doi[doi]
            else:                               # no library DOI printed: a clear, unique title match
                hits = [k for k in missing if pairs_found(by_key[k]['title'], text) >= 0.8]
                if len(hits) != 1:
                    continue
                key = hits[0]
        if has_pdf(key):
            if name == key + '.pdf':
                rejected.append((name, 'the library already has this PDF'))
            continue
        row = by_key[key]
        score = pairs_found(row['title'], text)
        if score < 0.6 or pages <= 2:
            rejected.append((name, f'title match {score:.2f}, {pages} pages'))
            continue
        shutil.move(src, os.path.join(LIT, key + '.pdf'))
        mark_full_text(row)
        md = os.path.join(LIT, key + '.md')
        src_md = header_value(read_text(md), 'text_source') if os.path.exists(md) else ''
        if not src_md.startswith(IRREPLACEABLE):   # a Markdown from JATS or a web page is better: keep it
            write_markdown(row, pdf_to_md(os.path.join(LIT, key + '.pdf')), 'full text, PDF (browser (user session))')
        if row['doi'] and row['text_type'] != 'abstract':   # an abstract read from the new full text
            found = abstract_from_markdown(read_text(md))
            if found:
                row.update(abstract_or_summary=found, text_type='abstract', text_source='full text (PDF or web page)')
        moved.append(f'{name} -> {key}.pdf')
    if moved:
        write_rows(rows, fields)
    print('filed', len(moved))
    for m in moved:
        print('  ' + m)
    for n, why in rejected:
        print('REJECTED', n, why)


def read_text_lenient(path):
    with open(path, encoding='utf-8', errors='replace') as f:
        return f.read()


# ====================================================================== md
def cmd_md(args):
    """(Re)write Markdown files. With keys: those works. Without: every work whose Markdown is missing or
    stale (a PDF exists and the Markdown holds only the abstract or the metadata, or is older than the PDF).
    A Markdown made from JATS XML or a web page is kept unless --force is given, because its source is
    no longer stored. A reference without a DOI gets a Markdown only from a PDF."""
    fields, rows = read_rows()
    by_key = {r['key']: r for r in rows}
    unknown = [k for k in args.keys if k not in by_key]
    if unknown:
        sys.exit('unknown keys: ' + ', '.join(unknown))
    written, kept = [], 0
    for row in ([by_key[k] for k in args.keys] if args.keys else rows):
        key = row['key']
        pdf, md = os.path.join(LIT, key + '.pdf'), os.path.join(LIT, key + '.md')
        src = header_value(read_text(md), 'text_source') if os.path.exists(md) else ''
        if not row['doi'] and not os.path.exists(pdf):
            if args.keys:
                print(f'{key}: no DOI and no PDF, nothing to write')
            continue
        if src.startswith(IRREPLACEABLE) and not args.force:
            kept += 1
            if args.keys:
                print(f'{key}: kept, its Markdown comes from {src.split(" (")[0][len("full text, "):]} (use --force to rewrite it)')
            continue
        if not args.keys and os.path.exists(md):
            stale = os.path.exists(pdf) and (src.startswith(('abstract only', 'metadata only'))
                                             or os.path.getmtime(md) < os.path.getmtime(pdf))
            if not stale:
                kept += 1
                continue
        if os.path.exists(pdf):
            m = re.match(r'full text, PDF \((.*)\)$', src)
            write_markdown(row, pdf_to_md(pdf), f'full text, PDF ({m.group(1) if m else "source not recorded"})')
            mark_full_text(row)
        else:
            write_markdown(row, *summary_body(row))
            row['full_text'] = 'no'
        written.append(key)
    write_rows(rows, fields)
    print(f'written {len(written)}: {", ".join(written)} | kept {kept}')


# ====================================================================== check
def check_problems(lit=None):
    """List of consistency problems between bibliography.csv and the files of the library folder."""
    lit = lit or LIT
    problems = []
    fields, rows = read_rows(os.path.join(lit, CSV_NAME))
    missing = [c for c in COLUMNS if c not in fields]
    extra = [c for c in fields if c not in COLUMNS]
    if missing:
        problems.append('columns missing from the CSV: ' + ', '.join(missing))
    if extra:
        problems.append('unexpected columns in the CSV: ' + ', '.join(extra))
    for col in ('key', 'doi'):
        seen = {}
        for r in rows:
            v = r.get(col) or ''
            if v:
                seen[v] = seen.get(v, 0) + 1
        problems += [f'duplicate {col}: {v} ({n} rows)' for v, n in sorted(seen.items()) if n > 1]
    names = set(os.listdir(lit))
    described = {CSV_NAME}
    # Rows that name files (or claim a full text) of which none is here, as every row of a fresh clone,
    # which receives the CSV without the files: one line with the remedy instead of a line per missing file.
    claiming, fileless = 0, []
    for r in rows:
        key = r.get('key') or ''
        claims = bool(r.get('pdf') or r.get('md') or r.get('full_text') == 'yes')
        restore = claims and key + '.pdf' not in names and key + '.md' not in names
        claiming += claims
        if restore:
            fileless.append(key)
        for col, ext in (('pdf', '.pdf'), ('md', '.md')):
            name, value = key + ext, r.get(col) or ''
            here = name in names
            if value and value != name:
                problems.append(f'{key}: the {col} column says "{value}", expected "{name}"')
            elif value and not here and not restore:
                problems.append(f'{key}: {value} is named in the CSV but missing from the folder')
            elif here and not value:
                problems.append(f'{key}: {name} is in the folder but the {col} column is empty')
            if here:
                described.add(name)
        md_text = read_text(os.path.join(lit, key + '.md')) if key + '.md' in names else ''
        if md_text and header_value(md_text, 'key') != key:
            problems.append(f'{key}: the header of {key}.md names the key "{header_value(md_text, "key")}"')
        full = full_text_here(key, lit)
        if r.get('full_text') not in ('yes', 'no'):
            problems.append(f'{key}: full_text is "{r.get("full_text")}", expected yes or no')
        elif (r['full_text'] == 'yes') != full and not restore:
            problems.append(f'{key}: full_text is {r["full_text"]} but the folder holds '
                            + ('a full text' if full else 'no full text'))
    if fileless:
        who = ('none of the works has its files here, as in a fresh clone' if len(fileless) == claiming
               else 'no local files for ' + ', '.join(fileless))
        problems.append(f'{who}: fetch downloads the legal open-access copies and writes the Markdown, '
                        'then collect files the copies downloaded in the browser')
    for n in sorted(names - described):
        kind = 'subfolder' if os.path.isdir(os.path.join(lit, n)) else 'file'
        problems.append(f'{kind} not described by any row of the CSV: {n}')
    return problems, rows


def cmd_check(args):
    problems, rows = check_problems()
    for p in problems:
        print('PROBLEM', p)
    n_pdf = sum(1 for r in rows if r['pdf'])
    n_md = sum(1 for r in rows if r['md'])
    n_full = sum(1 for r in rows if r['full_text'] == 'yes')
    print(f'{len(rows)} rows, {n_pdf} PDF, {n_md} Markdown, {n_full} with full text: '
          + (f'{len(problems)} problems' if problems else 'consistent'))
    return 1 if problems else 0


# ====================================================================== bib
BIBTYPE = {'journal article': 'article', 'book': 'book', 'book chapter': 'incollection',
           'conference paper': 'inproceedings', 'report': 'techreport', 'statistics report': 'techreport'}


def bib_escape(s):
    return re.sub(r'([&%#_])', r'\\\1', s or '')


def bib_authors(row):
    """BibTeX author list. Works with a DOI: authors_full, each 'Family, Given' as is and a single name
    (an organisation) in braces. References without a DOI: the authors column as one braced name."""
    if row.get('doi'):
        names = [a for a in (row.get('authors_full') or '').split('; ') if a]
        return ' and '.join(a if ', ' in a else '{' + a + '}' for a in names)
    return '{' + row['authors'] + '}' if row.get('authors') else ''


def bibtex(r):
    """One BibTeX entry for a CSV row, keyed by its library key."""
    typ = BIBTYPE.get(r['kind'], 'misc')
    f = [('author', bib_authors(r)), ('title', '{' + bib_escape(r['title']) + '}'), ('year', r['year'])]
    if typ == 'article':
        f.append(('journal', bib_escape(r['source'])))
    elif typ in ('incollection', 'inproceedings'):
        f.append(('booktitle', bib_escape(r['source'])))
    elif r['source']:
        f.append(('publisher' if typ in ('book', 'techreport') else 'howpublished', bib_escape(r['source'])))
    for k in ('volume', 'number', 'pages', 'doi', 'pmid', 'pmcid', 'url'):
        v = r.get('issue' if k == 'number' else k, '')
        if k == 'pages':
            v = v.replace('-', '--')        # BibTeX page range
        if k == 'url' and r.get('doi'):
            v = ''                          # the DOI already locates the work
        if v:
            f.append((k, v))
    body = ',\n'.join(f'  {k} = {{{v}}}' for k, v in f if v)
    return f'@{typ}{{{r["key"]},\n{body}\n}}\n'


def cmd_bib(args):
    _, rows = read_rows()
    text = ''.join(bibtex(r) + '\n' for r in sorted(rows, key=lambda r: r['key']))
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f'{len(rows)} entries written to {args.out}')
    else:
        try:
            sys.stdout.write(text)
        except BrokenPipeError:             # the output was piped into a reader that stopped early (head)
            sys.stderr.close()


# ====================================================================== the library folder
def git_root(start):
    """The root of the git repository holding `start`, or None outside a repository."""
    here = pathlib.Path(start).resolve()
    for d in [here, *here.parents]:
        if (d / '.git').exists():
            return d
    return None


def find_library(start):
    """The library folder: literature/ or docs/literature/ holding bibliography.csv, in `start` or one of
    its parents up to the repository root (so the script runs from anywhere inside the project). None when
    the project has no library yet."""
    here = pathlib.Path(start).resolve()
    top = git_root(here)
    for d in [here, *here.parents]:
        if d.name == 'literature' and (d / CSV_NAME).is_file():
            return str(d)
        for cand in (d / 'literature', d / 'docs' / 'literature'):
            if (cand / CSV_NAME).is_file():
                return str(cand)
        if top is not None and d == top:
            break
    return None


def create_library(lib):
    """A new, empty library: the folder, a bibliography.csv with its header, and the .gitignore lines of the
    repository that keep every file of the folder local except bibliography.csv. Returns the lines added."""
    os.makedirs(lib, exist_ok=True)
    write_rows([], COLUMNS, os.path.join(lib, CSV_NAME))
    top = git_root(lib)
    if top is None:
        return []
    rel = pathlib.Path(lib).resolve().relative_to(top).as_posix()
    wanted = [f'{rel}/*', f'!{rel}/{CSV_NAME}']
    gi = top / '.gitignore'
    have = gi.read_text(encoding='utf-8').splitlines() if gi.exists() else []
    added = [w for w in wanted if w not in have]
    if added:
        text = gi.read_text(encoding='utf-8') if gi.exists() else ''
        with open(gi, 'a', encoding='utf-8') as f:
            f.write(('\n' if text and not text.endswith('\n') else '') + '\n'.join(added) + '\n')
    return added


def set_library(lib_arg, command, cwd=None):
    """Set LIT for this run: --lib when given, else the library found from the working directory. The
    first add in a project without a library creates literature/ at the repository root."""
    global LIT
    cwd = cwd or os.getcwd()
    lib = os.path.abspath(lib_arg) if lib_arg else find_library(cwd)
    if lib is None:
        if command != 'add':
            sys.exit('no library here: no literature/ or docs/literature/ with bibliography.csv from this folder '
                     'up to the repository root (give --lib, or add a first work to create one)')
        lib = str((git_root(cwd) or pathlib.Path(cwd)) / 'literature')
    if not os.path.isfile(os.path.join(lib, CSV_NAME)):
        if command != 'add':
            sys.exit(f'{lib} holds no {CSV_NAME}')
        added = create_library(lib)
        print(f'new library at {lib}' + (f'; .gitignore gains: {", ".join(added)}' if added else ''))
    LIT = lib
    return lib


# ====================================================================== command line
def main(argv=None):
    for stream in (sys.stdout, sys.stderr):     # titles and names are UTF-8; the Windows console may not be
        try:
            stream.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(prog='literature.py', description=__doc__.split('\n\n')[0])
    p.add_argument('--lib', help='the library folder (default: literature/ or docs/literature/ found from here)')
    p.add_argument('--archive', help='a local folder of PDFs searched by the DOI printed in them (add, fetch)')
    sub = p.add_subparsers(dest='command', required=True)
    a = sub.add_parser('add', help='add a work by its DOI')
    a.add_argument('--key', help='the key to use instead of the one the library would make')
    a.add_argument('doi', help='the DOI, bare or as a doi.org link')
    a.add_argument('--title', help='the title as cited: the DOI is refused if its registered title does not match')
    a.add_argument('--cited-in', default='', help='where the work is cited (cited_in column)')
    a.add_argument('--note', help='a short description, kept as the summary when no abstract is found')
    a.add_argument('--pdf', help='a PDF of the work (copied into the library if its title checks out)')
    f = sub.add_parser('fetch', help='retry the open-access sources for works whose full text is not in the folder')
    f.add_argument('keys', nargs='*', help='keys to retry (default: every work with a DOI and no full text in the folder)')
    c = sub.add_parser('collect', help='file the PDFs downloaded by hand')
    c.add_argument('--from', dest='src', default=DOWNLOADS, help='folder to look in (default: %(default)s)')
    m = sub.add_parser('md', help='write <key>.md again')
    m.add_argument('keys', nargs='*', help='keys (default: every missing or stale Markdown)')
    m.add_argument('--force', action='store_true',
                   help='also rewrite Markdown made from JATS XML or a web page (their source is not stored)')
    sub.add_parser('check', help='consistency report; exit code 1 on problems')
    b = sub.add_parser('bib', help='export BibTeX')
    b.add_argument('--out', help='file to write (default: print)')
    args = p.parse_args(argv)
    global ARCHIVE
    ARCHIVE = os.path.abspath(args.archive) if args.archive else None
    set_library(args.lib, args.command)
    commands = {'add': cmd_add, 'fetch': cmd_fetch, 'collect': cmd_collect, 'md': cmd_md,
                'check': cmd_check, 'bib': cmd_bib}
    return commands[args.command](args) or 0


if __name__ == '__main__':
    sys.exit(main())
