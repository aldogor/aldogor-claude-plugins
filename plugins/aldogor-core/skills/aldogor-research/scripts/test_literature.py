"""Tests for the pure functions of literature.py and its library-folder handling. No network: nothing here calls a web API.

Run with: python -m pytest <this folder>
"""
import os
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


# ---------------------------------------------------------------- CSV round trip
def sample_rows():
    base = {c: '' for c in lit.COLUMNS}
    return [
        dict(base, key='zeta2020b', authors='Zeta A', year='2020', title='Second, "quoted" title'),
        dict(base, key='alpha2021x', authors='Ålpha B, Beta C', year='2021',
             abstract_or_summary='Line one\nline two, with a comma', license='CC BY'),
        dict(base, key='zeta2020a', authors='Zeta A', year='2020', title='First'),
    ]


def test_csv_round_trip_keeps_bom_column_order_and_values(tmp_path):
    path = str(tmp_path / 'bibliography.csv')
    fields = list(reversed(lit.COLUMNS))                    # any order must survive
    lit.write_rows(sample_rows(), fields, path)
    with open(path, 'rb') as f:
        raw = f.read()
    assert raw.startswith(b'\xef\xbb\xbf')
    got_fields, got = lit.read_rows(path)
    assert got_fields == fields
    assert [r['key'] for r in got] == ['alpha2021x', 'zeta2020a', 'zeta2020b']      # sorted by author, year, key
    assert got[0]['abstract_or_summary'] == 'Line one\nline two, with a comma'
    assert got[2]['title'] == 'Second, "quoted" title'
    lit.write_rows(got, got_fields, path)                   # a second pass changes nothing
    with open(path, 'rb') as f:
        assert f.read() == raw


def test_csv_write_appends_missing_canonical_columns(tmp_path):
    path = str(tmp_path / 'bibliography.csv')
    lit.write_rows(sample_rows(), lit.COLUMNS[:-1], path)
    fields, _ = lit.read_rows(path)
    assert fields == lit.COLUMNS


# ---------------------------------------------------------------- authors and BibTeX
def test_authors_columns_from_crossref():
    m = {'author': [{'family': 'Alonzo', 'given': 'Rea'}, {'family': 'Hussain', 'given': 'Junayd'},
                    {'family': 'Stranges', 'given': 'Saverio'}, {'family': 'Anderson', 'given': 'Kelly K.'},
                    {'name': 'HBSC Group'}, {'family': '\nthe 2018 Group\n'}]}
    assert lit.authors_short(m) == 'Alonzo R, Hussain J, Stranges S, et al.'
    assert lit.authors_full(m) == 'Alonzo, Rea; Hussain, Junayd; Stranges, Saverio; Anderson, Kelly K.; HBSC Group; the 2018 Group'


def test_bib_authors_and_entry():
    row = {c: '' for c in lit.COLUMNS}
    row.update(key='alonzo2021interplay', doi='10.1016/j.smrv.2020.101414', kind='journal article',
               title='Interplay & more', year='2021', source='Sleep Medicine Reviews', pages='101-110',
               authors_full='Alonzo, Rea; HBSC Group')
    assert lit.bib_authors(row) == 'Alonzo, Rea and {HBSC Group}'
    entry = lit.bibtex(row)
    assert entry.startswith('@article{alonzo2021interplay,\n')
    assert 'title = {{Interplay \\& more}}' in entry and 'pages = {101--110}' in entry and 'url' not in entry
    no_doi = dict(row, doi='', authors='Boniel-Nissim M, Marino C', authors_full='', kind='report',
                  url='https://example.org')
    assert lit.bib_authors(no_doi) == '{Boniel-Nissim M, Marino C}'
    assert lit.bibtex(no_doi).startswith('@techreport{') and 'url = {https://example.org}' in lit.bibtex(no_doi)


# ---------------------------------------------------------------- Markdown headers and JATS
HEADER = '---\nkey: k2020x\ntitle: "T"\npmid: \npmcid: \nlicense: "cc-by"\ntext_source: "abstract only (full text not retrieved)"\n---\n'


def test_header_value_and_set_fields():
    assert lit.header_value(HEADER + '# T\n', 'text_source') == 'abstract only (full text not retrieved)'
    assert lit.header_value(HEADER, 'missing') == ''
    new = lit.set_header_fields(HEADER, {'license': lit.yaml_str('CC BY'), 'pmid': '123', 'journal': '"J"'})
    assert 'license: "CC BY"\n' in new and 'pmid: 123\n' in new and new.endswith('journal: "J"\n---\n')


def test_write_markdown_keeps_existing_header_and_title(tmp_path):
    (tmp_path / 'k2020x.md').write_text(HEADER + '# Original title\n\n## Abstract\n\nold\n', encoding='utf-8')
    row = {c: '' for c in lit.COLUMNS}
    row.update(key='k2020x', title='CSV title', pmid='42', license='CC BY')
    lit.write_markdown(row, 'new body', 'full text, PDF (browser (user session))', lit=str(tmp_path))
    text = (tmp_path / 'k2020x.md').read_text(encoding='utf-8')
    assert text.startswith('---\nkey: k2020x\n') and '\n# Original title\n\nnew body\n' in text
    assert lit.header_value(text, 'pmid') == '42' and lit.header_value(text, 'license') == 'CC BY'
    assert row['md'] == 'k2020x.md'


