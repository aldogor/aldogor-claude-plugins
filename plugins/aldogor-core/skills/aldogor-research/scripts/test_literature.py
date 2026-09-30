"""Tests for literature.py: its pure functions, the record, the library folder and the commands, on the fixtures
in fixtures/ (fictitious works, DOIs under Crossref's test prefix 10.5555). No network: the commands run with
retrieve() and the metadata sources replaced by stand-ins.

Run with: python -m pytest <this folder>
"""
import argparse
import csv
import json
import os
import shutil
import sys

import pymupdf
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import literature as lit  # noqa: E402


# ---------------------------------------------------------------- key rule
def meta(family='Alonzo', year=2021, title='Interplay between social media use, sleep quality, and mental health'):
    m = {'title': [title]}
    if family:
        m['author'] = [{'family': family, 'given': 'Rea'}]
    if year:
        m['issued'] = {'date-parts': [[year]]}
    return m


def test_key_is_family_year_first_significant_word():
    assert lit.make_citekey(meta(), set()) == 'alonzo2021interplay'


def test_key_skips_english_and_italian_stop_words():
    assert lit.make_citekey(meta(title='The effects of limits'), set()) == 'alonzo2021effects'
    assert lit.make_citekey(meta(title='Il benessere digitale'), set()) == 'alonzo2021benessere'


def test_key_folds_accents_and_drops_non_letters():
    assert lit.make_citekey(meta(family='Plöderl'), set()) == 'ploderl2021interplay'
    assert lit.make_citekey(meta(family="O'Brien-Smith"), set()) == 'obriensmith2021interplay'


def test_key_without_year_and_without_author():
    assert lit.make_citekey(meta(year=None), set()) == 'alonzondinterplay'
    no_author = {'title': ['Diagnostic manual'], 'publisher': 'American Psychiatric Association',
                 'issued': {'date-parts': [[2022]]}}
    assert lit.make_citekey(no_author, set()) == 'association2022diagnostic'


def test_key_collision_gets_b_then_c():
    assert lit.make_citekey(meta(), {'alonzo2021interplay'}) == 'alonzo2021interplayb'
    assert lit.make_citekey(meta(), {'alonzo2021interplay', 'alonzo2021interplayb'}) == 'alonzo2021interplayc'


def test_key_is_cut_at_40_characters():
    key = lit.make_citekey(meta(family='Averyveryverylongfamilynamewithoutend', title='Supercalifragilistic'), set())
    assert len(key) == 40


# ---------------------------------------------------------------- DOIs
@pytest.mark.parametrize('text, doi', [
    ('see https://doi.org/10.1016/J.SMRV.2020.101414.', '10.1016/j.smrv.2020.101414'),
    ('doi: 10.1089/cyber.2018.0070)', '10.1089/cyber.2018.0070'),
    ('https://onlinelibrary.wiley.com/doi/10.1111/add.12345/full', '10.1111/add.12345'),
    ('Journal 2020;12:1-10. DOI 10.3390/brainsci13050787, published', '10.3390/brainsci13050787'),
    ('no identifier on this page', None),
])
def test_find_doi(text, doi):
    assert lit.find_doi(text) == doi


def test_clean_doi_prefixes_and_non_dois():
    assert lit.clean_doi('https://dx.doi.org/10.1000/ABC') == '10.1000/abc'
    assert lit.clean_doi('doi:10.1000/abc;') == '10.1000/abc'
    assert lit.clean_doi('PMC123456') is None
    assert lit.clean_doi('') is None


# ---------------------------------------------------------------- title matching
def test_tokens_normalise_spelling_variants():
    assert lit.tokens('Behaviour meta-analysis Effects') == lit.tokens('behavior metaanalysis effect')


def test_containment_and_pair_containment():
    title = 'Social media addiction and psychological distress'
    assert lit.containment(title, 'a study of social media addiction and psychological distress in adults') == 1.0
    # the same words in another order: every word is there, few of the word pairs are
    shuffled = 'distress psychological and addiction media social'
    assert lit.containment(title, shuffled) == 1.0
    assert lit.pair_containment(title, shuffled) < 0.5


def test_title_accepted_rule():
    m = {'title': ['A week without using social media'], 'subtitle': ['results from an ecological momentary study']}
    assert lit.title_accepted(m, 'A Week Without Using Social Media: Results from an Ecological Momentary Study')
    assert lit.title_accepted(m, 'A week without using social media')          # subtitle dropped in the citation
    assert not lit.title_accepted(m, 'Problematic smartphone use in adolescents')
    short = {'title': ['The PHQ-9']}
    assert lit.title_accepted(short, 'The PHQ-9: validity of a brief depression severity measure')


def test_pairs_found_joins_line_end_hyphens():
    title = 'Fear of missing out and problematic social media use'
    page = 'Journal of X\nFear of missing out and problem-\natic social media use\nAbstract'
    assert lit.pairs_found(title, page) == 1.0
    assert lit.pairs_found(title, 'An unrelated paper on sleep') == 0.0


