#!/usr/bin/env python3
"""A project's literature library: add works, retrieve their text, keep the record consistent.

The library is one flat folder of the project, literature/ at the root (docs/literature/ where a development
repository keeps its research side in docs/), holding
    bibliography.json  the record, tracked by git: a CSL JSON array (the data model of citation processors,
                       read by Pandoc as it is), one entry per cited work, sorted by id. An entry keeps what
                       identifies and cites the work (id, type, title, language, author, issued,
                       container-title or publisher, volume, issue, page, DOI, PMID, PMCID, and URL for a work
                       without a DOI) and, in its custom object, what the project writes about it: cited_in
                       (where the project uses it) and summary (a description written for a work without an
                       abstract). Any other field of an entry is kept as found.
    <key>.pdf          the full text of a work, when a legal copy was obtained (local, ignored by git)
    <key>.md           the text of a work for reading and searching (local, ignored by git): the full text,
                       the abstract, the summary or the metadata, as its YAML header says (text_source), with
                       the licence of the work
Nothing in the record describes one machine: what the folder holds is read from the folder, and what a source
can give again (the abstract, the licence, the open-access status, update notices) is looked up when needed.
The id is the name of both files and the work's citation key. A new library uses Surname_Year keys
(Iyamu_2021, DelReyPuech_2026, WHO_2025; a second work of the same author and year gets b, then c); a library
whose keys are mostly citation keys in the form author, year, first title word (alonzo2021interplay) keeps
that form for the works it adds. The files are rebuilt from the record with fetch, collect and md, so a clone
that has only the record gets its open-access texts back.

Subcommands (run from anywhere inside the project: the library is the literature/ or docs/literature/ folder
holding bibliography.json, found from the working directory up to the repository root, or given with --lib)
    add DOI [--key K] [--title T] [--cited-in T] [--note T] [--pdf PATH]
                        add a work: metadata from Crossref, legal open-access full text or abstract,
                        Markdown, new entry in the record. In a project without a library, the first add
                        creates literature/ at the repository root and the .gitignore lines that keep its
                        files local
    fetch [KEY ...]     try the legal open-access sources again for works whose full text is not in the
                        folder (in a fresh clone, every work with a DOI), writing the full text or the abstract
    collect [--from DIR]
                        file the PDFs downloaded by hand (default: the Downloads folder) under their keys
    md [KEY ...] [--force]
                        write <key>.md again from <key>.pdf; a work without a PDF gets a missing <key>.md
                        from its summary or its metadata (fetch brings the abstract)
    check [--fix]       the record and its agreement with the files; exit code 1 on problems; --fix first
                        rewrites the record in the script's layout
    list [KEY ...] [--csv PATH]
                        each work with the text the folder holds for it; --csv writes the table for a
                        spreadsheet, R or Python
    convert             turn the older bibliography.csv into bibliography.json, once, with no network call
--json, before the subcommand, prints one JSON object on standard output; the messages go to standard error.
Exit codes: 0 done, 1 check found problems, 2 refused (usage, a DOI or key that does not fit, no library, an
unreadable record), 3 a source the command needs could not be reached.
A work without a DOI (a report, a web page) is an entry written by hand (id, type, title, author, issued,
publisher or container-title, URL, custom.summary); md then writes its Markdown from a PDF placed in the
library as <key>.pdf. For LaTeX or Typst, pandoc bibliography.json -t biblatex -o references.bib writes a .bib.

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
import collections
import csv
import glob
import html
import json
import os
import pathlib
import re
import shutil
import sys
import time
import unicodedata
import urllib.parse

try:
    import pymupdf
    import requests
    from lxml import etree
except ImportError as _missing:       # a clear message instead of a traceback on a machine without them
    print(f'literature.py needs {_missing.name}: python -m pip install requests lxml pymupdf pymupdf4llm',
          file=sys.stderr)
    sys.exit(2)

# ====================================================================== paths
# The library folder and the optional local archive are set by main() from --lib and --archive, or found
# from the working directory; tests set them directly.
LIT = None
ARCHIVE = None
JSON = False        # set by --json: messages go to standard error, standard output carries one JSON object
RECORD = 'bibliography.json'
LEGACY = 'bibliography.csv'     # the record before CSL JSON, turned into bibliography.json by convert
DOWNLOADS = os.path.join(os.path.expanduser('~'), 'Downloads')

# Fields of an entry in the order the script writes them; any other field follows, in the order found.
FIELDS = ['id', 'type', 'title', 'language', 'author', 'issued', 'container-title', 'publisher', 'volume',
          'issue', 'page', 'DOI', 'PMID', 'PMCID', 'URL', 'custom']
# Keys of an entry's custom object that the script manages, in their order; any other key is kept.
CUSTOM = ['cited_in', 'summary']

# The item types of the CSL schema 1.0.2 (github.com/citation-style-language/schema, csl-data.json).
CSL_TYPES = {
    'article', 'article-journal', 'article-magazine', 'article-newspaper', 'bill', 'book', 'broadcast',
    'chapter', 'classic', 'collection', 'dataset', 'document', 'entry', 'entry-dictionary',
    'entry-encyclopedia', 'event', 'figure', 'graphic', 'hearing', 'interview', 'legal_case', 'legislation',
    'manuscript', 'map', 'motion_picture', 'musical_score', 'pamphlet', 'paper-conference', 'patent',
    'performance', 'periodical', 'personal_communication', 'post', 'post-weblog', 'regulation', 'report',
    'review', 'review-book', 'software', 'song', 'speech', 'standard', 'thesis', 'treaty', 'webpage'}
# Crossref work types as CSL types; any other Crossref type becomes a document.
CSL_TYPE = {'journal-article': 'article-journal', 'book': 'book', 'monograph': 'book', 'edited-book': 'book',
            'reference-book': 'book', 'book-chapter': 'chapter', 'book-section': 'chapter', 'book-part': 'chapter',
            'proceedings-article': 'paper-conference', 'report': 'report', 'report-component': 'report',
            'posted-content': 'article', 'dataset': 'dataset', 'reference-entry': 'entry-encyclopedia',
            'dissertation': 'thesis', 'standard': 'standard', 'peer-review': 'review'}
# CSL types whose journal, book, site, gazette or programme is a container-title; the others have a publisher.
CONTAINER = {'article', 'article-journal', 'article-magazine', 'article-newspaper', 'chapter', 'paper-conference',
             'entry', 'entry-dictionary', 'entry-encyclopedia', 'webpage', 'post', 'post-weblog', 'broadcast',
             'legislation', 'legal_case'}
# OpenAlex open-access statuses meaning that a free copy exists somewhere.
OPEN = {'gold', 'hybrid', 'bronze', 'green', 'diamond'}


def say(*parts):
    """A message for the user: standard output, or standard error when --json keeps standard output for the
    JSON result."""
    print(*parts, file=sys.stderr if JSON else sys.stdout, flush=True)


class Refused(Exception):
    """The command cannot run as asked: a DOI or key that does not fit, no library, an unreadable record.
    Exit code 2."""


class Unreachable(Exception):
    """A source the command needs could not be reached. Exit code 3."""


# ====================================================================== the record
def read_entries(path=None):
    """Read bibliography.json: the list of its entries. A file that is not a JSON array of objects each with an
    id (a merge conflict left in it, a hand edit gone wrong) is refused with the line and column where JSON
    stops."""
    path = path or os.path.join(LIT, RECORD)
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise Refused(f'{path} is not valid JSON: {e.msg} at line {e.lineno}, column {e.colno}') from None
    if not isinstance(data, list) or not all(isinstance(e, dict) and isinstance(e.get('id'), str) and e['id']
                                             for e in data):
        raise Refused(f'{path} is not a list of entries each with an id')
    return data


def sort_key(entry):
    """Entry order of the record: the id, ASCII-folded and in lower case, then as written."""
    return fold(entry['id']), entry['id']


def canonical(entry):
    """The entry as the script writes it: the fields of FIELDS in their order, then any other field as found;
    in custom, the keys of CUSTOM first. A managed field or custom key left empty is dropped."""
    e = dict(entry)
    if isinstance(e.get('custom'), dict):
        c = e['custom']
        e['custom'] = {**{k: c[k] for k in CUSTOM if c.get(k)}, **{k: v for k, v in c.items() if k not in CUSTOM}}
    out = {k: e[k] for k in FIELDS if k in e and e[k] not in ('', None, [], {})}
    out.update((k, v) for k, v in e.items() if k not in FIELDS)
    return out


def dump(entries):
    """The record's text: entries sorted by id, each in canonical form, indented by two spaces (Python's own
    json layout, so that any tool writes it the same way), characters as they are, a final newline."""
    return json.dumps([canonical(e) for e in sorted(entries, key=sort_key)], ensure_ascii=False, indent=2) + '\n'


def write_entries(entries, path=None):
    """Write bibliography.json: UTF-8 without a byte order mark, LF line ends. Written to a temporary file and
    then renamed, so an interruption never leaves a half-written record."""
    path = path or os.path.join(LIT, RECORD)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write(dump(entries))
    os.replace(tmp, path)


def doi_of(entry):
    """The entry's DOI in lower case ('' without one)."""
    return (entry.get('DOI') or '').lower()


