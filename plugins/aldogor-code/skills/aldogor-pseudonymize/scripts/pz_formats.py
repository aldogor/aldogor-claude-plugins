"""Reading originals, writing masked copies and restored files, by format.

Plain text (.txt, .md) is masked as it is. Word (.docx) and PDF with a text layer become Markdown, the
form Claude reads best. CSV and Excel (.xlsx) stay tables and are masked by column: a column whose
header names a personal field (cognome, nome, codice fiscale, data di nascita, telefono, indirizzo,
email, tessera, iban) is replaced whole, the other cells go through the detector one by one, and the
header row and the separators are never touched. In a column that names an organisation unit (servizio,
reparto, centro di costo, its description) the model's people are set aside: hospitals and towns there bear
people's names. A PDF without a text layer (a scan) is reported and left alone.

python-docx, pypdf and openpyxl live in the private environment and are imported only when a file of
their format is met, so the plain-text path and the tests need the standard library alone.
"""

import csv
import io
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import pz_engine as eng

TEXT_EXT = {".txt", ".md", ".markdown"}
SUPPORTED = TEXT_EXT | {".docx", ".pdf", ".csv", ".xlsx"}

# Header of a personal column -> how its cells are masked. SURNAME and GIVEN cells of one row form one
# person. A place of birth stays in clear, like every municipality.
PERSONAL_COLUMNS = [
    (re.compile(r"luogo|comune|citt[aà]|provincia", re.I), None),
    (re.compile(r"^(?:cognome|surname|last\s*name)$", re.I), "SURNAME"),
    (re.compile(r"^(?:nome|first\s*name|given\s*name)$", re.I), "GIVEN"),
    (re.compile(r"nominativo|assistit|paziente|utente|cognome\s*(?:e|/|-)\s*nome|nome\s*(?:e|/|-)\s*cognome"
                r"|intestatari|familiar|caregiver|tutore|amministratore\s+di\s+sostegno", re.I), "FULLNAME"),
    (re.compile(r"codice\s*fiscale|^c\.?\s?f\.?$", re.I), "CF"),
    (re.compile(r"nascita|^d\.?\s?d\.?\s?n\.?$|^dob$", re.I), "BIRTHDATE"),
    (re.compile(r"telefono|cellulare|^tel\.?$|^cell\.?$|recapito", re.I), "TELEPHONENUM"),
    (re.compile(r"indirizzo|residenza|domicilio|^via$", re.I), "STREET"),
    (re.compile(r"e-?mail|^pec$", re.I), "EMAIL"),
    (re.compile(r"tessera|^ts$|^team$", re.I), "TS"),
    (re.compile(r"iban", re.I), "IBAN"),
]


# Header of an organisation-unit column (a service, a ward, a cost centre and its description): its cells name
# offices, wards, hospitals and places, so the model's people there are set aside (eng.first_pass, `org`), while
# titles, always.txt and the people already known are masked there as anywhere else.
ORG_COLUMN = re.compile(r"servizi|struttur|reparto|\bsede\b|centro\s*di\s*costo|\bcdc\b|c\.d\.c\.|unit[aà]\s*operativ"
                        r"|^u\.?o\.?[cs]?\.?d?\.?$|presidio|ufficio|dipartiment|distrett|azienda|^ente$|^area$", re.I)


def column_kind(header: str):
    for pat, kind in PERSONAL_COLUMNS:
        if pat.search(header.strip()):
            return kind
    return None


@dataclass
class Document:
    """An original as the engine sees it."""
    path: Path
    kind: str                       # "text", "table" or "skipped"
    text: str = ""
    sheets: list = field(default_factory=list)   # [(sheet name, rows as lists of strings)]
    out_ext: str = ".md"
    delimiter: str = ";"
    note: str = ""                  # why a file was skipped


