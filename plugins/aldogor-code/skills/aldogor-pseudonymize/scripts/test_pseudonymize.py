"""Tests of aldogor-pseudonymize without the model: a stub detector stands in for rizzo-pii's model and
the vendored regex net runs as it is. Every name and code here is invented. The codice fiscale and the IBAN
are the textbook examples that rizzo-pii's own tests use, so that no published value can belong to a real
person; the tessera sanitaria number is synthetic. All three carry valid check characters.

Run: python -m unittest plugins/aldogor-code/skills/aldogor-pseudonymize/scripts/test_pseudonymize.py
(Word and Excel tests run only where python-docx and openpyxl are installed, as in the private environment.)
"""

import csv
import importlib.util
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pz_engine as eng  # noqa: E402
import pz_formats as fmt  # noqa: E402
from vendor.rizzo_pii import detectors as rz  # noqa: E402

CF = "RSSMRA85H12F205Y"
TS_NUM = "80380000011235813215"
IBAN = "IT60X0542811101000000123456"


class StubDetector:
    """Finds a fixed list of strings as the model would (FULLNAME unless given), plus the regex net."""

    name = "stub"

    def __init__(self, names=(), labels=None):
        self.names = list(names)
        self.labels = labels or {}

    def detect_many(self, texts):
        out = []
        for t in texts:
            found = rz.detect_regex(t)
            for n in self.names:
                for m in re.finditer(r"(?<!\w)" + re.escape(n) + r"(?!\w)", t):
                    found.append({"label": self.labels.get(n, "FULLNAME"), "start": m.start(), "end": m.end(),
                                  "score": 0.99, "validated": False, "source": "model"})
            out.append(found)
        return out


def context(**kw):
    ctx = eng.Context.load(HERE / "data", None)
    for k, v in kw.items():
        setattr(ctx, k, v)
    return ctx


def mask(texts, names=(), labels=None, table=None, ctx=None, people=()):
    table = table or eng.Table()
    res = eng.mask_texts(texts, StubDetector(names, labels), table, ctx or context(), people=people)
    return [r.text for r in res], table