def year_in(entry):
    """The year of the entry's issued date ('' without one)."""
    try:
        return str(entry['issued']['date-parts'][0][0])
    except (KeyError, TypeError, IndexError):
        return ''


def container(entry):
    """The journal, book, site or publisher of an entry, for a Markdown header and the table of list."""
    return entry.get('container-title') or entry.get('publisher') or ''


def project(entry):
    """The entry's custom object, where the project's own fields live ({} when it has none)."""
    return entry.get('custom') if isinstance(entry.get('custom'), dict) else {}


def name_text(n):
    """One CSL name as text: 'Given Family', or the literal name."""
    return n.get('literal') or ' '.join(x for x in (n.get('given'), n.get('family')) if x)


def names_line(entry, n=3):
    """The first authors of an entry as 'Family Initials', then 'et al.': for messages and the table of list."""
    out = []
    for a in entry.get('author') or []:
        ini = ''.join(p[0] for p in re.split(r'[\s\-.]+', a.get('given') or '') if p)
        out.append(a.get('literal') or f'{a.get("family", "")} {ini}'.strip())
    return ', '.join(out[:n]) + (', et al.' if len(out) > n else '')


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


FAILED = set()      # endpoint names whose last request got no answer (no connection, or 429 or 5xx twice)


def get(url, name, throttle, timeout=40, allow_redirects=True, **kw):
    """GET with throttling and one retry on 429 or 5xx. Returns a Response, or None on failure or when
    the URL (or a redirect) points to a refused host. An endpoint that gives no answer is noted in FAILED."""
    headers = kw.pop('headers', UA)
    r = None
    for attempt in range(2):
        throttle.wait(name)
        try:
            r = _get_following(url, headers, timeout, allow_redirects, **kw)
        except RefusedHost as e:
            say(f'    not requested: {e} (ScienceDirect, Wiley or an institutional login)')
            return None
        except requests.RequestException:
            r = None
        if r is not None and r.status_code not in (429, 500, 502, 503, 504):
            FAILED.discard(name)
            return r
        time.sleep(5 * (attempt + 1))
    FAILED.add(name)
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