def test_jats_to_md_and_abstract():
    xml = b'''<article><front><article-meta><abstract><sec><title>Background</title><p>Why.</p></sec>
    <sec><title>Results</title><p>What <italic>found</italic>.</p></sec></abstract></article-meta></front>
    <body><sec><title>Methods</title><p>We did it.</p><list list-type="bullet"><list-item><p>one</p></list-item>
    </list></sec></body><back><ref-list><ref><mixed-citation>Ref A.</mixed-citation></ref></ref-list></back></article>'''
    md = lit.jats_to_md(xml)
    assert md.startswith('## Abstract\n\n### Background\n\nWhy.') and '\n## Methods\n' in md
    assert '*found*' in md and '- one' in md and '## References\n\n1. Ref A.' in md
    assert lit.jats_abstract(xml) == 'Background: Why. Results: What found.'


def test_abstract_from_markdown_only_for_full_text():
    body = 'Abstract\n' + 'This study measured things. ' * 12 + '\nKeywords: a, b\n'
    full = '---\ntext_source: "full text, PDF (x)"\n---\n# T\n\n' + body
    assert lit.abstract_from_markdown(full).startswith('This study measured things.')
    assert lit.abstract_from_markdown(full.replace('full text, PDF (x)', 'abstract only')) is None


# ---------------------------------------------------------------- check
def test_check_problems_on_a_small_library(tmp_path):
    rows = [{c: '' for c in lit.COLUMNS} for _ in range(2)]
    rows[0].update(key='a2020x', authors='A', full_text='yes', pdf='a2020x.pdf', md='a2020x.md', doi='10.1/a')
    rows[1].update(key='b2020y', authors='B', full_text='yes', doi='10.1/a')     # duplicate DOI, no full text
    lit.write_rows(rows, lit.COLUMNS, str(tmp_path / 'bibliography.csv'))
    (tmp_path / 'a2020x.pdf').write_bytes(b'%PDF-')
    (tmp_path / 'a2020x.md').write_text('---\nkey: a2020x\ntext_source: "full text, PDF (x)"\n---\n# A\n', encoding='utf-8')
    (tmp_path / 'stray.txt').write_text('x')
    (tmp_path / 'pdf').mkdir()
    problems, _ = lit.check_problems(str(tmp_path))
    text = '\n'.join(problems)
    assert 'duplicate doi: 10.1/a' in text
    assert 'b2020y: full_text is yes but the folder holds no full text' in text
    assert 'file not described by any row of the CSV: stray.txt' in text
    assert 'subfolder not described by any row of the CSV: pdf' in text
    assert not any(p.startswith('a2020x') for p in problems)


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
    assert lit.key_style([{'key': 'Iyamu_2021'}, {'key': 'alonzo2021interplay'}]) == 'surname_year'
    assert lit.key_style([{'key': 'alonzo2021interplay'}, {'key': 'luo2021determination'}, {'key': 'Iyamu_2021'}]) == 'citekey'
    assert lit.make_key(meta(), set(), 'citekey') == 'alonzo2021interplay'
    assert lit.make_key(meta(), set()) == 'Alonzo_2021'


# ---------------------------------------------------------------- the library folder
def test_find_library_from_anywhere_in_the_project(tmp_path):
    (tmp_path / '.git').mkdir()
    lib = tmp_path / 'docs' / 'literature'
    lib.mkdir(parents=True)
    (lib / lit.CSV_NAME).write_text('key\n', encoding='utf-8-sig')
    deep = tmp_path / 'docs' / 'chapters'
    deep.mkdir()
    assert lit.find_library(deep) == str(lib)
    assert lit.find_library(lib) == str(lib)
    other = tmp_path / 'elsewhere'
    other.mkdir()
    (tmp_path / 'docs' / 'literature' / lit.CSV_NAME).unlink()
    assert lit.find_library(other) is None


def test_first_add_creates_the_library_and_its_gitignore_lines(tmp_path, monkeypatch):
    (tmp_path / '.git').mkdir()
    (tmp_path / '.gitignore').write_text('.env', encoding='utf-8')
    monkeypatch.setattr(lit, 'LIT', None)
    lib = lit.set_library(None, 'add', cwd=str(tmp_path))
    assert lib == str(tmp_path / 'literature')
    fields, rows = lit.read_rows(os.path.join(lib, lit.CSV_NAME))
    assert fields == lit.COLUMNS and rows == []
    assert (tmp_path / '.gitignore').read_text(encoding='utf-8').splitlines() == ['.env', 'literature/*', '!literature/bibliography.csv']
    # a second creation adds nothing to .gitignore
    assert lit.create_library(lib) == []


def test_commands_other_than_add_need_a_library(tmp_path):
    (tmp_path / '.git').mkdir()
    with pytest.raises(SystemExit):
        lit.set_library(None, 'check', cwd=str(tmp_path))