class RulesTest(unittest.TestCase):
    def test_tessera_sanitaria_outranks_the_card_label(self):
        out, table = mask([f"Tessera sanitaria: {TS_NUM}"])
        self.assertEqual(out[0], "Tessera sanitaria: [TS_1]")
        self.assertTrue(eng.luhn(TS_NUM))

    def test_birth_date_masked_other_dates_kept(self):
        out, _ = mask(["Nata a Susa il 14/03/1938, dimessa il 02/09/2026.",
                       "nato il 3 marzo 1950; visita del 7 ottobre 2026"])
        self.assertEqual(out[0], "Nata a Susa il [BIRTHDATE_1], dimessa il 02/09/2026.")
        self.assertEqual(out[1], "nato il [BIRTHDATE_2]; visita del 7 ottobre 2026")

    def test_case_numbers_keep_their_word(self):
        out, _ = mask(["Pratica UVG n. 2026/0417.", "prenotazione n. 2026TO30884512", "prenotazione del 12/06/2026",
                       "richiesta del 20 giugno", "NRE 1500A4012345678"])
        self.assertEqual(out[0], "Pratica UVG n. [DOCID_1].")
        self.assertEqual(out[1], "prenotazione n. [DOCID_2]")
        self.assertEqual(out[2], "prenotazione del 12/06/2026")
        self.assertEqual(out[3], "richiesta del 20 giugno")
        self.assertEqual(out[4], "NRE [DOCID_3]")

    def test_name_after_a_greeting(self):
        out, _ = mask(["ciao fede,\nti scrivo", "Ciao a tutti,\nla riunione", "Gentile dottoressa,\nle invio",
                       "grazie mille, a dopo", "ciao bella!"])
        self.assertTrue(out[0].startswith("ciao [FULLNAME_1],"))
        self.assertEqual(out[1:], ["Ciao a tutti,\nla riunione", "Gentile dottoressa,\nle invio",
                                   "grazie mille, a dopo", "ciao bella!"])

    def test_functional_mailbox_kept_personal_masked(self):
        out, _ = mask(["Scrivere a urp@asl.example.org o a mario.verdolini@asl.example.org."])
        self.assertEqual(out[0], "Scrivere a urp@asl.example.org o a [EMAIL_1].")

    def test_keep_list_beats_the_model(self):
        out, _ = mask(["ASL TO3, Distretto Val Susa e Val Sangone; demenza di Alzheimer"],
                      names=["TO3", "Val Susa", "Alzheimer"], labels={"TO3": "TARGA", "Val Susa": "STREET"},
                      ctx=context(keep=eng.read_list(HERE / "data" / "keep_default.txt") + ["Val Susa", "Val Sangone"]))
        self.assertEqual(out[0], "ASL TO3, Distretto Val Susa e Val Sangone; demenza di Alzheimer")

    def test_checksum_identifier_survives_the_keep_list(self):
        out, _ = mask([f"CF {CF}"], ctx=context(keep=[CF]))
        self.assertEqual(out[0], "CF [CF_1]")

    def test_spans_widen_to_whole_words(self):
        text = "Il signor Chiabrando ha scritto"
        cut = {"label": "FULLNAME", "start": 10, "end": 15, "score": 0.9, "validated": False, "source": "model"}
        spans = eng.merge([cut], text)
        self.assertEqual(text[spans[0]["start"]:spans[0]["end"]], "Chiabrando")

    def test_name_after_a_title(self):
        out, _ = mask(["ha chiamato il dott. Re per la terapia; firma la dott.ssa Laura Bertolotti.",
                       "lo vede il dott. di guardia; la sig.ra rossetti non risponde; la dott.ssa della COT"])
        # people are registered from the longest name, so Laura Bertolotti is 1 and Re is 2
        self.assertEqual(out[0], "ha chiamato il dott. [FULLNAME_2] per la terapia; firma la dott.ssa [FULLNAME_1].")
        self.assertEqual(out[1], "lo vede il dott. di guardia; la sig.ra [FULLNAME_3] non risponde; la dott.ssa della COT")

    def test_name_before_an_initial(self):
        out, _ = mask(["Hanno lavorato Bertolotti A. e Ghirardi M. sul progetto.", "Vedi Allegato A. e la Vitamina D. nel piano"])
        self.assertEqual(out[0], "Hanno lavorato [FULLNAME_1] A. e [FULLNAME_2] M. sul progetto.")
        self.assertEqual(out[1], "Vedi Allegato A. e la Vitamina D. nel piano")

    def test_names_on_an_attendance_line(self):
        out, _ = mask(["Presenti: Paola Rinaudo (Direttrice), Fabio Chiolero, Ufficio Formazione\nOrdine del giorno: Turni"])
        self.assertEqual(out[0], "Presenti: [FULLNAME_1] (Direttrice), [FULLNAME_2], Ufficio Formazione\nOrdine del giorno: Turni")

    def test_surname_that_is_a_municipality(self):
        docs = ["Referente: dott.ssa Laura Usseglio.", "ho sentito Usseglio ieri; la sede di Usseglio è chiusa"]
        out, _ = mask(docs)
        self.assertEqual(out[1], "ho sentito [FULLNAME_1] ieri; la sede di Usseglio è chiusa")

    def test_a_name_after_a_title_stays_on_its_line(self):
        out, _ = mask(["Sig.ra Anna Bertolotti\nA.S.L. TO3 - S.C. Acquisti"])
        self.assertEqual(out[0], "Sig.ra [FULLNAME_1]\nA.S.L. TO3 - S.C. Acquisti")

    def test_model_detections_need_their_shape(self):
        text = ("Distretto Val Susa; residente in via Roma 12, 10094 Giaveno; CDC 10122; AOO A1400A; codice V-892080; "
                "targa AB123CD; N. Prot. 00012345 del 14/10/2026")
        labels = {"Val Susa": "STREET", "via Roma": "STREET", "12": "BUILDINGNUM", "10094": "ZIPCODE", "10122": "ZIPCODE",
                  "A1400A": "TARGA", "V-892080": "ID_DOC", "AB123CD": "TARGA"}
        out, _ = mask([text], names=list(labels), labels=labels)
        self.assertEqual(out[0], "Distretto Val Susa; residente in [STREET_1] [BUILDINGNUM_1], [ZIPCODE_1] Giaveno; "
                                 "CDC 10122; AOO A1400A; codice V-892080; targa [TARGA_1]; N. Prot. 00012345 del 14/10/2026")

    def test_a_valley_is_no_person(self):
        out, table = mask(["CURE DOMICILIARI VAL CHISONE", "Distretto Val Chisone, sede di Perosa"], names=["VAL CHISONE"])
        self.assertEqual(out, ["CURE DOMICILIARI VAL CHISONE", "Distretto Val Chisone, sede di Perosa"])
        self.assertEqual(table.entries, {})

    def test_officials_left_in_clear(self):
        out, _ = mask(["Presenti: Paola Giordano (Direttrice), Franco Bertolotti (assistito)"],
                      names=["Paola Giordano", "Franco Bertolotti"], ctx=context(officials=["Paola Giordano"]))
        self.assertEqual(out[0], "Presenti: Paola Giordano (Direttrice), [FULLNAME_1] (assistito)")