def make_pdf(text):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(50, 50, 550, 800), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def test_pdf_matches_title_on_first_page():
    title = 'Screen time limits and social media addiction in university students'
    pdf = make_pdf(f'Journal of Studies\n{title}\nA. Author, B. Author\nAbstract: we studied ...')
    assert lit.pdf_matches(pdf, title)
    assert not lit.pdf_matches(pdf, 'Sleep quality and depressive symptoms in older adults living alone')


def test_save_pdf_refuses_non_pdf_and_small_files(tmp_path):
    rec = lit.new_record()
    assert not lit.save_pdf(b'<html>just a moment</html>', 'k', 'Any title here', 'http://x', rec, lit=str(tmp_path))
    assert rec['tried'][-1] == ['http://x', 'not a pdf']
    assert not os.listdir(tmp_path)


# ---------------------------------------------------------------- hosts and anti-bot pages
@pytest.mark.parametrize('url, blocked', [
    ('https://www.sciencedirect.com/science/article/pii/S0747563213000800', True),
    ('https://pdf.sciencedirectassets.com/271802/1-s2.0-S0.pdf', True),
    ('https://linkinghub.elsevier.com/retrieve/pii/S0747563213000800', True),
    ('https://onlinelibrary.wiley.com/doi/pdf/10.1111/add.12345', True),
    ('https://acamh.onlinelibrary.wiley.com/doi/10.1111/jcpp.1', True),
    ('https://unito.idm.oclc.org/login?url=https://x.org', True),
    ('https://europepmc.org/articles/PMC123', False),
    ('https://iris.unito.it/retrieve/handle/2318/1.pdf', False),
    ('https://www.mdpi.com/2076-3425/13/5/787/pdf', False),
])
def test_refused_hosts(url, blocked):
    assert lit.refused(url) is blocked


def test_redirect_to_refused_host_is_not_followed(monkeypatch):
    """A DOI link that redirects to ScienceDirect: the first hop is requested, the redirect never is."""
    calls = []

    class Redirect:
        status_code, is_redirect = 302, True

        def __init__(self, url):
            self.url, self.headers = url, {'location': 'https://www.sciencedirect.com/science/article/pii/X'}

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, url, **kw):
            calls.append(url)
            return Redirect(url)

    monkeypatch.setattr(lit.requests, 'Session', FakeSession)
    assert lit.get('https://doi.org/10.1016/x', 'doi', lit.Throttle(0)) is None
    assert calls == ['https://doi.org/10.1016/x']
    assert lit.download('https://onlinelibrary.wiley.com/doi/pdf/10.1111/x')[0] is None
    assert calls == ['https://doi.org/10.1016/x']            # a refused host is not even requested


class FakeResponse:
    def __init__(self, status=200, ctype='text/html', text='', content=b'x'):
        self.status_code, self.headers, self.text, self.content = status, {'content-type': ctype}, text, content


def test_challenged_pages():
    assert lit.challenged(FakeResponse(text='<title>Just a moment...</title>'))
    assert lit.challenged(FakeResponse(text='<p>Oh noes! Anubis is checking</p>'))
    assert lit.challenged(FakeResponse(status=202, content=b''))                       # AWS WAF
    assert not lit.challenged(FakeResponse(ctype='application/pdf', text='just a moment'))
    assert not lit.challenged(FakeResponse(text='<h1>Article</h1>'))
    assert not lit.challenged(None)


# ---------------------------------------------------------------- licences
@pytest.mark.parametrize('raw, norm', [
    ('cc-by', 'CC BY'), ('cc by', 'CC BY'), ('CC BY', 'CC BY'),
    ('cc-by-nc', 'CC BY-NC'), ('cc by-nc', 'CC BY-NC'),
    ('cc-by-nc-nd', 'CC BY-NC-ND'), ('cc by-nc-nd', 'CC BY-NC-ND'), ('cc by-nc-sa', 'CC BY-NC-SA'),
    ('TDM', 'TDM'), ('public-domain', 'public-domain'), ('other-oa', 'other-oa'), ('', ''),
])
def test_normalise_license(raw, norm):
    assert lit.normalise_license(raw) == norm



# ---------------------------------------------------------------- the record
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')


def fixture_entries():
    """The fixture record: an article with every identifier, an Italian article carrying a field (editor) and a
    custom key (screening) the script does not manage, a report by an organisation with a summary, a web page."""
    return lit.read_entries(os.path.join(FIXTURES, lit.RECORD))


def by_id(entries):
    return {e['id']: e for e in entries}


def test_the_fixture_record_is_in_the_scripts_layout():
    with open(os.path.join(FIXTURES, lit.RECORD), encoding='utf-8') as f:
        assert f.read() == lit.dump(fixture_entries())


