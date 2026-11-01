"""Tests of legislation.py, offline: the parsers run on fixtures cut from the sources' real answers (November 2026),
and the network is replaced by a fake that serves them. `python legislation.py smoke` is the live counterpart.

The fixtures are short excerpts of official texts: Italian legislative and official acts are outside copyright
(art. 5 L. 633/1941), Normattiva's content is published by IPZS under CC BY 4.0, and EU documents are reusable
under Commission Decision 2011/833/EU.

Run: python -m unittest plugins/aldogor-code/skills/aldogor-legislation/scripts/test_legislation.py
"""

import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import legislation as L  # noqa: E402

FIXTURES = HERE / "fixtures"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class FakeNet:
    """Stands in for legislation.http: answers each URL from the first route whose key it contains, and keeps the
    requests so a test can look at what was sent. A route is (body, content type), or a function of the request's
    data returning one, for an endpoint such as SPARQL that answers several kinds of query."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[tuple[str, bytes | None]] = []

    def __call__(self, url, data=None, headers=None, opener=None):
        self.calls.append((url, data))
        for key, answer in self.routes.items():
            if key in url:
                body, content_type = answer(data) if callable(answer) else answer
                return body, content_type, url
        raise L.SourceError(f"no fixture for {url}")


def sparql_answer(rows: list[dict]) -> bytes:
    """A SPARQL JSON answer holding the given rows of variable name to value."""
    bindings = [{key: {"type": "literal", "value": value} for key, value in row.items()} for row in rows]
    return json.dumps({"results": {"bindings": bindings}}).encode()


def run_main(argv: list[str]) -> tuple[int, str, str]:
    """main(argv) with stdout and stderr captured: (exit code, output, errors)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = L.main(argv)
    return code, out.getvalue(), err.getvalue()


class TextTests(unittest.TestCase):
    def test_html_to_text_keeps_blocks_apart_and_drops_scripts(self):
        text = L.html_to_text("<div>Art. 1</div><p>Primo  comma</p><script>var x;</script><li>a)&nbsp;voce</li>")
        self.assertEqual(text, "Art. 1\n\nPrimo comma\n\na) voce")

    def test_join_paragraphs_rejoins_broken_sentences(self):
        self.assertEqual(L.join_paragraphs("Art. 1. (Modifiche al\nr.r. 10/2011\n)\n\n1.\nAl\ncomma 3"),
                         "Art. 1. (Modifiche al r.r. 10/2011)\n\n1. Al comma 3")

    def test_decode_reads_utf8_and_stray_windows_1252_bytes(self):
        self.assertEqual(L.decode("Finalità ".encode() + "è stato".encode("cp1252"), "text/html; charset=UTF-8"),
                         "Finalità è stato")

    def test_decode_uses_a_declared_charset_other_than_utf8(self):
        self.assertEqual(L.decode("città".encode("latin-1"), "text/html; charset=ISO-8859-1"), "città")