def key_style(entries):
    """The key form of a library: 'surname_year' when it is empty or when at least half of its keys have
    that form, otherwise 'citekey'. The keys already in the library are never renamed."""
    keys = [e.get('id') or '' for e in entries if e.get('id')]
    if not keys or 2 * sum(bool(SURNAME_YEAR.match(k)) for k in keys) >= len(keys):
        return 'surname_year'
    return 'citekey'


def make_key(meta, taken, style='surname_year'):
    """A new key in the library's form (see key_style)."""
    return make_citekey(meta, taken) if style == 'citekey' else make_surname_year(meta, taken)


def csl_names(meta):
    """The authors of a Crossref record as CSL names: family and given names, or one literal name for an
    organisation or a person Crossref records with a single name."""
    out = []
    for a in meta.get('author') or []:
        fam, given, name = (ws(a.get(k)).strip() for k in ('family', 'given', 'name'))
        if fam and given:
            out.append({'family': fam, 'given': given})
        elif fam or name:
            out.append({'literal': fam or name})
    return out


def retraction(meta):
    """Kinds of update notice Crossref records for a work (correction, erratum, retraction)."""
    kinds = [x.get('type') for x in (meta.get('updated-by') or [])]
    return ', '.join(sorted(set(k for k in kinds if k)))


def entry_from_meta(key, doi, meta):
    """A new entry for a work with a DOI, from its Crossref (or Europe PMC) record: the CSL type, the title
    with its subtitle, the language when it is not English, the authors, the year, the journal (or the book,
    site or programme) or else the publisher, volume, issue, page and DOI."""
    typ = CSL_TYPE.get(meta.get('type'), 'document')
    e = {'id': key, 'type': typ, 'title': u(full_title(meta))}
    lang = (meta.get('language') or '').strip()
    if lang and not lang.lower().startswith('en'):
        e['language'] = lang
    if csl_names(meta):
        e['author'] = csl_names(meta)
    if year_of(meta).isdigit():
        e['issued'] = {'date-parts': [[int(year_of(meta))]]}
    src, pub = u((meta.get('container-title') or [''])[0]), u(meta.get('publisher'))
    if typ in CONTAINER:
        if src:
            e['container-title'] = src
        if pub and typ in ('chapter', 'paper-conference'):
            e['publisher'] = pub
    elif pub or src:
        e['publisher'] = pub or src
    for var in ('volume', 'issue', 'page'):
        if meta.get(var):
            e[var] = str(meta[var])
    e['DOI'] = doi
    return e


def first_family(entry):
    """Family name of the first author of an entry, or its literal name (for matching other versions of the
    work)."""
    first = (entry.get('author') or [{}])[0]
    return first.get('family') or first.get('literal') or ''


# ====================================================================== abstracts
PARSER = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, recover=True)


def clean_abstract(s):
    """Plain text of an abstract: markup removed, whitespace collapsed, a leading 'Abstract' dropped."""
    s = re.sub(r'<[^>]+>', ' ', s or '')
    s = re.sub(r'\s+', ' ', s).strip()
    return re.sub(r'^(Abstract|ABSTRACT|Summary)[:.]?\s+', '', s)


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


def choose_abstract(doi, rec):
    """(abstract, source) of a work whose full text was not found, in order of preference: Europe PMC or
    OpenAlex (already in rec), Crossref, Semantic Scholar. (None, None) when none has one."""
    if rec.get('abstract'):
        return clean_abstract(rec['abstract']), 'Europe PMC / OpenAlex'
    a = crossref_abstract(doi)
    if a:
        return a, 'Crossref'
    a = s2_abstract(doi)
    if a:
        return a, 'Semantic Scholar'
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


def front_matter(entry, source, license=''):
    """YAML header of a new Markdown file, so that the file can be read without the record."""
    authors = [name_text(a) for a in entry.get('author') or []]
    lines = ['---', f'key: {entry["id"]}', f'title: {yaml_str(entry.get("title"))}',
             'authors: [' + ', '.join(yaml_str(a) for a in authors[:30]) + (', "et al."' if len(authors) > 30 else '') + ']',
             f'year: {year_in(entry)}', f'journal: {yaml_str(container(entry))}', f'doi: {entry.get("DOI", "")}',
             f'pmid: {entry.get("PMID", "")}', f'pmcid: {entry.get("PMCID", "")}', f'license: {yaml_str(license)}',
             f'text_source: {yaml_str(source)}', '---', '']
    return '\n'.join(lines)