def test_record_layout_order_and_fields_the_script_does_not_manage(tmp_path):
    path = str(tmp_path / lit.RECORD)
    entries = [
        {'custom': {'screening': 'include', 'cited_in': 'ch. 2'}, 'title': 'Zeta', 'id': 'zeta2020', 'type': 'report',
         'volume': '', 'note': 'kept as found'},
        {'id': 'Alpha_2021', 'type': 'article-journal', 'title': 'Città e salute', 'custom': {'summary': ''}},
    ]
    lit.write_entries(entries, path)
    with open(path, 'rb') as f:
        raw = f.read()
    assert not raw.startswith(b'\xef\xbb\xbf') and b'\r\n' not in raw and raw.endswith(b']\n')
    assert 'Città'.encode('utf-8') in raw                           # characters as they are, not \u escapes
    got = lit.read_entries(path)
    assert [e['id'] for e in got] == ['Alpha_2021', 'zeta2020']     # sorted by id, case folded
    assert list(got[1]) == ['id', 'type', 'title', 'custom', 'note']  # managed fields in order, then the others
    assert got[1]['custom'] == {'cited_in': 'ch. 2', 'screening': 'include'}
    assert 'volume' not in got[1] and 'custom' not in got[0]        # empty managed values dropped
    lit.write_entries(got, path)                                    # a second pass changes nothing
    with open(path, 'rb') as f:
        assert f.read() == raw


def test_a_record_broken_by_a_merge_is_refused_with_its_line(tmp_path):
    path = tmp_path / lit.RECORD
    path.write_text('[\n<<<<<<< HEAD\n  {"id": "a"}\n=======\n  {"id": "b"}\n>>>>>>> other\n]\n', encoding='utf-8')
    with pytest.raises(lit.Refused, match='line 2'):
        lit.read_entries(str(path))
    path.write_text('[{"title": "no id"}]', encoding='utf-8')
    with pytest.raises(lit.Refused, match='each with an id'):
        lit.read_entries(str(path))


# ---------------------------------------------------------------- authors and entries from Crossref
def test_csl_names_from_crossref():
    m = {'author': [{'family': 'Alonzo', 'given': 'Rea'}, {'name': 'HBSC Group'}, {'family': '\nthe 2018 Group\n'},
                    {'family': 'Nawsherwan'}]}
    assert lit.csl_names(m) == [{'family': 'Alonzo', 'given': 'Rea'}, {'literal': 'HBSC Group'},
                                {'literal': 'the 2018 Group'}, {'literal': 'Nawsherwan'}]


def test_names_line_and_first_family():
    e = {'author': [{'family': 'Alonzo', 'given': 'Rea'}, {'family': 'Hussain', 'given': 'Junayd'},
                    {'family': 'Stranges', 'given': 'Saverio'}, {'family': 'Anderson', 'given': 'Kelly K.'}]}
    assert lit.names_line(e) == 'Alonzo R, Hussain J, Stranges S, et al.'
    assert lit.first_family(e) == 'Alonzo'
    assert lit.first_family({'author': [{'literal': 'World Health Organization'}]}) == 'World Health Organization'
    assert lit.names_line({}) == '' and lit.first_family({}) == ''
    edited = {'editor': [{'family': 'Rechel', 'given': 'Bernd'}, {'family': 'Maresso', 'given': 'Anna'}]}
    assert lit.names_line(edited) == 'Rechel B, Maresso A' and lit.first_family(edited) == 'Rechel'
    assert 'authors: ["Bernd Rechel", "Anna Maresso"]' in lit.front_matter(dict(edited, id='Rechel_2018'), 'x')


def test_entry_from_crossref_record():
    m = {'type': 'journal-article', 'title': ['Uso dei social media'], 'subtitle': ['uno studio di coorte'],
         'language': 'it', 'author': [{'family': 'Rossi', 'given': 'Maria'}], 'issued': {'date-parts': [[2024, 5, 2]]},
         'container-title': ['Rivista di Esempio'], 'publisher': 'Editore', 'volume': 3, 'page': '10-20'}
    e = lit.entry_from_meta('Rossi_2024', '10.5555/rossi', m)
    assert e == {'id': 'Rossi_2024', 'type': 'article-journal', 'title': 'Uso dei social media: uno studio di coorte',
                 'language': 'it', 'author': [{'family': 'Rossi', 'given': 'Maria'}],
                 'issued': {'date-parts': [[2024]]}, 'container-title': 'Rivista di Esempio', 'volume': '3',
                 'page': '10-20', 'DOI': '10.5555/rossi'}
    report = lit.entry_from_meta('X_2020', '10.5555/x', {'type': 'report', 'title': ['R'], 'publisher': 'WHO',
                                                          'language': 'en-GB', 'container-title': ['Series 4']})
    assert report['type'] == 'report' and report['publisher'] == 'WHO' and 'container-title' not in report
    assert 'language' not in report and 'issued' not in report
    assert lit.entry_from_meta('Y', '10.5555/y', {'type': 'grant', 'title': ['G']})['type'] == 'document'