class TableTest(unittest.TestCase):
    def test_variants_of_one_person_share_a_placeholder(self):
        text = ("Assistita: FERRERO Giuseppina. Figlio: Marco Ferrero. La signora Giuseppina sta bene; "
                "la signora Ferrero vive sola.")
        out, table = mask([text], names=["FERRERO Giuseppina", "Marco Ferrero", "Giuseppina", "Ferrero"])
        self.assertEqual(out[0], "Assistita: [FULLNAME_1]. Figlio: [FULLNAME_2]. La signora [FULLNAME_1] sta bene; "
                                 "la signora [FULLNAME_3] vive sola.")
        self.assertTrue(table.entries["[FULLNAME_3]"]["ambiguous"])
        self.assertEqual(table.display("[FULLNAME_1]"), "FERRERO Giuseppina")

    def test_numbering_is_stable_across_runs(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "table.json"
            t1 = eng.Table(path)
            out1, _ = mask(["Rosa Usseglio e Davide Chiabrando"], names=["Rosa Usseglio", "Davide Chiabrando"], table=t1)
            t1.save()
            out2, _ = mask(["Davide Chiabrando, poi Rosa Usseglio"], names=["Rosa Usseglio", "Davide Chiabrando"],
                           table=eng.Table(path))
            self.assertEqual(out1[0], "[FULLNAME_1] e [FULLNAME_2]")
            self.assertEqual(out2[0], "[FULLNAME_2], poi [FULLNAME_1]")

    def test_project_wide_pass_and_common_words(self):
        docs = ["Elenco: Serena Martina, Franco Sola.", "la sig.ra martina non vuole; vive sola con la Sola."]
        out, _ = mask(docs, names=["Serena Martina", "Franco Sola"])
        self.assertEqual(out[1], "la sig.ra [FULLNAME_1] non vuole; vive sola con la [FULLNAME_2].")

    def test_a_municipality_mistaken_for_a_name_does_not_spread(self):
        class OneDoc(StubDetector):
            def detect_many(self, texts):  # the model marks "Bruino" in the second text only
                out = super().detect_many(texts)
                out[1].append({"label": "FULLNAME", "start": 14, "end": 20, "score": 0.9, "validated": False,
                               "source": "model"})
                return out

        docs = ["CURE DOMICILIARI ADI AVIGLIANA", "visto ieri a Bruino.", "Bruino conferma; Assessora di Avigliana"]
        res = eng.mask_texts(docs, OneDoc(["AVIGLIANA"]), eng.Table(), context())
        self.assertEqual([r.text for r in res], [docs[0], "visto ieri a [FULLNAME_1].", docs[2]])

    def test_a_first_name_that_is_a_common_word_joins_the_surname(self):
        out, table = mask(["A: Letizia Bertolotti <lb@example.org>; Serena", "Bertolotti Letizia"], names=["Bertolotti"])
        self.assertEqual(out, ["A: [FULLNAME_1] <[EMAIL_1]>; Serena", "[FULLNAME_1]"])

    def test_single_words_of_a_name_within_limits(self):
        docs = ["Presenti: Nella Del Rosso, Anna Ottobre.", "Del Rosso osserva che la Ottobre è assente.",
                "Evidenziare in rosso le righe; il 12 ottobre nella sede della Regione. ROSSO = urgente",
                "Ho sentito la rosso ieri."]
        out, _ = mask(docs)
        # a month never travels alone, even when someone bears it as a surname
        self.assertEqual(out[1], "[FULLNAME_1] osserva che la Ottobre è assente.")
        self.assertEqual(out[2], docs[2])
        # "rosso" is an ordinary word in this project, so not even an article makes it the person
        self.assertEqual(out[3], docs[3])

    def test_lowercase_after_a_cue_unless_the_project_uses_the_word(self):
        self.assertEqual(eng.lowercase_words(["la sig.ra martina chiama", "evidenziare in rosso",
                                              "a: <cristina.bellando@example.org>"]) & {"martina", "rosso", "cristina"},
                         {"rosso"})
        docs = ["Referente: dott. Fabio Chiolero.", "ne parlo con il chiolero domani, ciao chiolero"]
        out, _ = mask(docs)
        self.assertEqual(out[1], "ne parlo con il [FULLNAME_1] domani, ciao [FULLNAME_1]")

    def test_nicknames_travel_in_lowercase(self):
        docs = ["Presenti: Gio Perino, Fabio Chiolero.", "prova a sentire gio, è libera. ne parlo con chiolero"]
        out, _ = mask(docs)
        self.assertEqual(out[1], "prova a sentire [FULLNAME_1], è libera. ne parlo con chiolero")

    def test_a_directory_lends_full_names_only(self):
        given = ["Anna", "Marco", "Paola", "Luca", "Sara", "Elena", "Fabio", "Giulia", "Piero", "Rosa"]
        surnames = ["Ferraris", "Bertolotti", "Chiolero", "Usseglio", "Garnier", "Allasia"]
        rows = [["Servizio", "Cognome", "Nome"]] + [["S.C. Cardiologia", s, g] for g in given for s in surnames]
        rows += [["S.C. Pediatria", "Rosso", "Nella"], ["S.C. Pediatria", "Gribaudo", "Elena"]]
        people = fmt.table_people(rows, "censimento.xlsx")
        self.assertTrue(all(info["directory"] for *_, info in people))
        docs = ["Da: ROSSO NELLA; A: Bertolotti Marco, N. Rosso", "evidenziare in Rosso; Nella sede; Garnier propone",
                "dott.ssa Elena Gribaudo, referente", "Gribaudo conferma; Allasia anche"]
        out, table = mask(docs, people=people)
        ph = {e["variants"][0]: p for p, e in table.entries.items()}
        self.assertEqual(out[0], f"Da: {ph['Nella Rosso']}; A: {ph['Marco Bertolotti']}, {ph['Nella Rosso']}")
        self.assertEqual(out[1], docs[1])
        # met in a text, a directory person's surname travels on its own; a surname ten people share does not
        self.assertEqual(out[3], f"{ph['Elena Gribaudo']} conferma; Allasia anche")
        self.assertNotIn("directory", table.entries[ph["Elena Gribaudo"]])
        self.assertTrue(table.entries[ph["Marco Bertolotti"]]["directory"])

    def test_two_rows_are_two_people(self):
        rows = [["Cognome", "Nome"], ["Rossi", "Anna"], ["Rossi", "Anna Maria"]]
        table = eng.Table()
        table.register_people(fmt.table_people(rows, "elenco.csv"))
        self.assertEqual(len(table.entries), 2)

    def test_restore(self):
        out, table = mask([f"La signora Giuseppina Ferrero, CF {CF}, IBAN {IBAN}"], names=["Giuseppina Ferrero"])
        back, n, unknown = eng.restore_text(out[0] + " [FULLNAME_9] [DA_COMPLETARE]", table)
        self.assertEqual(back, f"La signora Giuseppina Ferrero, CF {CF}, IBAN {IBAN} [FULLNAME_9] [DA_COMPLETARE]")
        self.assertEqual((n, unknown), (3, ["[FULLNAME_9]"]))


class DetectorTest(unittest.TestCase):
    def test_identical_chunks_go_through_the_model_once(self):
        seen = []

        def nlp(chunks, batch_size=1):
            seen.extend(chunks)
            return [[{"entity_group": "FULLNAME", "start": 0, "end": 5, "score": 0.9}] for _ in chunks]

        det = eng.RizzoDetector.__new__(eng.RizzoDetector)
        det.nlp = nlp
        found = det.detect_many(["Rossi Anna", "Rossi Anna", "Bruno"])
        self.assertEqual(sorted(seen), ["Bruno", "Rossi Anna"])
        self.assertEqual([[(e["start"], e["end"]) for e in f if e["source"] == "model"] for f in found],
                         [[(0, 5)], [(0, 5)], [(0, 5)]])


class TableFormatTest(unittest.TestCase):
    ROWS = [["COGNOME", "NOME", "CODICE FISCALE", "DATA NASCITA", "COMUNE", "TELEFONO", "NOTE"],
            ["FERRERO", "GIUSEPPINA", CF, "14/03/1938", "GIAVENO", "347 512 8830", "BPCO, ossigenoterapia"],
            ["SOLA", "FRANCO", "", "17/04/1958", "AVIGLIANA", "", "in carico al CSM"]]

    def test_columns_masked_header_and_separators_kept(self):
        table = eng.Table()
        sheets, cells = fmt.mask_sheets([("", self.ROWS)], StubDetector(), table, context(), "elenco.csv")
        rows = sheets[0][1]
        self.assertEqual(rows[0], self.ROWS[0])
        self.assertEqual(rows[1][:4], ["[FULLNAME_1]", "[FULLNAME_1]", "[CF_1]", "[BIRTHDATE_1]"])
        self.assertEqual(rows[1][4:], ["GIAVENO", "[TELEPHONENUM_1]", "BPCO, ossigenoterapia"])
        self.assertEqual(rows[2][2], "")
        self.assertEqual(table.display("[FULLNAME_1]"), "GIUSEPPINA FERRERO")
        buf = io.StringIO()
        csv.writer(buf, delimiter=";", lineterminator="\n").writerows(rows)
        self.assertEqual(buf.getvalue().splitlines()[1].count(";"), 6)

    def test_header_found_below_title_rows(self):
        rows = [["Elenco iscritti, corso di aggiornamento", "", ""], ["Docente: dott.ssa Carla Bertolotti", "", ""],
                ["", "", ""], ["Cognome", "Nome", "Note"], ["Ferrero", "Anna", "presente"]]
        table = eng.Table()
        sheets, _ = fmt.mask_sheets([("", rows)], StubDetector(), table, context(), "corso.csv")
        out = sheets[0][1]
        self.assertEqual(out[0], rows[0])
        self.assertEqual(out[1][0], "Docente: dott.ssa [FULLNAME_2]")
        self.assertEqual(out[3], rows[3])
        self.assertEqual(out[4], ["[FULLNAME_1]", "[FULLNAME_1]", "presente"])

    def test_a_note_under_the_surname_column_is_text_not_a_person(self):
        rows = [["Cognome", "Nome"], ["Ferrero", "Anna"],
                ["Il registro è conservato dall'Ufficio Formazione ai fini ECM.", ""]]
        table = eng.Table()
        sheets, _ = fmt.mask_sheets([("", rows)], StubDetector(), table, context(), "registro.csv")
        self.assertEqual(sheets[0][1][2][0], rows[2][0])
        self.assertEqual([e["variants"] for e in table.entries.values()], [["Anna Ferrero"]])

    def test_a_surname_that_is_an_office_word_is_a_name_beside_a_given_name(self):
        rows = [["Cognome", "Nome"], ["Medici", "Anna"], ["STRADA", "LUCA"], ["Ufficio Formazione", ""]]
        table = eng.Table()
        sheets, _ = fmt.mask_sheets([("", rows)], StubDetector(), table, context(), "elenco.csv")
        out = sheets[0][1]
        self.assertEqual(out[1:3], [["[FULLNAME_1]", "[FULLNAME_1]"], ["[FULLNAME_2]", "[FULLNAME_2]"]])
        self.assertEqual(out[3], rows[3])
        self.assertEqual(table.display("[FULLNAME_1]"), "Anna Medici")

    def test_organisation_unit_columns_set_the_models_people_aside(self):
        rows = [["Servizio", "Cognome", "Nome", "Descrizione CDC"],
                ["S.C. Cardiologia", "Ferrero", "Anna", "Reparto Bertolotti"],
                ["S.C. Pediatria", "Gribaudo", "Carla", "Ambulatorio dott.ssa Anna Ferrero"],
                ["Day Surgery", "Allais", "Piero", "Day Surgery Rivoli"]]
        table = eng.Table()
        sheets, _ = fmt.mask_sheets([("", rows)], StubDetector(["Bertolotti", "Day"]), table, context(), "censimento.xlsx")
        out = sheets[0][1]
        self.assertEqual(out[1][3], "Reparto Bertolotti")
        self.assertEqual(out[2][3], "Ambulatorio dott.ssa " + out[1][1])
        self.assertEqual([out[3][0], out[3][3]], ["Day Surgery", "Day Surgery Rivoli"])
        self.assertNotIn("Bertolotti", [v for e in table.entries.values() for v in e["variants"]])

    def test_offices_and_disciplines_on_a_list_line_are_no_people(self):
        out, table = mask(["e p.c. ai Medici di Medicina Generale del Distretto", "Ufficio Relazioni con il Pubblico"],
                          names=["Ufficio Relazioni"])
        self.assertEqual(out, ["e p.c. ai Medici di Medicina Generale del Distretto", "Ufficio Relazioni con il Pubblico"])
        self.assertEqual(table.entries, {})

    @unittest.skipUnless(importlib.util.find_spec("openpyxl"), "openpyxl not installed")
    def test_xlsx_round_trip(self):
        from openpyxl import Workbook
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "elenco.xlsx"
            wb = Workbook()
            for r in self.ROWS:
                wb.active.append(r)
            wb.save(src)
            doc = fmt.read_document(src)
            table = eng.Table()
            sheets, _ = fmt.mask_sheets(doc.sheets, StubDetector(), table, context(), "elenco.xlsx")
            out = Path(d) / "masked.xlsx"
            fmt.write_masked(doc, sheets, out)
            restored, n, _ = fmt.restore_file(out, table, Path(d) / "restored")
            back = fmt.read_document(restored).sheets[0][1]
            self.assertEqual(back[1][2], CF)
            self.assertEqual(n, 8)  # row 1: surname, name, CF, birth date, phone; row 2: surname, name, birth date

    @unittest.skipUnless(importlib.util.find_spec("docx"), "python-docx not installed")
    def test_docx_read_and_restore(self):
        import docx
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "lettera.docx"
            doc = docx.Document()
            doc.add_paragraph("Gentile signora Rosa Usseglio,")
            t = doc.add_table(rows=1, cols=2)
            t.cell(0, 0).text, t.cell(0, 1).text = "CF", CF
            doc.save(src)
            text = fmt.read_document(src).text
            self.assertIn("| CF | " + CF + " |", text)
            out, table = mask([text], names=["Rosa Usseglio"])
            draft = Path(d) / "bozza.docx"
            dd = docx.Document()
            dd.add_paragraph(out[0].splitlines()[0])
            dd.save(draft)
            restored, n, _ = fmt.restore_file(draft, table, Path(d) / "restored")
            self.assertEqual(docx.Document(str(restored)).paragraphs[0].text, "Gentile signora Rosa Usseglio,")


class CliTest(unittest.TestCase):
    """The script, run as Claude runs it: nothing it prints shows a value or an original file name."""

    def run_cli(self, data, project, *args):
        return subprocess.run([sys.executable, str(HERE / "pseudonymize.py"), "--data", str(data), "--project", str(project), *args],
                              capture_output=True, text=True, encoding="utf-8")

    def test_init_mask_review_restore_status(self):
        with tempfile.TemporaryDirectory() as d:
            data, project = Path(d) / "data", Path(d) / "progetto"
            project.mkdir()
            r = self.run_cli(data, project, "init")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("Read(pseudonymize-private/**)",
                          json.loads((project / ".claude" / "settings.json").read_text())["permissions"]["deny"])
            self.assertIn("/pseudonymize-private/", (project / ".gitignore").read_text())
            # the working rules load in every later session of the project, the skill only on /aldogor-pseudonymize
            rules = (project / ".claude" / "rules" / "pseudonymize.md").read_text(encoding="utf-8")
            self.assertIn("`masked/`", rules)
            self.assertIn("[DA_COMPLETARE]", rules)
            secret =["Ferrero", "Giuseppina", CF, TS_NUM, IBAN, "347 512 8830", "m.ferrero@example.org"]
            (project / "pseudonymize-private" / "always.txt").write_text("Giuseppina Ferrero\n", encoding="utf-8")
            (project / "pseudonymize-private" / "originals" / "Relazione_Ferrero.txt").write_text(
                f"Assistita: Giuseppina Ferrero, CF {CF}, tessera {TS_NUM}, IBAN {IBAN}, "
                f"cell. 347 512 8830, m.ferrero@example.org\n", encoding="utf-8")
            r = self.run_cli(data, project, "mask", "--detector", "regex-only")
            self.assertEqual(r.returncode, 0, r.stderr)
            for s in secret:
                self.assertNotIn(s, r.stdout)
            masked = list((project / "masked").iterdir())
            self.assertEqual(len(masked), 1)
            body = masked[0].read_text(encoding="utf-8")
            for s in secret:
                self.assertNotIn(s, body)
                self.assertNotIn(s, masked[0].name)
            r = self.run_cli(data, project, "review")
            self.assertEqual(r.returncode, 0, r.stderr)
            page = (project / "pseudonymize-private" / "review.html").read_text(encoding="utf-8")
            self.assertIn("dal più frequente", page)
            self.assertIn("Campione per il conteggio", page)
            r = self.run_cli(data, project, "mask", "--detector", "regex-only", "--fresh")
            self.assertEqual(r.returncode, 0, r.stderr)
            for s in secret:
                self.assertNotIn(s, r.stdout)
            backups = list((project / "pseudonymize-private").glob("backup-*"))
            self.assertEqual(len(backups), 1)
            self.assertTrue((backups[0] / "table.json").exists())
            self.assertEqual(len(list((backups[0] / "masked").iterdir())), 1)
            self.assertEqual(len(list((project / "masked").iterdir())), 1)
            draft = project / "bozza.md"
            draft.write_text("Si propone il rimborso a [FULLNAME_1] su [IBAN_1].", encoding="utf-8")
            r = self.run_cli(data, project, "restore", str(draft))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertNotIn(IBAN, r.stdout)
            restored = (project / "pseudonymize-private" / "restored" / "bozza.md").read_text(encoding="utf-8")
            self.assertEqual(restored, f"Si propone il rimborso a Giuseppina Ferrero su {IBAN}.")
            r = self.run_cli(data, project, "status")
            for s in secret:
                self.assertNotIn(s, r.stdout)


if __name__ == "__main__":
    unittest.main()