def _read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.strftime("%d/%m/%Y") if (v.hour, v.minute) == (0, 0) else v.strftime("%d/%m/%Y %H:%M")
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _docx_text(path: Path) -> str:
    """Paragraphs and tables in document order, headers and footers first; tables as Markdown rows."""
    import docx  # python-docx
    from docx.table import Table as DocxTable
    from docx.text.paragraph import Paragraph
    d = docx.Document(str(path))
    out = []
    for section in d.sections:
        for part in (section.header, section.footer):
            out += [p.text for p in part.paragraphs if p.text.strip()]
    for child in d.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            out.append(Paragraph(child, d).text)
        elif tag == "tbl":
            for row in DocxTable(child, d).rows:
                out.append("| " + " | ".join(c.text.replace("\n", " ") for c in row.cells) + " |")
    return "\n".join(out)


def _pdf_text(path: Path) -> tuple[str, int]:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    pages = [p.extract_text() or "" for p in reader.pages]
    return "\n\n".join(pages), len(pages)


def read_document(path: Path) -> Document:
    ext = path.suffix.lower()
    if ext in TEXT_EXT:
        return Document(path, "text", text=_read_text_file(path), out_ext=ext)
    if ext == ".docx":
        return Document(path, "text", text=_docx_text(path), out_ext=".md")
    if ext == ".pdf":
        text, n = _pdf_text(path)
        if len(re.sub(r"\s", "", text)) < 40 * max(n, 1):
            return Document(path, "skipped", note="no text layer (a scan): needs OCR, not handled")
        return Document(path, "text", text=text, out_ext=".md")
    if ext == ".csv":
        text = _read_text_file(path)
        try:
            delim = csv.Sniffer().sniff(text[:4096], delimiters=";,\t").delimiter
        except csv.Error:
            delim = ";"
        rows = list(csv.reader(io.StringIO(text), delimiter=delim))
        return Document(path, "table", sheets=[("", rows)], out_ext=".csv", delimiter=delim)
    if ext == ".xlsx":
        from openpyxl import load_workbook
        wb = load_workbook(str(path), data_only=True, read_only=True)
        try:
            sheets = [(ws.title, [[_cell(v) for v in row] for row in ws.iter_rows(values_only=True)]) for ws in wb.worksheets]
        finally:
            wb.close()  # read-only mode keeps the file open until closed
        return Document(path, "table", sheets=sheets, out_ext=".xlsx")
    return Document(path, "skipped", note=f"format {ext or 'without extension'} not handled")


# --------------------------------------------------------------------------- #
# Masking tables
# --------------------------------------------------------------------------- #
def header_index(rows: list[list[str]], limit: int = 15):
    """The header row: the first of the opening rows with a personal column. Spreadsheets often open with a
    title, a date or a teacher's name above the header; None when no row names a personal column."""
    for i, row in enumerate(rows[:limit]):
        if any(column_kind(c) for c in row if c and c.strip()):
            return i
    return None


def _kinds(rows):
    h = header_index(rows)
    return h, ({j: column_kind(c) for j, c in enumerate(rows[h])} if h is not None else {})


def _org_columns(rows, h) -> set:
    """The organisation-unit columns of a table whose header row is h (ORG_COLUMN), personal columns aside."""
    if h is None:
        return set()
    return {j for j, c in enumerate(rows[h]) if c and column_kind(c) is None and ORG_COLUMN.search(c.strip())}


NAME_KINDS = {"SURNAME", "GIVEN", "FULLNAME"}


def cell_kind(v: str, kind):
    """The kind a cell is masked as: its column's, unless the cell is a note written in that column (a
    sentence under a surname column, a legend under the names), which goes to the detector as text."""
    if kind is None:
        return None
    if kind in NAME_KINDS:
        return kind if eng.looks_like_name(v) else None
    return kind if len(v.split()) <= 5 else None