# ---------------------------------------------------------------- Markdown headers and JATS
HEADER = '---\nkey: k2020x\ntitle: "T"\npmid: \npmcid: \nlicense: "cc-by"\ntext_source: "abstract only (full text not retrieved)"\n---\n'


def test_header_value_and_set_fields():
    assert lit.header_value(HEADER + '# T\n', 'text_source') == 'abstract only (full text not retrieved)'
    assert lit.header_value(HEADER, 'missing') == ''
    new = lit.set_header_fields(HEADER, {'license': lit.yaml_str('CC BY'), 'pmid': '123', 'journal': '"J"'})
    assert 'license: "CC BY"\n' in new and 'pmid: 123\n' in new and new.endswith('journal: "J"\n---\n')


def test_write_markdown_keeps_existing_header_and_title(tmp_path):
    (tmp_path / 'k2020x.md').write_text(HEADER + '# Original title\n\n## Abstract\n\nold\n', encoding='utf-8')
    entry = {'id': 'k2020x', 'title': 'Record title', 'PMID': '42'}
    lit.write_markdown(entry, 'new body', 'full text, PDF (browser (user session))', lit=str(tmp_path))
    text = (tmp_path / 'k2020x.md').read_text(encoding='utf-8')
    assert text.startswith('---\nkey: k2020x\n') and '\n# Original title\n\nnew body\n' in text
    assert lit.header_value(text, 'pmid') == '42'
    assert lit.header_value(text, 'license') == 'cc-by'            # no licence given: the header keeps its own
    lit.write_markdown(entry, 'new body', 'full text, PDF (x)', license='CC BY', lit=str(tmp_path))
    assert lit.header_value((tmp_path / 'k2020x.md').read_text(encoding='utf-8'), 'license') == 'CC BY'


def test_new_markdown_header_comes_from_the_entry(tmp_path):
    entry = by_id(fixture_entries())['WHO_2025']                    # a report by an organisation
    lit.write_markdown(entry, *lit.summary_body(entry), license='', lit=str(tmp_path))
    text = (tmp_path / 'WHO_2025.md').read_text(encoding='utf-8')
    assert 'authors: ["World Health Organization"]\n' in text and 'year: 2025\n' in text
    assert 'journal: "World Health Organization"\n' in text
    assert lit.header_value(text, 'text_source') == 'summary only (written for the project)'
    assert text.endswith('# Obesity and overweight\n\n## Summary\n\nFact sheet with the global figures on obesity and overweight.\n')


def test_jats_to_md():
    xml = b'''<article><front><article-meta><abstract><sec><title>Background</title><p>Why.</p></sec>
    <sec><title>Results</title><p>What <italic>found</italic>.</p></sec></abstract></article-meta></front>
    <body><sec><title>Methods</title><p>We did it.</p><list list-type="bullet"><list-item><p>one</p></list-item>
    </list></sec></body><back><ref-list><ref><mixed-citation>Ref A.</mixed-citation></ref></ref-list></back></article>'''
    md = lit.jats_to_md(xml)
    assert md.startswith('## Abstract\n\n### Background\n\nWhy.') and '\n## Methods\n' in md
    assert '*found*' in md and '- one' in md and '## References\n\n1. Ref A.' in md


# ---------------------------------------------------------------- a library in a temporary folder
def library(tmp_path, entries=None):
    """A library folder holding the fixture record (or the entries given), set as the library of this run."""
    lib = tmp_path / 'literature'
    lib.mkdir()
    lit.write_entries(fixture_entries() if entries is None else entries, str(lib / lit.RECORD))
    lit.LIT = str(lib)
    return lib


def markdown(lib, key, source):
    (lib / f'{key}.md').write_text(f'---\nkey: {key}\ntext_source: "{source}"\n---\n# T\n', encoding='utf-8')


def test_check_problems_on_a_small_library(tmp_path, monkeypatch):
    monkeypatch.setattr(lit, 'LIT', None)
    lib = library(tmp_path)
    entries = lit.read_entries(str(lib / lit.RECORD))
    by_id(entries)['Rossi_2024']['DOI'] = '10.5555/ALPHA.2021'      # a duplicate DOI, in another case
    by_id(entries)['Statista_2024']['type'] = 'web page'
    lit.write_entries(entries, str(lib / lit.RECORD))
    (lib / 'Alpha_2021.pdf').write_bytes(b'%PDF-')
    markdown(lib, 'Alpha_2021', 'full text, PDF (x)')
    markdown(lib, 'Rossi_2024', 'abstract only, from Crossref (full text not retrieved)')
    markdown(lib, 'WHO_2025', 'summary only (written for the project)')
    (lib / 'Statista_2024.md').write_text('---\nkey: Other_2024\n---\n# T\n', encoding='utf-8')
    (lib / 'stray.txt').write_text('x')
    (lib / 'pdf').mkdir()
    problems, _ = lit.check_problems(str(lib))
    assert problems == [
        'duplicate DOI: 10.5555/alpha.2021 (2 entries)',
        'Statista_2024: the type "web page" is not a CSL type',
        'Statista_2024: the header of Statista_2024.md names the key "Other_2024"',
        'subfolder not named by any entry of the record: pdf',
        'file not named by any entry of the record: stray.txt',
    ]