def read_text(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def write_markdown(entry, body, source, license=None, lit=None):
    """Write <key>.md: YAML header, '# title', body. An existing file keeps its header and title line, with
    text_source, pmid and pmcid brought up to date from the entry, and the licence when one is given; a new
    file gets a header built from the entry."""
    path = os.path.join(lit or LIT, entry['id'] + '.md')
    old = read_text(path) if os.path.exists(path) else ''
    m = HEADER_RE.match(old)
    if m:
        fields = {'pmid': entry.get('PMID', ''), 'pmcid': entry.get('PMCID', ''), 'text_source': yaml_str(source)}
        if license is not None:
            fields['license'] = yaml_str(license)
        head = set_header_fields(m.group(0), fields)
        first = old[m.end():].split('\n', 1)[0]
        title_line = first if first.startswith('# ') else '# ' + entry.get('title', '')
    else:
        head, title_line = front_matter(entry, source, license or ''), '# ' + entry.get('title', '')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(head + title_line + '\n\n' + body.strip() + '\n')


def summary_body(entry):
    """(body, text_source) of a Markdown with neither full text nor abstract: the summary written for the
    work, otherwise the metadata only."""
    if project(entry).get('summary'):
        return '## Summary\n\n' + project(entry)['summary'], 'summary only (written for the project)'
    return '', 'metadata only (full text and abstract not retrieved)'


# What a <key>.md can hold, as the start of its text_source.
HELD = ('full text', 'abstract only', 'summary only', 'metadata only')


# Markdown made from a source the library no longer stores (JATS XML, a saved web page): rewriting it
# from the PDF or the abstract would lose text, so it is kept unless md --force is given.
IRREPLACEABLE = ('full text, JATS XML', 'full text, article web page')


def full_text_here(key, lit=None):
    """True if the library folder holds the full text of a work: <key>.pdf, or a <key>.md whose header says
    it holds the full text (one made from JATS XML or a web page has no PDF). Decided from the files, which
    are the only witness of what one machine holds."""
    lit = lit or LIT
    if os.path.exists(os.path.join(lit, key + '.pdf')):
        return True
    md = os.path.join(lit, key + '.md')
    return os.path.exists(md) and header_value(read_text(md), 'text_source').startswith('full text')


def text_held(key, lit=None):
    """What the folder holds of a work: 'full text', 'abstract only', 'summary only', 'metadata only', or
    'none' when it has no Markdown and no PDF."""
    lit = lit or LIT
    if full_text_here(key, lit):
        return 'full text'
    md = os.path.join(lit, key + '.md')
    if not os.path.exists(md):
        return 'none'
    src = header_value(read_text(md), 'text_source')
    return next((h for h in HELD if src.startswith(h)), 'metadata only')


def apply_retrieval(entry, rec, note=None):
    """Bring an entry's identifiers and its Markdown up to date with what retrieve() found: the full text when
    a copy was found (JATS preferred, the PDF when the XML is thin), otherwise the abstract, otherwise the
    summary (a --note becomes the summary) or the metadata. A Markdown that already holds the abstract is
    kept. The licence goes into the Markdown's header. Returns what the Markdown now holds (its text_source)."""
    key = entry['id']
    for var, col in (('PMID', 'pmid'), ('PMCID', 'pmcid')):
        if rec.get(col) and not entry.get(var):
            entry[var] = str(rec[col])
    lic = normalise_license(rec.get('license') or '')
    path = os.path.join(LIT, key + '.md')
    if rec['pdf'] or rec['jats']:
        pdf = os.path.join(LIT, key + '.pdf')
        if rec['jats']:
            body, source = jats_to_md(rec['jats']), f'full text, JATS XML ({rec["xml"]})'
            if len(body) < 2000 and os.path.exists(pdf):
                body, source = pdf_to_md(pdf), f'full text, PDF ({rec["pdf"]})'
        else:
            body, source = pdf_to_md(pdf), f'full text, PDF ({rec["pdf"]})'
        write_markdown(entry, body, source, lic)
        if note:
            say(f'  --note not used: {key} has its full text')
        return source
    old = header_value(read_text(path), 'text_source') if os.path.exists(path) else ''
    if old.startswith('abstract only'):
        if note:
            say(f'  --note not used: {key} has an abstract')
        return old
    abstract, src = choose_abstract(entry['DOI'], rec) if entry.get('DOI') else (None, None)
    if abstract:
        write_markdown(entry, '## Abstract\n\n' + abstract, f'abstract only, from {src} (full text not retrieved)', lic)
        if note:
            say(f'  --note not used: {key} has an abstract')
    else:
        if note:
            entry.setdefault('custom', {})['summary'] = note
        write_markdown(entry, *summary_body(entry), lic)
    return header_value(read_text(path), 'text_source')


def print_tried(rec):
    for what, outcome in rec['tried']:
        say(f'    {what}: {outcome}')


# ====================================================================== add
def cmd_add(args):
    """Add one work by its DOI."""
    entries = read_entries()
    doi = clean_doi(args.doi)
    if not doi:
        raise Refused(f'not a DOI: {args.doi}')
    same = [e['id'] for e in entries if doi_of(e) == doi]
    if same:
        raise Refused(f'{doi} is already in the library as {same[0]}')
    if args.pdf and not os.path.isfile(args.pdf):
        raise Refused(f'no such file: {args.pdf}')
    meta = crossref(doi) or epmc_meta(doi)
    if not meta:
        if {'crossref', 'epmc'} <= FAILED:
            raise Unreachable(f'{doi}: neither Crossref nor Europe PMC answered')
        raise Refused(f'{doi}: not found on Crossref or Europe PMC')
    if args.title and not title_accepted(meta, args.title):
        raise Refused(f'{doi}: the registered title does not match the one given\n'
                      f'  registered: {full_title(meta)}\n  given:      {args.title}')
    taken = {e['id'] for e in entries}
    if args.key and args.key in taken:
        raise Refused(f'the key {args.key} is already in the library')
    key = args.key or make_key(meta, taken, key_style(entries))
    entry = entry_from_meta(key, doi, meta)
    if args.cited_in:
        entry['custom'] = {'cited_in': args.cited_in}
    say(f'{key}: {entry["title"]} ({names_line(entry)}, {year_in(entry)})')
    notice = retraction(meta)
    if notice:
        say(f'  Crossref records an update to this work: {notice}')

    rec = new_record()
    if args.pdf:                                # a PDF supplied by hand wins over every other source
        with open(args.pdf, 'rb') as f:
            if not save_pdf(f.read(), key, entry['title'], 'supplied by hand', rec):
                say(f'  {args.pdf} not filed ({rec["tried"][-1][1]}); if it is this paper, copy it as '
                    f'{key}.pdf into the library and run: literature.py md {key}')
    retrieve(doi, key, entry['title'], first_family(entry), rec)
    text = apply_retrieval(entry, rec, note=args.note)
    entries.append(entry)
    write_entries(entries)
    print_tried(rec)
    say(f'{key}: added; {text}; open-access status {rec["oa_status"] or "unknown"}')
    return 0, {'added': canonical(entry), 'text': text, 'oa_status': rec['oa_status'], 'update_notice': notice,
               'tried': rec['tried']}


# ====================================================================== fetch
def cmd_fetch(args):
    """Retry the open-access sources for works whose full text is not in the folder (all of them, or the
    keys given), writing the full text or the abstract into their Markdown. The folder decides what is
    missing, so that in a fresh clone, which has the record and none of the files, fetch downloads the
    open-access copies again and writes every Markdown."""
    entries = read_entries()
    by_key = {e['id']: e for e in entries}
    unknown = [k for k in args.keys if k not in by_key]
    if unknown:
        raise Refused('unknown keys: ' + ', '.join(unknown))
    targets = [by_key[k] for k in args.keys] if args.keys else \
        [e for e in entries if e.get('DOI') and not full_text_here(e['id'])]
    results = []
    for i, entry in enumerate(targets, 1):
        key = entry['id']
        if not entry.get('DOI'):
            say(f'{key}: no DOI, nothing to search')
            continue
        if full_text_here(key):
            say(f'{key}: already has its full text')
            continue
        rec = retrieve(entry['DOI'], key, entry['title'], first_family(entry), new_record())
        text = apply_retrieval(entry, rec)
        write_entries(entries)                  # after every work, so an interruption loses nothing
        ok = bool(rec['pdf'] or rec['jats'])
        say(f'{i}/{len(targets)} {key}: {"full text found" if ok else "no free copy"}')
        if not ok:
            print_tried(rec)
        results.append({'id': key, 'full_text': ok, 'text': text, 'oa_status': rec['oa_status'],
                        'tried': rec['tried']})
    found = [r['id'] for r in results if r['full_text']]
    say(f'done: {len(found)} new full texts', found)
    return 0, {'results': results, 'found': found}


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
    it is. Files that fail stay where they are and are reported. The record does not change: only the
    folder does."""
    entries = read_entries()
    by_key = {e['id']: e for e in entries}
    by_doi = {doi_of(e): e['id'] for e in entries if doi_of(e)}

    def has_pdf(k):
        return os.path.exists(os.path.join(LIT, k + '.pdf'))

    # candidates for identification by title: works without a PDF whose title is long enough to be distinctive
    missing = [k for k, e in by_key.items()
               if not has_pdf(k) and len(re.findall(r'[a-z0-9]+', fold(e.get('title')))) >= 5]
    moved, rejected = [], []
    for name in sorted(os.listdir(args.src)):
        key, ext = os.path.splitext(name)
        ext = ext.lower()
        if ext not in ('.pdf', '.html') or (ext == '.html' and key not in by_key):
            continue
        src = os.path.join(args.src, name)
        if ext == '.html':                      # article page saved from the browser
            entry = by_key[key]
            if full_text_here(key):
                continue
            text = read_text_lenient(src)
            score = pairs_found(entry['title'], re.sub(r'<[^>]+>', ' ', text))
            if score < 0.6:
                rejected.append((name, f'title match {score:.2f}'))
                continue
            write_markdown(entry, html_to_md(src), 'full text, article web page (browser)')
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
        entry = by_key[key]
        score = pairs_found(entry['title'], text)
        if score < 0.6 or pages <= 2:
            rejected.append((name, f'title match {score:.2f}, {pages} pages'))
            continue
        shutil.move(src, os.path.join(LIT, key + '.pdf'))
        md = os.path.join(LIT, key + '.md')
        src_md = header_value(read_text(md), 'text_source') if os.path.exists(md) else ''
        if not src_md.startswith(IRREPLACEABLE):   # a Markdown from JATS or a web page is better: keep it
            write_markdown(entry, pdf_to_md(os.path.join(LIT, key + '.pdf')), 'full text, PDF (browser (user session))')
        moved.append(f'{name} -> {key}.pdf')
    say('filed', len(moved))
    for m in moved:
        say('  ' + m)
    for n, why in rejected:
        say('REJECTED', n, why)
    return 0, {'filed': moved, 'rejected': [list(r) for r in rejected]}


def read_text_lenient(path):
    with open(path, encoding='utf-8', errors='replace') as f:
        return f.read()


# ====================================================================== md
def cmd_md(args):
    """(Re)write Markdown files from the PDFs. With keys: those works. Without: every work whose Markdown is
    missing, or stale next to its PDF (it holds less than the full text, or is older than the PDF). A work
    without a PDF gets a missing Markdown from its summary or its metadata and keeps an existing one, which
    may hold the abstract fetch found. A Markdown made from JATS XML or a web page is kept unless --force is
    given, because its source is no longer stored. The record does not change."""
    entries = read_entries()
    by_key = {e['id']: e for e in entries}
    unknown = [k for k in args.keys if k not in by_key]
    if unknown:
        raise Refused('unknown keys: ' + ', '.join(unknown))
    written, kept = [], []
    for entry in ([by_key[k] for k in args.keys] if args.keys else entries):
        key = entry['id']
        pdf, md = os.path.join(LIT, key + '.pdf'), os.path.join(LIT, key + '.md')
        src = header_value(read_text(md), 'text_source') if os.path.exists(md) else ''
        if src.startswith(IRREPLACEABLE) and not args.force:
            kept.append(key)
            if args.keys:
                say(f'{key}: kept, its Markdown comes from {src.split(" (")[0][len("full text, "):]} (use --force to rewrite it)')
            continue
        if os.path.exists(pdf):
            if not args.keys and os.path.exists(md) and src.startswith('full text') \
                    and os.path.getmtime(md) >= os.path.getmtime(pdf):
                kept.append(key)
                continue
            m = re.match(r'full text, PDF \((.*)\)$', src)
            write_markdown(entry, pdf_to_md(pdf), f'full text, PDF ({m.group(1) if m else "source not recorded"})')
        elif not os.path.exists(md):
            write_markdown(entry, *summary_body(entry))
        else:
            kept.append(key)
            if args.keys:
                say(f'{key}: no PDF, its Markdown is kept (fetch looks for the text again)')
            continue
        written.append(key)
    say(f'written {len(written)}: {", ".join(written)} | kept {len(kept)}')
    return 0, {'written': written, 'kept': kept}


# ====================================================================== check
def check_problems(lit=None):
    """Problems of the record and of its agreement with the files of the library folder: the record's layout,
    duplicate ids or DOIs, types outside the CSL list, entries without a title, works without their Markdown,
    Markdown headers naming another key, files no entry names. Returns (problems, entries)."""
    lit = lit or LIT
    path = os.path.join(lit, RECORD)
    entries = read_entries(path)
    problems = []
    with open(path, encoding='utf-8') as f:     # line ends are left to git (CRLF in a Windows checkout)
        if f.read() != dump(entries):
            problems.append(f'{RECORD} is not in the script\'s layout (order of entries or fields, indentation): '
                            'check --fix rewrites it')
    for label, values in (('id', [e['id'] for e in entries]), ('DOI', [doi_of(e) for e in entries if doi_of(e)])):
        problems += [f'duplicate {label}: {v} ({n} entries)'
                     for v, n in sorted(collections.Counter(values).items()) if n > 1]
    for e in entries:
        if e.get('type') not in CSL_TYPES:
            problems.append(f'{e["id"]}: the type "{e.get("type", "")}" is not a CSL type')
        if not e.get('title'):
            problems.append(f'{e["id"]}: no title')
    names = set(os.listdir(lit))
    described = {RECORD}
    without_md = []
    for e in entries:
        key = e['id']
        described |= {key + '.pdf', key + '.md'} & names
        if key + '.md' not in names:
            without_md.append(key)
            continue
        named = header_value(read_text(os.path.join(lit, key + '.md')), 'key')
        if named != key:
            problems.append(f'{key}: the header of {key}.md names the key "{named}"')
    # A fresh clone receives the record without the files: one line with the remedy, not a line per work.
    if without_md:
        who = ('none of the works has its Markdown here, as in a fresh clone' if len(without_md) == len(entries)
               else 'no Markdown for ' + ', '.join(without_md))
        problems.append(f'{who}: fetch writes the text of the works with a DOI, md that of the others (from a PDF, '
                        'the summary or the metadata), and collect files the copies downloaded in the browser')
    if LEGACY in names:
        described.add(LEGACY)
        problems.append(f'{LEGACY}, the older record, is still in the folder: {RECORD} replaces it, so it can be '
                        'deleted')
    for n in sorted(names - described):
        kind = 'subfolder' if os.path.isdir(os.path.join(lit, n)) else 'file'
        problems.append(f'{kind} not named by any entry of the record: {n}')
    return problems, entries


def cmd_check(args):
    if args.fix:
        write_entries(read_entries())
    problems, entries = check_problems()
    for p in problems:
        say('PROBLEM', p)
    held = collections.Counter(text_held(e['id']) for e in entries)
    say(f'{len(entries)} works (' + ', '.join(f'{n} {h}' for h, n in held.most_common()) + '): '
        + (f'{len(problems)} problems' if problems else 'consistent'))
    return (1 if problems else 0), {'works': len(entries), 'held': dict(held), 'problems': problems}


# ====================================================================== list
LIST_COLUMNS = ['id', 'authors', 'year', 'title', 'source', 'type', 'doi', 'pmid', 'pmcid', 'url', 'cited_in',
                'summary', 'pdf', 'text']


def cmd_list(args):
    """Each work (or the keys given) with the text the folder holds for it; --csv writes the same table as a
    CSV file (UTF-8 with a byte order mark, which spreadsheets need to read the accents)."""
    entries = read_entries()
    by_key = {e['id']: e for e in entries}
    unknown = [k for k in args.keys if k not in by_key]
    if unknown:
        raise Refused('unknown keys: ' + ', '.join(unknown))
    chosen = [by_key[k] for k in args.keys] if args.keys else sorted(entries, key=sort_key)
    rows = [{'id': e['id'], 'authors': names_line(e), 'year': year_in(e), 'title': e.get('title', ''),
             'source': container(e), 'type': e.get('type', ''), 'doi': e.get('DOI', ''), 'pmid': e.get('PMID', ''),
             'pmcid': e.get('PMCID', ''), 'url': e.get('URL', ''), 'cited_in': project(e).get('cited_in', ''),
             'summary': project(e).get('summary', ''), 'pdf': os.path.exists(os.path.join(LIT, e['id'] + '.pdf')),
             'text': text_held(e['id'])} for e in chosen]
    if args.csv:
        with open(args.csv, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=LIST_COLUMNS)
            writer.writeheader()
            writer.writerows(dict(r, pdf='yes' if r['pdf'] else 'no') for r in rows)
        say(f'{len(rows)} works written to {args.csv}')
    else:
        for r in rows:
            say(f'{r["id"]}  [{r["text"]}{", PDF" if r["pdf"] else ""}]  {r["authors"]} ({r["year"] or "n.d."}) '
                f'{r["title"][:90]}')
    return 0, {'works': rows}


# ====================================================================== convert (from the older CSV)
# The kind labels of the older record as CSL types; a label not listed becomes a document.
LEGACY_TYPE = {
    'journal article': 'article-journal', 'journal article (no DOI)': 'article-journal', 'preprint': 'article',
    'book': 'book', 'book chapter': 'chapter', 'conference paper': 'paper-conference',
    'conference paper (no DOI)': 'paper-conference', 'report': 'report', 'statistics report': 'report',
    'fact sheet': 'report', 'web page': 'webpage', 'statistics page': 'webpage', 'statistics table': 'dataset',
    'dataset': 'dataset', 'dictionary entry': 'entry-dictionary', 'reference entry': 'entry-encyclopedia',
    'news': 'article-newspaper', 'news (series)': 'article-newspaper', 'news (radio)': 'broadcast',
    'legislation': 'legislation', 'legal document': 'legal_case', 'presentation': 'speech',
    'software (online calculator)': 'software'}


def entry_from_row(row):
    """An entry from a row of the older bibliography.csv, with no network call: the fields that identify and
    cite the work, cited_in, and the description written for a work without an abstract. The authors come from
    authors_full, 'Family, Given; Family, Given' as Crossref gave them, where a name without a comma is one
    literal name (an organisation); a row without authors_full keeps its authors column as one literal name."""
    typ = LEGACY_TYPE.get(row.get('kind') or '', 'document')
    e = {'id': row['key'], 'type': typ, 'title': row.get('title') or ''}
    if row.get('authors_full'):
        e['author'] = []
        for a in row['authors_full'].split('; '):
            fam, _, given = a.partition(', ')
            if fam:
                e['author'].append({'family': fam, 'given': given} if given else {'literal': fam})
    elif row.get('authors'):
        e['author'] = [{'literal': row['authors']}]
    if re.fullmatch(r'\d{4}', row.get('year') or ''):
        e['issued'] = {'date-parts': [[int(row['year'])]]}
    if row.get('source'):
        e['container-title' if typ in CONTAINER else 'publisher'] = row['source']
    for col, var in (('volume', 'volume'), ('issue', 'issue'), ('pages', 'page'), ('doi', 'DOI'),
                     ('pmid', 'PMID'), ('pmcid', 'PMCID')):
        if row.get(col):
            e[var] = row[col]
    if row.get('url') and not row.get('doi'):
        e['URL'] = row['url']
    c = {}
    if row.get('cited_in'):
        c['cited_in'] = row['cited_in']
    if row.get('abstract_or_summary') and row.get('text_type') != 'abstract':
        c['summary'] = row['abstract_or_summary']
    if c:
        e['custom'] = c
    return e


def cmd_convert(args):
    """Turn the older bibliography.csv into bibliography.json, once, with no network call, so that no correction
    made by hand is lost. Each abstract of the CSV moves into its <key>.md when that file is missing or holds
    the metadata only; a work still without a Markdown gets one from its summary or its metadata. A Markdown
    whose header does not say what it holds is left as it is. The columns
    that described one machine (full_text, pdf, md, access) and what a source can give again (licence, update
    notices) are not carried over; the licence of a moved abstract goes into its Markdown's header. .gitignore
    follows, and the CSV is deleted."""
    src, dst = os.path.join(LIT, LEGACY), os.path.join(LIT, RECORD)
    if os.path.exists(dst):
        raise Refused(f'{dst} already exists: nothing to convert')
    if not os.path.exists(src):
        raise Refused(f'{LIT} holds no {LEGACY}')
    with open(src, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    dup = sorted(k for k, n in collections.Counter(r.get('key') for r in rows).items() if n > 1)
    if dup or any(not r.get('key') for r in rows):
        raise Refused(f'{LEGACY} has rows without a key or with the same key: {", ".join(map(str, dup))}; '
                      'fix them first')
    entries = [entry_from_row(r) for r in rows]
    moved, written = [], []
    for r, e in zip(rows, entries):
        md = os.path.join(LIT, e['id'] + '.md')
        old = header_value(read_text(md), 'text_source') if os.path.exists(md) else ''
        if os.path.exists(md) and not old.startswith('metadata only'):
            continue                            # the full text or the abstract, or a text of unknown origin
        if r.get('text_type') == 'abstract' and r.get('abstract_or_summary'):
            write_markdown(e, '## Abstract\n\n' + r['abstract_or_summary'],
                           f'abstract only, from {r.get("text_source") or "a source not recorded"} '
                           '(full text not retrieved)', normalise_license(r.get('license') or ''))
            moved.append(e['id'])
        elif not old or project(e).get('summary'):
            write_markdown(e, *summary_body(e), normalise_license(r.get('license') or ''))
            written.append(e['id'])
    write_entries(entries, dst)
    gitignore = ensure_gitignore(LIT)
    os.remove(src)
    as_document = sorted({r['kind'] for r, e in zip(rows, entries) if e['type'] == 'document' and r.get('kind')})
    to_split = [e['id'] for e in entries if len(e.get('author') or []) == 1
                and ', ' in e['author'][0].get('literal', '')]
    say(f'{len(entries)} entries written to {dst}; {LEGACY} deleted')
    say(f'  abstracts moved into their Markdown: {len(moved)}; Markdown written from a summary or the metadata: '
        f'{len(written)}')
    if gitignore:
        say('  .gitignore gains: ' + ', '.join(gitignore))
    if as_document:
        say('  kinds recorded as the CSL type document: ' + ', '.join(as_document))
    if to_split:
        say('  one literal author that may be a list of persons, to split into names by hand: ' + ', '.join(to_split))
    return 0, {'entries': len(entries), 'abstracts_moved': moved, 'markdown_written': written,
               'gitignore': gitignore, 'as_document': as_document, 'authors_to_split': to_split}


# ====================================================================== the library folder
def git_root(start):
    """The root of the git repository holding `start`, or None outside a repository."""
    here = pathlib.Path(start).resolve()
    for d in [here, *here.parents]:
        if (d / '.git').exists():
            return d
    return None


def find_library(start):
    """The library folder: literature/ or docs/literature/ holding bibliography.json (or the older
    bibliography.csv, for convert), in `start` or one of its parents up to the repository root (so the script
    runs from anywhere inside the project). None when the project has no library yet."""
    here = pathlib.Path(start).resolve()
    top = git_root(here)

    def holds(d):
        return (d / RECORD).is_file() or (d / LEGACY).is_file()

    for d in [here, *here.parents]:
        if d.name == 'literature' and holds(d):
            return str(d)
        for cand in (d / 'literature', d / 'docs' / 'literature'):
            if holds(cand):
                return str(cand)
        if top is not None and d == top:
            break
    return None


def ensure_gitignore(lib):
    """The lines of the repository's .gitignore that keep every file of the library local except the record,
    added when missing; a line that kept the older bibliography.csv is turned into the record's. The file keeps
    its line ends (LF or CRLF). Returns the lines added or changed."""
    top = git_root(lib)
    if top is None:
        return []
    rel = pathlib.Path(lib).resolve().relative_to(top).as_posix()
    gi = top / '.gitignore'
    text = gi.read_bytes().decode('utf-8') if gi.exists() else ''
    nl = '\r\n' if '\r\n' in text else '\n'
    lines = text.splitlines()
    old, changed = f'!{rel}/{LEGACY}', []
    if old in lines:
        lines = [f'!{rel}/{RECORD}' if x == old else x for x in lines]
        changed.append(f'!{rel}/{RECORD}')
    added = [w for w in (f'{rel}/*', f'!{rel}/{RECORD}') if w not in lines]
    if changed or added:
        gi.write_text(nl.join(lines + added) + nl, encoding='utf-8', newline='')
    return changed + added


def create_library(lib):
    """A new, empty library: the folder, an empty record, and the .gitignore lines of the repository that keep
    every file of the folder local except the record. Returns the lines added."""
    os.makedirs(lib, exist_ok=True)
    write_entries([], os.path.join(lib, RECORD))
    return ensure_gitignore(lib)


def set_library(lib_arg, command, cwd=None):
    """Set LIT for this run: --lib when given, else the library found from the working directory. The
    first add in a project without a library creates literature/ at the repository root; a library that
    still holds the older bibliography.csv is refused with the line naming convert."""
    global LIT
    cwd = cwd or os.getcwd()
    lib = os.path.abspath(lib_arg) if lib_arg else find_library(cwd)
    if lib is None:
        if command != 'add':
            raise Refused('no library here: no literature/ or docs/literature/ with bibliography.json from this '
                          'folder up to the repository root (give --lib, or add a first work to create one)')
        lib = str((git_root(cwd) or pathlib.Path(cwd)) / 'literature')
    if command != 'convert' and not os.path.isfile(os.path.join(lib, RECORD)):
        if os.path.isfile(os.path.join(lib, LEGACY)):
            raise Refused(f'{lib} holds {LEGACY}, the older record: run `literature.py convert` once to turn it '
                          f'into {RECORD}')
        if command != 'add':
            raise Refused(f'{lib} holds no {RECORD}')
        added = create_library(lib)
        say(f'new library at {lib}' + (f'; .gitignore gains: {", ".join(added)}' if added else ''))
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
    p.add_argument('--json', action='store_true',
                   help='print one JSON object on standard output; the messages go to standard error')
    sub = p.add_subparsers(dest='command', required=True)
    a = sub.add_parser('add', help='add a work by its DOI')
    a.add_argument('--key', help='the key to use instead of the one the library would make')
    a.add_argument('doi', help='the DOI, bare or as a doi.org link')
    a.add_argument('--title', help='the title as cited: the DOI is refused if its registered title does not match')
    a.add_argument('--cited-in', default='', help='where the work is cited (custom.cited_in)')
    a.add_argument('--note', help='a short description, kept as custom.summary when no abstract is found')
    a.add_argument('--pdf', help='a PDF of the work (copied into the library if its title checks out)')
    f = sub.add_parser('fetch', help='retry the open-access sources for works whose full text is not in the folder')
    f.add_argument('keys', nargs='*', help='keys to retry (default: every work with a DOI and no full text in the folder)')
    c = sub.add_parser('collect', help='file the PDFs downloaded by hand')
    c.add_argument('--from', dest='src', default=DOWNLOADS, help='folder to look in (default: %(default)s)')
    m = sub.add_parser('md', help='write <key>.md again from the PDF, or a missing one from the summary or metadata')
    m.add_argument('keys', nargs='*', help='keys (default: every missing or stale Markdown)')
    m.add_argument('--force', action='store_true',
                   help='also rewrite Markdown made from JATS XML or a web page (their source is not stored)')
    k = sub.add_parser('check', help='the record and its agreement with the files; exit code 1 on problems')
    k.add_argument('--fix', action='store_true', help="first rewrite the record in the script's layout")
    ls = sub.add_parser('list', help='each work with the text the folder holds for it')
    ls.add_argument('keys', nargs='*', help='keys (default: every work)')
    ls.add_argument('--csv', metavar='PATH', help='write the table to this CSV file, for a spreadsheet, R or Python')
    sub.add_parser('convert', help='turn the older bibliography.csv into bibliography.json, once, offline')
    args = p.parse_args(argv)
    global ARCHIVE, JSON
    ARCHIVE = os.path.abspath(args.archive) if args.archive else None
    JSON = args.json
    commands = {'add': cmd_add, 'fetch': cmd_fetch, 'collect': cmd_collect, 'md': cmd_md,
                'check': cmd_check, 'list': cmd_list, 'convert': cmd_convert}
    try:
        set_library(args.lib, args.command)
        code, result = commands[args.command](args)
    except (Refused, Unreachable) as e:
        code, result = (2 if isinstance(e, Refused) else 3), {'error': str(e)}
        print(e, file=sys.stderr)
    if JSON:
        print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == '__main__':
    sys.exit(main())