class NormattivaTests(unittest.TestCase):
    def test_act_types_in_short_and_full_form(self):
        self.assertEqual(L.it_type("D.Lgs."), "DECRETO LEGISLATIVO")
        self.assertEqual(L.it_type("dpr"), "DECRETO DEL PRESIDENTE DELLA REPUBBLICA")
        self.assertEqual(L.it_type("decreto-legge"), "DECRETO-LEGGE")

    def test_article_references(self):
        self.assertEqual(L.parse_article("13"), (13, 1, ""))
        self.assertEqual(L.parse_article("2-bis"), (2, 2, "bis"))
        self.assertEqual(L.parse_article("art. 2 septies"), (2, 7, "septies"))
        with self.assertRaises(SystemExit):
            L.parse_article("2-xyz")

    def test_a_regional_urn_is_never_sent_to_normattiva(self):
        # Normattiva answers urn:nir:regione.piemonte:legge:2007;18 with DPR 12 gennaio 2007, n. 18 and HTTP 200.
        with self.assertRaises(ValueError):
            L.normattiva_link("urn:nir:regione.piemonte:legge:2007;18")

    def test_links_use_the_urn_where_the_act_type_has_one(self):
        act = json.loads(fixture("normattiva_search.json"))["listaAtti"][0]
        self.assertEqual(L.it_link(act, L.parse_article("2-septies"), "2019-01-01"),
                         "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2003-06-30;196"
                         "~art2septies!vig=2019-01-01")
        decree = {"denominazioneAtto": "DECRETO", "dataGU": "2020-01-02", "codiceRedazionale": "20A00001"}
        self.assertIn("caricaDettaglioAtto?atto.dataPubblicazioneGazzetta=2020-01-02", L.it_link(decree))

    def test_article_as_in_force_on_a_past_date(self):
        net = FakeNet({"ricerca/avanzata": (fixture("normattiva_search.json"), "application/json"),
                       "dettaglio-atto": (fixture("normattiva_article.json"), "application/json")})
        with mock.patch.object(L, "http", net):
            act = L.it_find("DLGS", 2003, "196")
            found = L.it_article(act, L.parse_article("13"), "2010-01-01")
        self.assertEqual((found["from"], found["to"]), ("2009-11-25", "2011-07-12"))
        self.assertIn("Informativa", found["text"])
        sent = json.loads(net.calls[-1][1])
        self.assertEqual((sent["dataVigenza"], sent["tipoDettaglio"]), ("2010-01-01", "singolavigenza"))

    def test_command_prints_the_version_and_the_link_to_cite(self):
        net = FakeNet({"ricerca/avanzata": (fixture("normattiva_search.json"), "application/json"),
                       "dettaglio-atto": (fixture("normattiva_article.json"), "application/json")})
        with mock.patch.object(L, "http", net):
            code, out, _ = run_main(["it-article", "--type", "DLGS", "--year", "2003", "--number", "196",
                                     "--article", "13", "--date", "2010-01-01"])
        self.assertEqual(code, 0)
        self.assertIn("Version in force on 2010-01-01: from 2009-11-25 to 2011-07-12", out)
        self.assertIn("~art13!vig=2010-01-01", out)


class EurLexTests(unittest.TestCase):
    def test_references_to_celex(self):
        cases = {"32016R0679": "32016R0679", "Regolamento (UE) 2016/679": "32016R0679",
                 "Regulation (EC) No 1907/2006": "32006R1907", "Direttiva 95/46/CE": "31995L0046",
                 "Direttiva 2001/83/CE": "32001L0083", "Decisione (UE) 2020/1234": "32020D1234",
                 "http://data.europa.eu/eli/reg/2016/679/oj": "32016R0679",
                 "02016R0679-20160504": "02016R0679-20160504"}
        for ref, celex in cases.items():
            self.assertEqual(L.parse_eu_ref(ref), celex, ref)
        with self.assertRaises(SystemExit):
            L.parse_eu_ref("la legge sulla privacy")

    def test_the_consolidated_version_that_applies_on_a_date(self):
        versions = ["02016R0679-20160504", "02016R0679-20180525"]
        self.assertEqual(L.version_on(versions, "2019-01-01"), "02016R0679-20180525")
        self.assertEqual(L.version_on(versions, "2017-01-01"), "02016R0679-20160504")
        self.assertIsNone(L.version_on(versions, "2016-05-01"))

    def test_one_article_and_the_table_of_contents(self):
        text = L.html_to_text(fixture("eu_text.html").decode())
        article = L.eu_article(text, "9")
        self.assertTrue(article.startswith("Articolo 9"))
        self.assertIn("categorie particolari", article)
        self.assertNotIn("Articolo 10", article)
        self.assertEqual([line.split(":")[0] for line in L.eu_toc(text)], ["Articolo 8", "Articolo 9", "Articolo 10"])
        with self.assertRaises(L.SourceError):
            L.eu_article(text, "99")

    def test_consolidations_come_from_sparql(self):
        net = FakeNet({"sparql": (sparql_answer([{"celex": "02016R0679-20160504"}]), "application/sparql-results+json")})
        with mock.patch.object(L, "http", net):
            self.assertEqual(L.eu_consolidations("32016R0679"), ["02016R0679-20160504"])
        self.assertIn(b"^02016R0679(-[0-9]{8})?$", net.calls[0][1])

    def test_lookup_reports_an_unrecorded_in_force_flag_as_such(self):
        meta = sparql_answer([{"title": "Regolamento (UE) 2016/679", "date": "2016-04-27", "end": "9999-12-31"}])
        versions = sparql_answer([{"celex": "02016R0679-20160504"}])
        net = FakeNet({"sparql": lambda query: (meta if b"GROUP BY" in query else versions,
                                                "application/sparql-results+json")})
        with mock.patch.object(L, "http", net):
            code, out, _ = run_main(["eu-lookup", "Regolamento (UE) 2016/679"])
        self.assertEqual(code, 0)
        self.assertIn("In force: not recorded in CELLAR", out)
        self.assertIn("End of validity: none (open-ended)", out)
        self.assertIn("http://data.europa.eu/eli/reg/2016/679/oj", out)