def test_check_reports_a_record_out_of_layout_and_fix_rewrites_it(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(lit, 'LIT', None)
    lib = library(tmp_path)
    for k in ('Alpha_2021', 'Rossi_2024', 'WHO_2025', 'Statista_2024'):
        markdown(lib, k, 'metadata only (full text and abstract not retrieved)')
    entries = lit.read_entries(str(lib / lit.RECORD))
    (lib / lit.RECORD).write_text(json.dumps(list(reversed(entries))), encoding='utf-8')   # one line, reversed
    assert lit.main(['--lib', str(lib), 'check']) == 1
    assert 'not in the script\'s layout' in capsys.readouterr().out
    assert lit.main(['--lib', str(lib), 'check', '--fix']) == 0
    assert lit.read_entries(str(lib / lit.RECORD)) == entries


def test_check_accepts_a_record_checked_out_with_crlf(tmp_path, monkeypatch):
    monkeypatch.setattr(lit, 'LIT', None)
    lib = library(tmp_path)
    for k in ('Alpha_2021', 'Rossi_2024', 'WHO_2025', 'Statista_2024'):
        markdown(lib, k, 'metadata only (full text and abstract not retrieved)')
    text = (lib / lit.RECORD).read_bytes().replace(b'\n', b'\r\n')      # git's autocrlf on Windows
    (lib / lit.RECORD).write_bytes(text)
    assert lit.check_problems(str(lib))[0] == []


# ---------------------------------------------------------------- a fresh clone: the record without its files
JATS = (b'<article><front><article-meta><abstract><p>About alpha.</p></abstract></article-meta></front>'
        b'<body><sec><title>Methods</title><p>We did it.</p></sec></body></article>')


def fake_retrieve(called, open_access=('Alpha_2021',)):
    """A stand-in for retrieve(): records the keys it is asked for; the works in open_access come back with
    their JATS full text and a licence, the others with an abstract from Europe PMC."""
    def retrieve(doi, key, title, family, rec):
        called.append(key)
        if key in open_access:
            rec.update(jats=JATS, xml='europepmc', license='cc-by', pmcid='PMC0000001')
        else:
            rec.update(abstract='About the Italian study.')
        return rec
    return retrieve


def test_fetch_in_a_fresh_clone_writes_the_text_of_every_work_with_a_doi(tmp_path, monkeypatch):
    monkeypatch.setattr(lit, 'LIT', None)
    lib = library(tmp_path)
    before = (lib / lit.RECORD).read_bytes()
    called = []
    monkeypatch.setattr(lit, 'retrieve', fake_retrieve(called))
    assert lit.cmd_fetch(argparse.Namespace(keys=[]))[0] == 0
    assert called == ['Alpha_2021', 'Rossi_2024']                    # the two works with a DOI
    alpha = (lib / 'Alpha_2021.md').read_text(encoding='utf-8')
    assert lit.header_value(alpha, 'text_source') == 'full text, JATS XML (europepmc)'
    assert lit.header_value(alpha, 'license') == 'CC BY'
    rossi = (lib / 'Rossi_2024.md').read_text(encoding='utf-8')
    assert lit.header_value(rossi, 'text_source') == 'abstract only, from Europe PMC / OpenAlex (full text not retrieved)'
    assert '## Abstract\n\nAbout the Italian study.' in rossi
    # the record keeps its fields, those the script does not manage included, and gains nothing machine-local
    assert (lib / lit.RECORD).read_bytes() == before
    # what is left are the two works without a DOI, whose Markdown md writes from the summary or the metadata
    problems, _ = lit.check_problems(str(lib))
    assert len(problems) == 1 and problems[0].startswith('no Markdown for Statista_2024, WHO_2025:')
    assert lit.cmd_md(argparse.Namespace(keys=[], force=False))[1]['written'] == ['Statista_2024', 'WHO_2025']
    assert lit.check_problems(str(lib))[0] == []
    assert lit.text_held('WHO_2025') == 'summary only' and lit.text_held('Statista_2024') == 'metadata only'


def test_fetch_decides_from_the_files(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(lit, 'LIT', None)
    lib = library(tmp_path)
    (lib / 'Rossi_2024.pdf').write_bytes(b'%PDF-')                  # this work's full text is here
    called = []
    monkeypatch.setattr(lit, 'retrieve', fake_retrieve(called))
    lit.cmd_fetch(argparse.Namespace(keys=['Alpha_2021', 'Rossi_2024']))
    assert called == ['Alpha_2021']
    assert 'Rossi_2024: already has its full text' in capsys.readouterr().out


def test_fetch_keeps_an_abstract_already_held(tmp_path, monkeypatch):
    monkeypatch.setattr(lit, 'LIT', None)
    lib = library(tmp_path)
    (lib / 'Rossi_2024.md').write_text('---\nkey: Rossi_2024\ntext_source: "abstract only, from Crossref (full text '
                                       'not retrieved)"\n---\n# T\n\n## Abstract\n\nKept.\n', encoding='utf-8')
    monkeypatch.setattr(lit, 'retrieve', fake_retrieve([]))
    lit.cmd_fetch(argparse.Namespace(keys=['Rossi_2024']))
    assert (lib / 'Rossi_2024.md').read_text(encoding='utf-8').endswith('## Abstract\n\nKept.\n')


def test_check_recognises_a_fresh_clone_in_one_line(tmp_path, monkeypatch):
    monkeypatch.setattr(lit, 'LIT', None)
    lib = library(tmp_path)
    problems, _ = lit.check_problems(str(lib))
    assert len(problems) == 1
    assert 'fresh clone' in problems[0] and 'fetch' in problems[0] and 'collect' in problems[0]


# ---------------------------------------------------------------- list, --json and the exit codes
def test_list_as_json_and_as_csv(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(lit, 'JSON', False)
    lib = library(tmp_path)
    (lib / 'Alpha_2021.pdf').write_bytes(b'%PDF-')
    assert lit.main(['--json', '--lib', str(lib), 'list', 'Alpha_2021', 'WHO_2025']) == 0
    out = capsys.readouterr().out
    works = json.loads(out)['works']
    assert [(w['id'], w['text'], w['pdf']) for w in works] == [('Alpha_2021', 'full text', True),
                                                                ('WHO_2025', 'none', False)]
    assert works[0]['authors'] == 'Alpha A, Beta B' and works[1]['summary'].startswith('Fact sheet')
    table = tmp_path / 'table.csv'
    assert lit.main(['--lib', str(lib), 'list', '--csv', str(table)]) == 0
    with open(table, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    assert [r['id'] for r in rows] == ['Alpha_2021', 'Rossi_2024', 'Statista_2024', 'WHO_2025']
    assert rows[0]['pdf'] == 'yes' and rows[1]['cited_in'] == 'chapter 2' and rows[2]['url'].startswith('https://')


def test_exit_codes_and_json_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(lit, 'JSON', False)
    lib = library(tmp_path)
    assert lit.main(['--lib', str(lib), 'check']) == 1              # a fresh clone: problems
    capsys.readouterr()
    assert lit.main(['--json', '--lib', str(lib), 'fetch', 'Nobody_2020']) == 2
    assert json.loads(capsys.readouterr().out) == {'error': 'unknown keys: Nobody_2020'}
    (lib / lit.RECORD).write_text('[{"id": "a",}]', encoding='utf-8')
    assert lit.main(['--json', '--lib', str(lib), 'list']) == 2
    error = json.loads(capsys.readouterr().out)['error']
    assert 'is not valid JSON' in error and 'at line 1, column' in error   # the column differs across Pythons
    with pytest.raises(SystemExit) as usage:
        lit.main(['--lib', str(lib), 'list', '--no-such-option'])
    assert usage.value.code == 2


def test_add_distinguishes_an_unknown_doi_from_an_unreachable_source(tmp_path, monkeypatch):
    monkeypatch.setattr(lit, 'JSON', False)
    lib = library(tmp_path)
    monkeypatch.setattr(lit, 'crossref', lambda doi: None)
    monkeypatch.setattr(lit, 'epmc_meta', lambda doi: None)
    monkeypatch.setattr(lit, 'FAILED', set())
    assert lit.main(['--lib', str(lib), 'add', '10.5555/unknown']) == 2
    monkeypatch.setattr(lit, 'FAILED', {'crossref', 'epmc'})
    assert lit.main(['--lib', str(lib), 'add', '10.5555/unknown']) == 3
    assert lit.main(['--lib', str(lib), 'add', 'not-a-doi']) == 2
    assert lit.main(['--lib', str(lib), 'add', '10.5555/ALPHA.2021']) == 2   # already in the library


def test_add_writes_a_new_entry_and_its_markdown(tmp_path, monkeypatch):
    monkeypatch.setattr(lit, 'JSON', False)
    lib = library(tmp_path)
    meta = {'type': 'journal-article', 'title': ['A new example'], 'author': [{'family': 'Omega', 'given': 'Olga'}],
            'issued': {'date-parts': [[2026]]}, 'container-title': ['Journal of Examples'],
            'updated-by': [{'type': 'correction'}]}
    monkeypatch.setattr(lit, 'crossref', lambda doi: meta)
    monkeypatch.setattr(lit, 'retrieve', fake_retrieve([], open_access=()))
    monkeypatch.setattr(lit, 'choose_abstract', lambda doi, rec: (None, None))
    assert lit.main(['--lib', str(lib), 'add', 'https://doi.org/10.5555/OMEGA', '--cited-in', 'chapter 5',
                     '--note', 'A description written for the project.']) == 0
    added = {e['id']: e for e in lit.read_entries(str(lib / lit.RECORD))}['Omega_2026']
    assert added == {'id': 'Omega_2026', 'type': 'article-journal', 'title': 'A new example',
                     'author': [{'family': 'Omega', 'given': 'Olga'}], 'issued': {'date-parts': [[2026]]},
                     'container-title': 'Journal of Examples', 'DOI': '10.5555/omega',
                     'custom': {'cited_in': 'chapter 5', 'summary': 'A description written for the project.'}}
    text = (lib / 'Omega_2026.md').read_text(encoding='utf-8')
    assert lit.header_value(text, 'text_source') == 'summary only (written for the project)'


# ---------------------------------------------------------------- convert: the older CSV into the record
def legacy_library(tmp_path):
    """A repository whose literature folder still holds the older bibliography.csv (the fixture): Gamma_2020 with
    its PDF and full-text Markdown, Epsilon_2022 with a Markdown holding the metadata only."""
    (tmp_path / '.git').mkdir()
    (tmp_path / '.gitignore').write_text('.env\nliterature/*\n!literature/bibliography.csv\n', encoding='utf-8')
    lib = tmp_path / 'literature'
    lib.mkdir()
    shutil.copy(os.path.join(FIXTURES, lit.LEGACY), lib / lit.LEGACY)
    (lib / 'Gamma_2020.pdf').write_bytes(b'%PDF-')
    markdown(lib, 'Gamma_2020', 'full text, PDF (x)')
    markdown(lib, 'Epsilon_2022', 'metadata only (full text and abstract not retrieved)')
    return lib


def test_convert_turns_the_csv_into_the_record(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(lit, 'JSON', False)
    lib = legacy_library(tmp_path)
    assert lit.main(['--json', '--lib', str(lib), 'convert']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['entries'] == 4 and result['abstracts_moved'] == ['Epsilon_2022']
    assert result['markdown_written'] == ['Bingham_2025', 'Survey_2026']
    assert result['as_document'] == ['questionnaire'] and result['authors_to_split'] == ['Bingham_2025']
    assert result['gitignore'] == ['!literature/bibliography.json']
    assert not (lib / lit.LEGACY).exists()
    assert (tmp_path / '.gitignore').read_text(encoding='utf-8') == '.env\nliterature/*\n!literature/bibliography.json\n'
    by = {e['id']: e for e in lit.read_entries(str(lib / lit.RECORD))}
    assert by['Gamma_2020'] == {
        'id': 'Gamma_2020', 'type': 'article-journal', 'title': 'A trial of fictitious things',
        'author': [{'family': 'Gamma', 'given': 'Giulia'}, {'family': 'Delta', 'given': 'Dario'}],
        'issued': {'date-parts': [[2020]]}, 'container-title': 'Journal of Examples', 'volume': '3', 'issue': '1',
        'page': '1-9', 'DOI': '10.5555/gamma.2020', 'PMID': '10000002', 'custom': {'cited_in': 'chapter 3'}}
    assert by['Epsilon_2022']['author'] == [{'family': 'Epsilon', 'given': 'Elena'}, {'literal': 'Example Study Group'}]
    assert by['Bingham_2025'] == {
        'id': 'Bingham_2025', 'type': 'report', 'title': 'Principles for an example practice',
        'author': [{'literal': 'Bingham C, Bond A, et al.'}], 'issued': {'date-parts': [[2025]]},
        'publisher': 'Example Association', 'URL': 'https://example.org/principles.pdf',
        'custom': {'cited_in': 'protocol 3.2', 'summary': 'A description written for the project.'}}
    assert by['Survey_2026']['type'] == 'document' and 'issued' not in by['Survey_2026']
    # the abstract moved into the Markdown that held the metadata only, with its origin and licence
    eps = (lib / 'Epsilon_2022.md').read_text(encoding='utf-8')
    assert lit.header_value(eps, 'text_source') == 'abstract only, from full text (JATS) (full text not retrieved)'
    assert lit.header_value(eps, 'license') == 'CC BY-NC' and eps.endswith('## Abstract\n\nAn example programme improved example outcomes.\n')
    # the full text already there is untouched, and the library is consistent
    assert lit.header_value((lib / 'Gamma_2020.md').read_text(encoding='utf-8'), 'text_source') == 'full text, PDF (x)'
    assert lit.check_problems(str(lib))[0] == []
    assert lit.main(['--lib', str(lib), 'convert']) == 2             # once only


@pytest.mark.parametrize('nl', ['\n', '\r\n'])
def test_the_gitignore_keeps_its_line_ends(tmp_path, nl):
    (tmp_path / '.git').mkdir()
    (tmp_path / 'literature').mkdir()
    (tmp_path / '.gitignore').write_bytes(nl.join(['.env', 'literature/*', '!literature/bibliography.csv', '']).encode())
    assert lit.ensure_gitignore(str(tmp_path / 'literature')) == ['!literature/bibliography.json']
    assert (tmp_path / '.gitignore').read_bytes() == nl.join(['.env', 'literature/*', '!literature/bibliography.json', '']).encode()


def test_convert_leaves_a_markdown_of_unknown_origin_alone(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(lit, 'JSON', False)
    lib = legacy_library(tmp_path)
    (lib / 'Survey_2026.md').write_text('Notes written before the library had headers.\n', encoding='utf-8')
    assert lit.main(['--json', '--lib', str(lib), 'convert']) == 0
    assert json.loads(capsys.readouterr().out)['markdown_written'] == ['Bingham_2025']
    assert (lib / 'Survey_2026.md').read_text(encoding='utf-8') == 'Notes written before the library had headers.\n'


def test_a_library_with_only_the_csv_asks_for_convert(tmp_path):
    lib = legacy_library(tmp_path)
    assert lit.find_library(tmp_path) == str(lib)
    with pytest.raises(lit.Refused, match='convert'):
        lit.set_library(None, 'check', cwd=str(tmp_path))
    with pytest.raises(lit.Refused, match='convert'):
        lit.set_library(None, 'add', cwd=str(tmp_path))


# ---------------------------------------------------------------- Surname_Year keys and the key form
def test_surname_year_keys():
    assert lit.make_surname_year(meta(), set()) == 'Alonzo_2021'
    assert lit.make_surname_year(meta(family='Del Rey Puech'), set()) == 'DelReyPuech_2021'
    assert lit.make_surname_year(meta(family='Abi-Jaoude'), set()) == 'Abi-Jaoude_2021'
    assert lit.make_surname_year(meta(family="O'Brien"), set()) == 'OBrien_2021'
    assert lit.make_surname_year(meta(family='Plöderl'), set()) == 'Ploderl_2021'
    assert lit.make_surname_year(meta(year=None), set()) == 'Alonzo_nd'


def test_surname_year_for_organisations_and_collisions():
    org = {'title': ['Report'], 'author': [{'name': 'World Health Organization'}], 'issued': {'date-parts': [[2025]]}}
    assert lit.make_surname_year(org, set()) == 'WHO_2025'
    assert lit.make_surname_year(meta(), {'Alonzo_2021'}) == 'Alonzo_2021b'
    assert lit.make_surname_year(meta(), {'Alonzo_2021', 'Alonzo_2021b'}) == 'Alonzo_2021c'


def test_key_style_follows_the_library():
    assert lit.key_style([]) == 'surname_year'
    assert lit.key_style([{'id': 'Iyamu_2021'}, {'id': 'alonzo2021interplay'}]) == 'surname_year'
    assert lit.key_style([{'id': 'alonzo2021interplay'}, {'id': 'luo2021determination'}, {'id': 'Iyamu_2021'}]) == 'citekey'
    assert lit.make_key(meta(), set(), 'citekey') == 'alonzo2021interplay'
    assert lit.make_key(meta(), set()) == 'Alonzo_2021'


# ---------------------------------------------------------------- the library folder
def test_find_library_from_anywhere_in_the_project(tmp_path):
    (tmp_path / '.git').mkdir()
    lib = tmp_path / 'docs' / 'literature'
    lib.mkdir(parents=True)
    (lib / lit.RECORD).write_text('[]\n', encoding='utf-8')
    deep = tmp_path / 'docs' / 'chapters'
    deep.mkdir()
    assert lit.find_library(deep) == str(lib)
    assert lit.find_library(lib) == str(lib)
    other = tmp_path / 'elsewhere'
    other.mkdir()
    (lib / lit.RECORD).unlink()
    assert lit.find_library(other) is None


def test_first_add_creates_the_library_and_its_gitignore_lines(tmp_path, monkeypatch):
    (tmp_path / '.git').mkdir()
    (tmp_path / '.gitignore').write_text('.env', encoding='utf-8')
    monkeypatch.setattr(lit, 'LIT', None)
    lib = lit.set_library(None, 'add', cwd=str(tmp_path))
    assert lib == str(tmp_path / 'literature')
    assert lit.read_entries(os.path.join(lib, lit.RECORD)) == []
    assert (tmp_path / '.gitignore').read_text(encoding='utf-8').splitlines() == ['.env', 'literature/*', '!literature/bibliography.json']
    # a second creation adds nothing to .gitignore
    assert lit.create_library(lib) == []


def test_commands_other_than_add_need_a_library(tmp_path):
    (tmp_path / '.git').mkdir()
    with pytest.raises(lit.Refused):
        lit.set_library(None, 'check', cwd=str(tmp_path))