def row_kinds(row, kinds) -> dict:
    """The kind each cell of a data row is masked as (cell_kind), with one exception: a surname or given name
    made only of words that also name roles, offices or places ("Medici", "Strada") is a name when the other
    name column of the row holds one. Every path that reads a row (its person, its free cells, its masked
    cells) takes the kinds from here, so a cell is either a name part or free text, never both."""
    out = {j: cell_kind(row[j], k) if j < len(row) and row[j].strip() else None for j, k in kinds.items()}
    present = {k for k in out.values() if k in NAME_KINDS}
    for j, k in kinds.items():
        if k in ("SURNAME", "GIVEN") and out[j] is None and j < len(row) and row[j].strip():
            v = row[j].strip()
            other = "GIVEN" if k == "SURNAME" else "SURNAME"
            if (other in present and len(v.split()) <= 3 and not re.search(r"[\d:@/]", v)
                    and eng.only_role_or_office(v)):
                out[j] = k
    return out


def _part(row, rk, k) -> str:
    return " ".join(row[j].strip() for j, kk in rk.items() if kk == k)


def _person(row, rk) -> str:
    return f"{_part(row, rk, 'GIVEN')} {_part(row, rk, 'SURNAME')}".strip()


# A table that names more people than this is a directory (a staff census, a contact list): its people enter
# the project-wide pass by full name only, until a document names them (eng.Table.register_people).
DIRECTORY_ROWS = 50


def table_people(rows: list[list[str]], source: str) -> list[tuple[str, str, dict]]:
    """The person of each data row, from its SURNAME, GIVEN and FULLNAME columns, as (value, source, info)
    for eng.Table.register_people."""
    h, kinds = _kinds(rows)
    if h is None:
        return []
    found = []
    for row in rows[h + 1:]:
        rk = row_kinds(row, kinds)
        given, surname = _part(row, rk, "GIVEN"), _part(row, rk, "SURNAME")
        person = f"{given} {surname}".strip()
        if person:
            found.append((person, {"given": given, "surname": surname} if given and surname else {}))
        found += [(row[j].strip(), {}) for j, k in rk.items() if k == "FULLNAME"]
    directory = len({v.casefold() for v, _ in found}) > DIRECTORY_ROWS
    return [(v, source, dict(info, directory=directory)) for v, info in found]


def sheet_free_cells(sheets) -> tuple[list[str], list[tuple[int, int, int]], list[bool]]:
    """Cells that go through the detector, where each sits (sheet, row, column), and whether it sits in an
    organisation-unit column: every cell above the header, and the cells of non-personal columns below it.
    The header row is never masked."""
    free, where, org = [], [], []
    for s, (_, rows) in enumerate(sheets):
        h, kinds = _kinds(rows)
        org_cols = _org_columns(rows, h)
        for i, row in enumerate(rows):
            if i == h:
                continue
            rk = row_kinds(row, kinds) if h is not None and i > h else {}
            for j, v in enumerate(row):
                if v.strip() and rk.get(j) is None:
                    free.append(v)
                    where.append((s, i, j))
                    org.append(h is not None and i > h and j in org_cols)
    return free, where, org


def build_sheets(sheets, where, results, table, source: str) -> tuple[list, list]:
    """Masked sheets from the detector's results on the free cells and the table for personal columns;
    returns the sheets and the changed cells for the review page: (sheet, row, col, original, masked)."""
    masked_free = {w: r for w, r in zip(where, results)}
    out, cells = [], []
    for s, (name, rows) in enumerate(sheets):
        h, kinds = _kinds(rows)
        new_rows = []
        for i, row in enumerate(rows):
            if i == h:
                new_rows.append(list(row))
                continue
            rk = row_kinds(row, kinds) if h is not None and i > h else {}
            person = _person(row, rk)
            new = []
            for j, v in enumerate(row):
                kind = rk.get(j)
                if not v.strip():
                    new.append(v)
                    continue
                if kind in ("SURNAME", "GIVEN"):
                    m = table.assign("FULLNAME", person, source, row=True)
                elif kind is not None:
                    m = table.assign(kind, v, source)
                else:
                    m = masked_free[(s, i, j)].text
                new.append(m)
                if m != v:
                    cells.append((name, i, j, v, m))
            new_rows.append(new)
        out.append((name, new_rows))
    return out, cells