class PiedmontTests(unittest.TestCase):
    def test_urns_and_links(self):
        urn = L.regional_urn("legge", 2007, 18)
        self.assertEqual(urn, "urn:nir:regione.piemonte:legge:2007;18")
        self.assertEqual(L.arianna_url(urn, "2010-01-01", "3"), L.ARIANNA_LAW + urn + "@2010-01-01#art3")
        self.assertIn("dettaglioRegolamento.do?urnRegolamento=",
                      L.arianna_url(L.regional_urn("regolamento", "2024-04-08", 1)))

    def test_law_page_versions_articles_and_notes(self):
        act = L.parse_arianna(L.decode(fixture("arianna_law.html"), "text/html; charset=UTF-8"))
        self.assertEqual(act["heading"], "Legge regionale n. 18 del 06 agosto 2007")
        self.assertEqual([(v["label"], v["shown"]) for v in act["versions"]], [("V11", False), ("V12", True)])
        self.assertEqual([a["id"] for a in act["articles"]], ["22", "23", "24"])
        art22, art23 = act["articles"][0], act["articles"][1]
        self.assertTrue(art23["text"].startswith("Art. 23."))
        self.assertNotIn("[19]", art23["text"])
        self.assertTrue(art23["notes"][0].startswith("[19] L'articolo 23 è stato sostituito"))
        self.assertNotIn("Titolo IV", art22["text"])

    def test_search_results(self):
        rows = L.parse_arianna_search(fixture("arianna_search.html").decode())
        self.assertEqual([r["urn"] for r in rows], ["urn:nir:regione.piemonte:legge:2013;20",
                                                    "urn:nir:regione.piemonte:legge:2007;18"])
        self.assertEqual(rows[1]["date"], "06/08/2007")
        self.assertTrue(rows[1]["title"].startswith("Norme per la programmazione socio-sanitaria"))

    def test_bulletin_search_hits(self):
        hits = L.parse_bur_search(L.decode(fixture("bur_search.html"), "text/html"))
        self.assertEqual(len(hits), 3)
        self.assertTrue(hits[0]["text"].startswith("2022 - Supp. n. 1 al B.U. n. 03"))
        self.assertTrue(all("documenti trovati" not in h["text"] for h in hits))
        self.assertTrue(hits[1]["url"].endswith("2022/48/siste/00000056.htm"))

    def test_bulletin_act_page_and_its_pdf(self):
        page_url = "https://www.regione.piemonte.it/governo/bollettino/abbonati/2026/43/siste/00000042.htm"
        net = FakeNet({".pdf": (b"%PDF-1.4 test", "application/pdf"), page_url: (fixture("bur_act.html"), "text/html")})
        with mock.patch.object(L, "http", net), tempfile.TemporaryDirectory() as folder:
            text, saved = L.bur_act(page_url, pathlib.Path(folder))
            self.assertEqual([p.name for p in saved], ["dda1400000684_11200.pdf"])
            self.assertEqual(saved[0].read_bytes(), b"%PDF-1.4 test")
        self.assertIn("D.D. 23 Ottobre 2026, n. 684", text)
        self.assertIn("Attività", text)
        self.assertEqual(net.calls[1][0],
                         "https://www.regione.piemonte.it/governo/bollettino/abbonati/2026/43/attach/"
                         "dda1400000684_11200.pdf")


class MainTests(unittest.TestCase):
    def test_a_failing_source_exits_1_with_its_message(self):
        with mock.patch.object(L, "http", FakeNet({})):
            code, _, err = run_main(["it-search", "--type", "DLGS", "--year", "2003", "--number", "196"])
        self.assertEqual(code, 1)
        self.assertIn("no fixture for", err)

    def test_a_wrong_date_exits_2(self):
        code, _, err = run_main(["pie-law", "--year", "2007", "--number", "18", "--date", "2010/01/01"])
        self.assertEqual(code, 2)
        self.assertIn("YYYY-MM-DD", err)


if __name__ == "__main__":
    unittest.main()