def mask_sheets(sheets, detector, table, ctx, source: str) -> tuple[list, list]:
    """Mask the sheets of one document on their own (the project flow masks all documents in one pass)."""
    people = [p for _, rows in sheets for p in table_people(rows, source)]
    free, where, org = sheet_free_cells(sheets)
    results = eng.mask_texts(free, detector, table, ctx, [source] * len(free), people=people, org=org)
    return build_sheets(sheets, where, results, table, source)


def write_masked(doc: Document, masked, out_path: Path) -> None:
    """Write a masked text or masked sheets."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if doc.kind == "text":
        out_path.write_text(masked, encoding="utf-8")
    elif doc.out_ext == ".csv":
        with out_path.open("w", encoding="utf-8", newline="") as f:
            csv.writer(f, delimiter=doc.delimiter, lineterminator="\n").writerows(masked[0][1])
    else:
        from openpyxl import Workbook
        wb = Workbook()
        wb.remove(wb.active)
        for name, rows in masked:
            ws = wb.create_sheet(title=name or "Foglio1")
            for row in rows:
                ws.append(row)
        wb.save(str(out_path))


# --------------------------------------------------------------------------- #
# Restoring
# --------------------------------------------------------------------------- #
def restore_file(src: Path, table, out_dir: Path, to_docx: bool = False) -> tuple[Path, int, list[str]]:
    """Write src with real values into out_dir; returns the output path, the count, unknown placeholders."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = src.suffix.lower()
    total, unknown = 0, set()

    def sub(text):
        nonlocal total
        t, n, u = eng.restore_text(text, table)
        total += n
        unknown.update(u)
        return t

    out = out_dir / src.name
    if ext in TEXT_EXT:
        out.write_text(sub(_read_text_file(src)), encoding="utf-8")
        if to_docx and ext in (".md", ".markdown"):
            pandoc = shutil.which("pandoc")
            if not pandoc:
                raise RuntimeError("pandoc is not installed: the restored Markdown is written, not the .docx")
            docx_out = out.with_suffix(".docx")
            subprocess.run([pandoc, str(out), "-o", str(docx_out)], check=True)
            out = docx_out
    elif ext == ".csv":
        text = _read_text_file(src)
        try:
            delim = csv.Sniffer().sniff(text[:4096], delimiters=";,\t").delimiter
        except csv.Error:
            delim = ";"
        rows = [[sub(c) for c in r] for r in csv.reader(io.StringIO(text), delimiter=delim)]
        with out.open("w", encoding="utf-8", newline="") as f:
            csv.writer(f, delimiter=delim, lineterminator="\n").writerows(rows)
    elif ext == ".xlsx":
        from openpyxl import load_workbook
        wb = load_workbook(str(src))
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for c in row:
                    if isinstance(c.value, str):
                        c.value = sub(c.value)
        wb.save(str(out))
    elif ext == ".docx":
        import docx
        d = docx.Document(str(src))
        paragraphs = list(d.paragraphs)
        for t in d.tables:
            for row in t.rows:
                for cell in row.cells:
                    paragraphs += cell.paragraphs
        for section in d.sections:
            paragraphs += section.header.paragraphs + section.footer.paragraphs
        for p in paragraphs:
            if "[" in p.text and p.runs:
                new = sub(p.text)
                if new != p.text:  # the paragraph keeps the format of its first run
                    p.runs[0].text = new
                    for r in p.runs[1:]:
                        r.text = ""
        d.save(str(out))
    else:
        raise RuntimeError(f"cannot restore a {ext or 'file without extension'} file")
    return out, total, sorted(unknown)
