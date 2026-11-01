"""Detection, rules, the project table and masking for aldogor-pseudonymize.

The model sits behind one method, `detect_many(texts)`, so the detector can change
without touching the rest and the tests run with a stub detector. This module is
standard library only; `RizzoDetector` imports transformers when it is built, inside
the private environment that `pseudonymize.py setup` creates.

A text is masked in two passes over a whole project, so that the same person gets
the same placeholder in every document:
  1. candidates from the detector (model and regex net), this plugin's rules and
     the user's `always` list; the person names among them are registered in the
     project table, the longer names first, so that a lone surname joins the right
     person or is flagged as ambiguous;
  2. the same candidates plus every known name still in clear (the project-wide
     pass), merged, then replaced by the table's placeholders.

Adapted from rizzo-pii (https://github.com/Rizzo-AI-Academy/rizzo-pii, MIT,
commit 30d6f9c): `chunk_text`, the model call in `RizzoDetector` and `merge` follow
its src/app/app.py; its regex and checksum net, src/app/detectors.py, is vendored
unchanged in vendor/rizzo_pii/.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from vendor.rizzo_pii import detectors as rz

# The model revision this plugin is evaluated with: rizzoaiacademy/rizzo-pii-0.3B, tag v1.5.0.
MODEL_REPO = "rizzoaiacademy/rizzo-pii-0.3B"
MODEL_REVISION = "a1c3c83827eca22e9675e30c1111c4641caf5901"

# Tags of the detector the work needs in clear: ages, sex, times, amounts, organizations, provinces,
# municipalities, dates (the birth date is masked by this plugin's own rule, the timeline stays), act
# numbers (protocollo, repertorio: they name documents, and internal documents cite them; the case and
# booking numbers that point to a person are masked by this plugin's own rule) and cadastral data, which
# the model reads into classification numbers and codes.
EXCLUDED_DEFAULT = ("AGE", "GENDER", "TIME", "AMOUNT", "ORG", "PROVINCE", "CITY", "DATE", "DOCID", "CATASTO")

# Types with a check character or a fixed shape: a detection of the model counts only with that shape,
# compared without spaces, dots and hyphens. Cost-centre and product codes the model reads as plates or
# identity documents fail it.
SHAPES = {
    "CF": re.compile(r"^[A-Za-z]{6}[\dA-Za-z]{2}[A-Za-z][\dA-Za-z]{2}[A-Za-z][\dA-Za-z]{3}[A-Za-z]$"),
    "IBAN": re.compile(r"^[A-Za-z]{2}\d{2}[A-Za-z0-9]{11,30}$"),
    "PIVA": re.compile(r"^\d{11}$"),
    "CREDITCARDNUMBER": re.compile(r"^\d{13,19}$"),
    "TARGA": re.compile(r"^[A-Za-z]{2}\d{3}[A-Za-z]{2}$"),
    # identity card (CA12345AB), passport and paper identity card (YA1234567), driving licence (TO1234567A)
    "ID_DOC": re.compile(r"^(?:[A-Za-z]{2}\d{5}[A-Za-z]{2}|[A-Za-z]{2}\d{7}[A-Za-z]?|U1[A-Za-z0-9]{7}[A-Za-z])$"),
}
EMAIL_RX = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# A street of the model counts when it opens with a street word or a house number follows it; a postcode
# or a house number of the model counts when it follows a street on the same line. District and valley
# names ("Val Susa", "Area Metropolitana") and cost-centre codes fail.
STREET_WORD = re.compile(
    r"^\W*(?:via|viale|v\.\s?le|corso|c\.\s?so|piazza|p\.\s?zza|p\.\s?za|piazzale|largo|strada|str\.|vicolo|"
    r"borgata|b\.\s?ta|borgo|frazione|fraz\.|località|loc\.|contrada|lungo\w+|salita|vico|traversa)(?!\w)",
    re.IGNORECASE)
HOUSE_NUMBER_AFTER = re.compile(r"^[ \t]*,?[ \t]*(?:n\.?|nr\.?|n°|civ\.?)?[ \t]*\d{1,4}(?!\d)", re.IGNORECASE)
NEAR_STREET = 30
# A number right after "Prot." is a protocol number, which stays, not a phone number.
AFTER_PROT = re.compile(r"\bprot(?:ocollo)?\.?\s*(?:n(?:\.|°|r\.?|um\.?)?\s*)?[:.]?\s*$", re.IGNORECASE)

# Sources whose spans are exact by construction and outrank the model in the merge.
STRICT_SOURCES = {"regex", "rule", "table", "always"}

# Chunking for the model, as rizzo-pii does it: about 180 subword tokens, under the 512 of training.
MAX_WORDS, OVERLAP = 120, 20
# Chunks the model reads at once.
BATCH_SIZE = 8

# Titles and greetings stripped from a person's name before it is compared with the table.
TITLES = re.compile(
    r"^(?:(?:sig\.?\s?ra|sigra|sig|signora|signor|signore|dott\.?\s?ssa|dottssa|dott|dottor|dottore|"
    r"dottoressa|dr|prof\.?\s?ssa|prof|avv|ing|geom|rag|arch|gent\.?\s?mo|gent\.?\s?ma|egr)\.?\s+)+",
    re.IGNORECASE,
)
WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?")

# Identifiers compared without their separators, and phone numbers without the country prefix.
COMPACT_LABELS = {"CF", "IBAN", "TS", "CREDITCARDNUMBER", "PIVA", "TELEPHONENUM", "ID_DOC", "TARGA", "DOCID"}

_MONTHS = (r"gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre|"
           r"genn?|febb?|mar|apr|magg?|giu|lug|ago|sett?|ott|nov|dic")
DATE = (r"(?:(?:0?[1-9]|[12]\d|3[01])[/.\-](?:0?[1-9]|1[0-2])[/.\-](?:19|20)?\d{2}"
        r"|(?:0?[1-9]|[12]\d|3[01])\s?(?:°|º)?\s+(?:" + _MONTHS + r")\.?\s+(?:19|20)\d{2})")
# A birth date: a date within 40 characters of "nato", "nata", "nascita" or "d.d.n.", on the same line.
BIRTH = re.compile(r"\b(?:nat[oa]|nascita|d\.?\s?d\.?\s?n\.?)\b[^\n]{0,40}?(?P<v>" + DATE + r")(?!\d)", re.IGNORECASE)
# Tessera sanitaria (TEAM card): 20 digits starting 80380; validated when the Luhn digit passes.
TS = re.compile(r"(?<!\d)80380(?:[ ]?\d){15}(?!\d)")
# Case and booking numbers: the number after a word that names one. rizzo-pii's own DOCID rule knows
# only R.G., protocollo and repertorio; here the number alone is masked and the word stays.
CASE_WORDS = (r"pratica|prenotazione|nosologico|cartella(?:\s+clinica)?|impegnativa|ricetta(?:\s+elettronica)?|"
              r"n\.?\s?r\.?\s?e\.?|nre|sdo|codice\s+prenotazione|fascicolo|istanza|domanda|richiesta|verbale")
CASE = re.compile(
    r"\b(?:" + CASE_WORDS + r")\b(?-i:\s+[A-Z]{2,6}\b)?\s*(?:n(?:\.|°|º|r\.?|um\.?|umero)\s*)?[:#]?\s*"
    r"(?P<v>(?=[A-Za-z0-9/.\-]*\d)[A-Za-z0-9][A-Za-z0-9/.\-]{3,24}[A-Za-z0-9])",
    re.IGNORECASE,
)
# Words after which a number is a case number only when "n." follows (generic words).
_CASE_NEEDS_N = re.compile(r"^(?:istanza|domanda|richiesta|verbale)\b", re.IGNORECASE)
_CASE_HAS_N = re.compile(r"\bn(?:\.|°|º|r\.?|um\.?|umero)", re.IGNORECASE)

# A name right after a greeting that opens a message or a sentence ("ciao fede,", "cara paola!"): the
# lowercase register of internal email, where the model misses names. Role nouns, terms of endearment
# and words such as "tutti" are not names; any other word there is taken for one ("ciao fede,").
GREETING = re.compile(
    r"(?:^|(?<=[\n.!?])\s*)(?:ciao|cara|caro|care|cari|carissim[aoie]|gentile|gentilissim[aoie]|gent\.?\s?m[oa]"
    r"|buongiorno|buonasera|salve|grazie)\s+(?P<v>[^\W\d_]{3,})(?=\s*[,!\n])",
    re.IGNORECASE | re.MULTILINE,
)
NOT_NAMES = {
    "tutti", "tutte", "tutto", "voi", "ragazzi", "ragazze", "colleghi", "colleghe", "collega", "amici", "team",
    "gruppo", "mille", "ancora", "infinite", "anticipo", "davvero", "molte", "molto", "dottore", "dottoressa",
    "dott", "direttore", "direttrice", "signora", "signore", "signori", "professore", "professoressa",
    "presidente", "sindaco", "sindaca", "assessore", "assessora", "coordinatore", "coordinatrice", "infermiere",
    "infermiera", "responsabile", "utente", "cittadino", "cittadina", "paziente", "familiari", "famiglia",
    "dirigente", "segreteria", "ufficio", "staff", "ingegnere", "avvocato", "commissione", "comitato",
    "bella", "bello", "belli", "belle", "tesoro", "amore", "cara", "caro", "care", "cari", "carissima",
    "carissimo", "gentilissima", "gentilissimo", "mondo", "ancora", "sempre", "intanto", "comunque",
}
# Functional mailboxes stay in clear: a local part that starts with an office or a function word.
FUNCTIONAL_MAIL = re.compile(
    r"^(?:urp|protocollo|segreteria|info|direzione|distretto|ufficio|amministrazione|personale|formazione|"
    r"comunicazione|stampa|pec|posta|privacy|dpo|rpd|cup|prenotazioni|accettazione|relazioni|qualita|acquisti|"
    r"economato|tecnico|servizi|servizio|sportello|centralino|helpdesk|supporto|noreply|no-reply|webmaster|admin|"
    r"aziendale|asl|sanita|igiene|prevenzione|veterinari[ao]|farmacia|consultorio|poliambulatorio|dipartimento|"
    r"sert|serd|csm|uvg|adi|cure|medicina|coordinamento|anagrafe|sindaco|comune|cot|pua|cdc|casa|centro|"
    r"ambulatorio|reparto|ospedale|presidio|guardia|continuita|vaccinazioni|screening|ufficio)(?:[._-][a-z0-9]+)*@",
    re.IGNORECASE,
)

# Conventions of documents that mark a name whatever the model says.
# A name token: capitalized, two letters or more, possibly with an elided prefix (D'Amico, Dell'Acqua) or
# a hyphen. A run of them stays on one line, so the "A" of "A.S.L." on the next line is no part of a name.
NAME_TOKEN = r"(?:[A-ZÀ-Ý][a-zà-ÿ]*['’])?[A-ZÀ-Ý][\w'’\-]+"
NAME_RUN = NAME_TOKEN + r"(?:[ \t]+" + NAME_TOKEN + r"){0,2}"
_TITLE = (r"(?:sig\.?\s?ra|sigra|sig\.|signora|signor|dott\.?\s?ssa|dott\.|dottor|dottoressa|dr\.?\s?ssa|dr\.|prof\.?\s?ssa|prof\."
          r"|inf\.|avv\.|ing\.|geom\.|rag\.)")
# 1. A title followed by capitalized words ("dott. Re", "dott.ssa Paola Usseglio") or, in the lowercase register
#    of chats, by one lowercase word ("sig.ra martina").
TITLE_NAME = re.compile(r"(?<!\w)(?i:" + _TITLE + r")\s+(?P<v>" + NAME_RUN + r")")
TITLE_LOWER = re.compile(r"(?<!\w)" + _TITLE + r"\s+(?P<v>[a-zà-ÿ][a-zà-ÿ'’]{2,})\b", re.IGNORECASE)
# 2. Capitalized words followed by an initial ("Messina G.", "El Amrani K."), the form of attendance lists.
WITH_INITIAL = re.compile(r"(?<![\w.])(?P<v>" + NAME_RUN + r")\s+[A-Z]\.(?=[\s,;:)]|$)")
# 3. The names on a line that lists people: Presenti, Assenti, Verbalizza, Partecipanti, In copia.
ATTENDANCE = re.compile(
    r"^[\s*_#>-]*(?:presenti|assenti(?:\s+giustificati)?|assente\s+giustificat[oa]|collegat[ie](?:\s+da\s+remoto)?"
    r"|verbalizza|verbalizzante|partecipanti|hanno\s+partecipato|invitati|in\s+copia|e\s+p\.\s?c\.)[\s*_]*:?[\s*_]*"
    r"(?P<rest>.+)$",
    re.IGNORECASE | re.MULTILINE,
)
# A capitalized run that holds one of these words names an office, a place or a part of a document, not a
# person ("Ufficio Formazione", "Via Roma", "Allegato A.", "Vitamina D."): the run is dropped whole.
ORG_WORDS = {
    "via", "viale", "piazza", "corso", "largo", "strada", "borgata", "frazione", "località", "san", "santa", "santo", "val",
    "ospedale", "casa", "case", "distretto", "comune", "regione", "provincia", "prot", "rep", "art", "articolo", "nota",
    "allegato", "tabella", "figura", "fig", "cap", "capitolo", "punto", "sezione", "vitamina", "epatite", "gruppo",
    "tipo", "classe", "livello", "fascia", "area", "zona", "lotto", "fase", "modulo", "sala", "piano", "scala",
    "edificio", "padiglione", "reparto", "letto", "stanza", "coordinamento", "ufficio", "servizio", "dipartimento",
    "direzione", "consorzio", "struttura", "unità", "segreteria", "ambulatorio", "poliambulatorio", "consultorio",
    # disciplines and offices: "Medici di Medicina Generale", "Ufficio Relazioni con il Pubblico"
    "medicina", "chirurgia", "pediatria", "cardiologia", "geriatria", "oncologia", "psichiatria", "ortopedia",
    "neurologia", "nefrologia", "radiologia", "anestesia", "rianimazione", "ginecologia", "ostetricia", "urologia",
    "dermatologia", "oculistica", "pneumologia", "gastroenterologia", "endocrinologia", "diabetologia",
    "riabilitazione", "farmacia", "laboratorio", "igiene", "prevenzione", "vaccinazioni", "screening", "guardia",
    "continuità", "emergenza", "urgenza", "pronto", "soccorso", "sanità", "salute", "dipendenze", "mentale",
    "relazioni", "pubblico", "formazione", "personale", "risorse", "umane", "qualità", "accreditamento",
    "protocollo", "legenda", "turni", "ferie", "riposo", "generale", "sanitaria", "sanitario", "territoriale",
}
# Roles and function words that stand next to a name: trimmed from the ends of a run ("Direttore Rossi").
ROLE_WORDS = {
    "direttore", "direttrice", "coordinatore", "coordinatrice", "sindaco", "sindaca", "assessore", "assessora",
    "presidente", "responsabile", "referente", "dirigente", "infermiere", "infermiera", "medico", "medici", "oss",
    "assistente", "sociale", "fisioterapista", "segretario", "segretaria", "collega", "colleghi", "dottore",
    "dottoressa", "uditrice", "uditore", "ospite", "rappresentante", "delegato", "delegata", "tecnico", "tecnica",
    "amministrativo", "amministrativa", "il", "la", "lo", "le", "gli", "i", "un", "una", "e", "ed", "con", "per",
    "del", "della", "dei", "degli", "vedi", "cfr",
}
NOT_NAME_WORDS = ORG_WORDS | ROLE_WORDS
# Particles of a surname: before an initial, "El Amrani K." and "De Luca M." keep both words.
PARTICLES = {"el", "al", "de", "del", "della", "di", "da", "dal", "lo", "la", "le", "van", "von", "mac", "mc", "ben",
             "abu", "bin", "dos", "da", "du"}
# Function words that never are a name after a title ("dott. di guardia", "dott.ssa della COT").
STOPWORDS = {"di", "del", "della", "dello", "dei", "degli", "delle", "da", "dal", "dalla", "dai", "in", "nel",
             "nella", "per", "con", "su", "sul", "sulla", "tra", "fra", "che", "il", "lo", "la", "gli", "le", "un",
             "una", "uno", "al", "alla", "ai", "alle", "non", "anche", "già", "turno", "guardia", "reperibile"}
# Place prepositions: after one, a municipality's name is a place ("Comune di Avigliana"), not the person who
# bears it as a surname, and the project-wide pass leaves it.
PLACE_PREPS = ("di", "a", "da", "in", "per", "presso", "verso", "tra", "fra", "su", "al", "alla", "del", "della",
               "nel", "nella", "dal", "dalla")
# Words of a known name that never travel alone in the project-wide pass: dates are written with them
# ("12 ottobre", "lunedì") far more often than the people who bear them as names.
CALENDAR_WORDS = {"gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre",
                  "ottobre", "novembre", "dicembre", "lunedì", "martedì", "mercoledì", "giovedì", "venerdì",
                  "lunedi", "martedi", "mercoledi", "giovedi", "venerdi", "sabato", "domenica"}
# What may stand before a known name written in lowercase: an article, a title or a greeting ("la martina",
# "sig.ra martina", "ciao fede"). Anywhere else a lowercase word is the ordinary word.
LOWER_CUE = (r"(?:(?<![\w.])(?i:la|il|lo|sig\.?\s?ra|sigra|sig\.|signora|signor|dott\.?\s?ssa|dott\.|dottor|"
             r"dottoressa|dr\.?\s?ssa|dr\.|inf\.|ciao|cara|caro|gentile|gent\.?\s?m[oa])[ \t]+|(?<![\w.])(?i:l)['’])")
_CUE = re.compile(LOWER_CUE)
# A name word this short is matched in lowercase anywhere: nicknames ("gio", "ele", "ste") are written so.
NICKNAME_LETTERS = 4
# Before a common word (the shipped list) in lowercase only an article counts: "la serena" is the colleague.
ARTICLE_CUE = r"(?:(?<![\w.])(?i:la|il|lo)[ \t]+|(?<![\w.])(?i:l)['’])"
LOWER_WORD = re.compile(r"(?<![\w'’])[a-zà-ÿ][a-zà-ÿ'’]*(?!\w)")
URL_OR_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}|(?:https?|ftp)://\S+|www\.\S+", re.IGNORECASE)

# Words after which a lowercase word is probably a name (review page, possible misses).
NAME_CUES = re.compile(r"\b(?:sig\.?\s?ra|signora|signor|sig\.|dott\.?\s?ssa|dott\.|dottor|ciao|caro|cara|gentile)\s+(?P<w>[a-zà-ù]{3,})\b", re.IGNORECASE)


def luhn(digits: str) -> bool:
    """Luhn check over any number of digits (rizzo-pii's luhn_ok stops at 19)."""
    total, alt = 0, False
    for ch in reversed(digits):
        n = int(ch)
        if alt:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
        alt = not alt
    return total % 10 == 0


def norm_value(label: str, value: str) -> str:
    """The form under which two spellings of one value are the same entry of the table."""
    v = value.strip()
    if label in COMPACT_LABELS:
        v = re.sub(r"[\s.\-/]", "", v).upper()
        if label == "TELEPHONENUM":
            v = re.sub(r"^(?:\+39|0039)", "", v)
        return v
    if label in ("EMAIL", "URL"):
        return v.lower()
    return re.sub(r"\s+", " ", v).casefold()


def person_tokens(value: str) -> frozenset:
    """The words of a person's name, titles removed, lowercased; initials ("A.") ignored."""
    v = TITLES.sub("", value.strip())
    return frozenset(t.casefold() for t in WORD.findall(v) if len(t) > 1)


def read_list(path: Path) -> list[str]:
    """Lines of a list file, without blank lines and # comments."""
    if not path or not path.exists():
        return []
    return [l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip() and not l.lstrip().startswith("#")]


@dataclass
class Context:
    """What the rules need besides the text: the lists and the tags left to the model."""
    keep: list[str] = field(default_factory=list)          # terms never masked (services, eponyms, institutions)
    officials: list[str] = field(default_factory=list)     # officials left in clear when acting in role
    always: list[tuple[str, str]] = field(default_factory=list)  # (label, value) always masked
    comuni: set[str] = field(default_factory=set)          # municipality names, casefolded
    common: set[str] = field(default_factory=set)          # common Italian words that are also names, casefolded
    excluded: set[str] = field(default_factory=lambda: set(EXCLUDED_DEFAULT))

    @classmethod
    def load(cls, data_dir: Path, project_cfg: Path | None, excluded=None) -> "Context":
        """Lists shipped with the skill (data_dir) plus the project's own (.pseudonymize/ and the private folder)."""
        ctx = cls()
        ctx.keep = read_list(data_dir / "keep_default.txt")
        ctx.common = {w.casefold() for w in read_list(data_dir / "common_words_it.txt")}
        ctx.comuni = {w.casefold() for w in read_list(data_dir / "comuni_it.txt")}
        if project_cfg:
            ctx.keep += read_list(project_cfg / "keep.txt")
            ctx.officials = read_list(project_cfg / "officials.txt")
        if excluded is not None:
            ctx.excluded = set(excluded)
        return ctx

    def load_always(self, path: Path) -> None:
        """always.txt: one value per line, optionally "LABEL: value" (default FULLNAME)."""
        for line in read_list(path):
            m = re.match(r"^([A-Z_]{2,20}):\s*(.+)$", line)
            self.always.append((m.group(1), m.group(2).strip()) if m else ("FULLNAME", line))


# --------------------------------------------------------------------------- #
# Detectors
# --------------------------------------------------------------------------- #
def chunk_text(text: str, max_words: int = MAX_WORDS, overlap: int = OVERLAP) -> list[tuple[str, int]]:
    """Word-safe chunks with their global offsets (rizzo-pii's chunk_text)."""
    words = list(re.finditer(r"\S+", text))
    if not words:
        return []
    chunks, i = [], 0
    step = max(1, max_words - overlap)
    while i < len(words):
        block = words[i:i + max_words]
        start, end = block[0].start(), block[-1].end()
        chunks.append((text[start:end], start))
        if i + max_words >= len(words):
            break
        i += step
    return chunks


class RizzoDetector:
    """rizzo-pii's model plus its regex and checksum net, on any number of texts at once."""

    name = "rizzo-pii"

    def __init__(self, model_dir: Path):
        from transformers import pipeline  # only inside the private environment
        self.nlp = pipeline("token-classification", model=str(model_dir), tokenizer=str(model_dir),
                            aggregation_strategy="simple", device=-1)

    def detect_many(self, texts: list[str]) -> list[list[dict]]:
        chunks, owners = [], []
        for i, t in enumerate(texts):
            for c, off in chunk_text(t):
                chunks.append(c)
                owners.append((i, off, c))
        found = [[] for _ in texts]
        # Identical chunks (a service written on every row of a census) go through the model once, the
        # shortest first, so that each batch pads little.
        unique = sorted(set(chunks), key=len)
        if unique:
            results = self.nlp(unique, batch_size=BATCH_SIZE)
            if len(unique) == 1 and (not results or isinstance(results[0], dict)):
                results = [results]
            by_chunk = dict(zip(unique, results))
            for i, off, c in owners:
                for e in by_chunk[c]:
                    found[i].append({"label": e["entity_group"], "start": int(e["start"]) + off,
                                     "end": int(e["end"]) + off, "score": float(e["score"]),
                                     "validated": False, "source": "model"})
        for i, t in enumerate(texts):
            found[i].extend(rz.detect_regex(t))
        return found


class RegexOnlyDetector:
    """The regex and checksum net alone: for tests, and for a quick check without the model."""

    name = "regex-only"

    def detect_many(self, texts: list[str]) -> list[list[dict]]:
        return [rz.detect_regex(t) for t in texts]


# --------------------------------------------------------------------------- #
# This plugin's rules
# --------------------------------------------------------------------------- #
def _span(label, start, end, score=2.0, validated=False, source="rule"):
    return {"label": label, "start": start, "end": end, "score": score, "validated": validated, "source": source}


def only_role_or_office(value: str) -> bool:
    """A span made only of office, discipline, role and function words ("Ufficio Formazione") is no person."""
    words = [w.casefold().strip(".,;:'’()") for w in value.split()]
    return bool(words) and all(w in NOT_NAME_WORDS for w in words)


def lone_town(value: str, ctx: "Context") -> bool:
    """A municipality's name and nothing else ("PINEROLO", "Usseglio", "TORRE PELLICE"): the model marks towns
    as people in service names and headings, so alone it is no evidence of a person."""
    toks = person_tokens(value)
    return (len(toks) == 1 and toks <= ctx.comuni) or " ".join(TITLES.sub("", value).split()).casefold() in ctx.comuni


def _joinable(word: str, ctx: "Context") -> bool:
    w = word.casefold()
    return w in ctx.common and w not in NOT_NAME_WORDS and w not in NOT_NAMES


def join_name_words(spans: list[dict], text: str, ctx: "Context") -> list[dict]:
    """A common word that is also a first name, capitalized right next to a name, joins it ("Letizia" before a
    surname the model took alone): the model reads such words as ordinary ones."""
    for i, e in enumerate(spans):
        if e["label"] != "FULLNAME":
            continue
        prev_end = spans[i - 1]["end"] if i else 0
        next_start = spans[i + 1]["start"] if i + 1 < len(spans) else len(text)
        m = re.search(r"([A-ZÀ-Ý][a-zà-ÿ]+)[ \t]+$", text[max(0, e["start"] - 30):e["start"]])
        if m and _joinable(m.group(1), ctx):
            s = e["start"] - len(m.group(0))
            if s >= prev_end and (s == 0 or not text[s - 1].isalnum()):
                e["start"] = s
        m = re.match(r"[ \t]+([A-ZÀ-Ý][a-zà-ÿ]+)(?![\w'’])", text[e["end"]:e["end"] + 30])
        if m and _joinable(m.group(1), ctx) and e["end"] + m.end() <= next_start:
            e["end"] += m.end()
    return spans


def looks_like_name(value: str) -> bool:
    """A value that can be a person's name: one to five words, no digits, no colon, at sign or slash, not
    made only of role and office words. A sentence in a name column or a span gone wrong fails."""
    words = value.split()
    return (0 < len(words) <= 5 and not re.search(r"[\d:@/]", value) and not only_role_or_office(value))


def _name_run(text: str, start: int, end: int, ctx: "Context | None", before_initial: bool = False):
    """The name inside a capitalized run, or None.

    A run that holds an office, place or document word, or a single-word term of the keep list, is not a
    name. Role and function words are trimmed from its ends. Before an initial the name is the last word,
    with a particle before it when there is one ("El Amrani K.").
    """
    keep = {k.casefold() for k in ctx.keep if " " not in k} if ctx else set()
    words = list(re.finditer(r"\S+", text[start:end]))
    if any(w.group().casefold().strip(".,;:") in ORG_WORDS or w.group().casefold() in keep for w in words):
        return None
    while words and words[0].group().casefold().strip(".,;:") in ROLE_WORDS:
        words.pop(0)
    while words and words[-1].group().casefold().strip(".,;:") in ROLE_WORDS:
        words.pop()
    if before_initial and len(words) > 1:
        words = words[-2:] if words[-2].group().casefold().rstrip("'’") in PARTICLES else words[-1:]
    if not words:
        return None
    return start + words[0].start(), start + words[-1].end()


def convention_candidates(text: str, ctx: "Context | None" = None) -> list[dict]:
    """Names marked by a document's conventions: after a title, before an initial, on an attendance line."""
    out = []

    def add(s, e, before_initial=False):
        run = _name_run(text, s, e, ctx, before_initial)
        if run:
            out.append(_span("FULLNAME", run[0], run[1], score=1.5))

    for m in TITLE_NAME.finditer(text):
        add(m.start("v"), m.end("v"))
    for m in TITLE_LOWER.finditer(text):
        w = m.group("v").casefold()
        if w not in STOPWORDS and w not in NOT_NAMES and w not in NOT_NAME_WORDS:
            out.append(_span("FULLNAME", m.start("v"), m.end("v"), score=1.5))
    for m in WITH_INITIAL.finditer(text):
        add(m.start("v"), m.end("v"), before_initial=True)
    for m in ATTENDANCE.finditer(text):
        rest, off = m.group("rest"), m.start("rest")
        # Parenthesized notes on an attendance line are roles or offices ("(OSS, uditrice)"), not names.
        masked = re.sub(r"\([^)]*\)", lambda p: " " * len(p.group()), rest)
        for r in re.finditer(NAME_RUN, masked):
            add(off + r.start(), off + r.end())
    return out


def rule_candidates(text: str, ctx: "Context | None" = None) -> list[dict]:
    """Names after a greeting and by convention, birth dates, tessera sanitaria numbers and case numbers."""
    out = convention_candidates(text, ctx)
    for m in GREETING.finditer(text):
        if m.group("v").casefold() not in NOT_NAMES:
            out.append(_span("FULLNAME", m.start("v"), m.end("v")))
    for m in BIRTH.finditer(text):
        out.append(_span("BIRTHDATE", m.start("v"), m.end("v")))
    for m in TS.finditer(text):
        out.append(_span("TS", m.start(), m.end(), score=3.0, validated=luhn(re.sub(r"\D", "", m.group()))))
    for m in CASE.finditer(text):
        word = m.group(0)
        if _CASE_NEEDS_N.match(word) and not _CASE_HAS_N.search(word[: m.start("v") - m.start()]):
            continue
        out.append(_span("DOCID", m.start("v"), m.end("v")))
    return out


def _phrase_pattern(value: str, case_sensitive: bool) -> re.Pattern:
    words = [re.escape(w) for w in value.split()]
    return re.compile(r"(?<!\w)" + r"\s+".join(words) + r"(?!\w)", 0 if case_sensitive else re.IGNORECASE)


def always_candidates(text: str, ctx: Context) -> list[dict]:
    out = []
    for label, value in ctx.always:
        for m in _phrase_pattern(value, False).finditer(text):
            out.append(_span(label, m.start(), m.end(), score=2.5, source="always"))
    return out


def keep_spans(text: str, ctx: Context) -> list[tuple[int, int]]:
    """Where the keep list, the officials and the functional mailboxes occur.

    Acronyms of the keep list match case-sensitively, the rest in any case. A functional mailbox is kept
    whole, so no source (model, regex, rules, the project-wide pass) masks a piece of it.
    """
    spans = []
    for term in ctx.keep + ctx.officials:
        acronym = term.isupper() and len(term) <= 8
        for m in _phrase_pattern(term, acronym).finditer(text):
            spans.append((m.start(), m.end()))
    for m in EMAIL_RX.finditer(text):
        if FUNCTIONAL_MAIL.match(m.group()):
            spans.append((m.start(), m.end()))
    return spans


def drop_kept(cands: list[dict], spans: list[tuple[int, int]]) -> list[dict]:
    """Drop the candidates that overlap a kept term, except identifiers whose checksum passed."""
    if not spans:
        return cands
    return [c for c in cands if c["validated"] or not any(c["start"] < e and s < c["end"] for s, e in spans)]


# --------------------------------------------------------------------------- #
# Merge (after rizzo-pii's _merge)
# --------------------------------------------------------------------------- #
def _is_word(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def merge(cands: list[dict], text: str) -> list[dict]:
    """Non-overlapping spans: checksum-valid, then exact sources, then score, then length.

    Spans are trimmed of spaces, widened to whole words (a span that cuts a word in half would leave
    a readable rest, "[FULLNAME_1]abrando"), and touching spans of one label are joined.
    """
    order = sorted(
        cands,
        key=lambda e: (1 if e["validated"] else 0,
                       1 if (e["source"] in STRICT_SOURCES and e["label"] not in rz.SOFT_REGEX_LABELS) else 0,
                       e["score"], e["end"] - e["start"]),
        reverse=True,
    )
    kept = []
    for e in order:
        if any(k["start"] < e["end"] and e["start"] < k["end"] for k in kept):
            continue
        kept.append(dict(e))
    for e in kept:
        # Spaces, brackets and closing punctuation stay outside the placeholder ("<[EMAIL_1]>", "[FULLNAME_1].").
        while e["start"] < e["end"] and (text[e["start"]].isspace() or text[e["start"]] in "<([{\"'«"):
            e["start"] += 1
        while e["end"] > e["start"] and (text[e["end"] - 1].isspace() or text[e["end"] - 1] in ">)]}\"'».,;:"):
            e["end"] -= 1
    kept = [e for e in kept if e["end"] > e["start"]]
    for e in kept:
        while e["start"] > 0 and _is_word(text[e["start"] - 1]) and _is_word(text[e["start"]]):
            e["start"] -= 1
        while e["end"] < len(text) and _is_word(text[e["end"]]) and _is_word(text[e["end"] - 1]):
            e["end"] += 1
    kept.sort(key=lambda e: (e["start"], -(e["end"] - e["start"])))
    merged = []
    for e in kept:
        if merged and e["start"] < merged[-1]["end"]:
            merged[-1]["end"] = max(merged[-1]["end"], e["end"])
            continue
        if merged and e["start"] == merged[-1]["end"] and e["label"] == merged[-1]["label"]:
            merged[-1]["end"] = e["end"]
            continue
        merged.append(e)
    return merged


# --------------------------------------------------------------------------- #
# The project table
# --------------------------------------------------------------------------- #
def _key(word: str) -> str:
    """The word under which the project-wide pass files a pattern: its first run of letters, lowercased."""
    m = re.search(r"[^\W\d_]+", word)
    return m.group().lower() if m else ""


def _title(word: str) -> str:
    """A name word as it is written capitalized: "d'amico" to "D'Amico"."""
    return re.sub(r"[^\W\d_]+", lambda m: m.group()[0].upper() + m.group()[1:], word)


def lowercase_words(texts: list[str]) -> set[str]:
    """The words the texts write in lowercase away from an article, a title or a greeting: in this project
    they are ordinary words, whatever names they also are ("evidenziare in rosso"). Email addresses and web
    links are left out, where names are lowercase by convention."""
    out = set()
    for t in texts:
        t = URL_OR_EMAIL.sub(" ", t)
        cued = {m.end() for m in _CUE.finditer(t)}
        out.update(m.group().casefold() for m in LOWER_WORD.finditer(t) if m.start() not in cued)
    return out


class Table:
    """Placeholders of one project: stable numbering, every spelling of a value, persons linked by name.

    Stored as JSON: {"version", "counters": {label: n}, "entries": {placeholder: {"type", "variants",
    "first_file", "ambiguous"}}}; a person from a table's name columns also carries "given" and "surname"
    when the table splits them, and "directory" while they are known only from a directory (see
    `register_people`). Only the engine reads it; the deny rules keep Claude out of it.
    """

    def __init__(self, path: Path | None = None):
        self.path = path
        data = json.loads(path.read_text(encoding="utf-8")) if path and path.exists() else {}
        self.counters: dict = data.get("counters", {})
        self.entries: dict = data.get("entries", {})
        self.added: list[str] = []  # placeholders created in this run
        self._index = {}
        self._words = {}  # placeholder -> the words of every spelling of that person
        for ph, e in self.entries.items():
            for v in e["variants"]:
                self._index[(e["type"], norm_value(e["type"], v))] = ph
            if e["type"] == "FULLNAME":
                self._words[ph] = frozenset().union(*(person_tokens(v) for v in e["variants"]))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"version": 1, "counters": self.counters, "entries": self.entries}
        self.path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")

    def _new(self, label: str, value: str, source: str, ambiguous: bool = False, directory: bool = False) -> str:
        self.counters[label] = self.counters.get(label, 0) + 1
        ph = f"[{label}_{self.counters[label]}]"
        self.entries[ph] = {"type": label, "variants": [value], "first_file": source, "ambiguous": ambiguous}
        if directory:
            self.entries[ph]["directory"] = True
        self._index[(label, norm_value(label, value))] = ph
        if label == "FULLNAME":
            self._words[ph] = person_tokens(value)
        self.added.append(ph)
        return ph

    def _add_variant(self, ph: str, label: str, value: str) -> None:
        if value not in self.entries[ph]["variants"]:
            self.entries[ph]["variants"].append(value)
        self._index[(label, norm_value(label, value))] = ph
        if label == "FULLNAME":
            self._words[ph] = self._words.get(ph, frozenset()) | person_tokens(value)

    def person_words(self, ph: str) -> frozenset:
        return self._words.get(ph, frozenset())

    def assign(self, label: str, value: str, source: str = "", row: bool = False, directory: bool = False) -> str:
        """The placeholder for a value, created when the value is new.

        A person's name found in a text joins the known person whose name holds it or is held by it. A row
        of a table's name columns is a person of its own, since two rows are two people even when one name
        holds the other ("Anna Rossi", "Anna Maria Rossi"): it joins only the same spelling.
        """
        key = (label, norm_value(label, value))
        if key in self._index:
            return self._index[key]
        if label == "FULLNAME" and not row:
            toks = person_tokens(value)
            if toks:
                # An ambiguous entry (a lone surname shared by two people) never absorbs another name.
                matches = [ph for ph, e in self.entries.items()
                           if e["type"] == "FULLNAME" and not e.get("ambiguous")
                           and (toks <= self.person_words(ph) or self.person_words(ph) <= toks)]
                if len(matches) == 1:
                    self._add_variant(matches[0], label, value)
                    return matches[0]
                return self._new(label, value, source, ambiguous=len(matches) > 1)
        return self._new(label, value, source, directory=directory)

    def register_people(self, names: list[tuple]) -> None:
        """Register person names, the longest first, so that a lone surname finds its person.

        A name found in a text is (value, source). A person from a table's name columns is (value, source,
        info): info holds "given" and "surname" when the table splits them, and "directory" when the table
        lists more people than a document names (a staff census). A directory person enters the
        project-wide pass by full name only, until a name found in a text joins them: then every word of
        their name travels, as for anyone met in a text.
        """
        for n in sorted(names, key=lambda n: -len(person_tokens(n[0]))):
            value, source, info = n[0], n[1], (n[2] if len(n) > 2 else None)
            ph = self.assign("FULLNAME", value, source, row=info is not None,
                             directory=bool(info and info.get("directory")))
            e = self.entries[ph]
            if info is None:
                e.pop("directory", None)
            elif info.get("given") and info.get("surname") and "surname" not in e:
                e["given"], e["surname"] = info["given"], info["surname"]

    def display(self, ph: str) -> str:
        """The value a placeholder is restored to: for a person the fullest spelling, titles removed."""
        e = self.entries[ph]
        if e["type"] != "FULLNAME":
            return e["variants"][0]
        best = max(e["variants"], key=lambda v: (len(person_tokens(v)), -e["variants"].index(v)))
        return TITLES.sub("", best).strip()

    def known_name_patterns(self, ctx: Context, ordinary: set = frozenset()) -> dict:
        """Patterns for the project-wide pass, filed under a word each one needs (see `table_candidates`).

        Every person matches by full name, in any case and in either order ("Mario Rossi", "ROSSI MARIO"),
        and, when a table gave the given name and the surname apart, by surname and initial ("Rossi M.",
        "M. Rossi"). The words of a name travel alone only for people met in a text, never for a person
        known only from a directory, and within these limits:
          - never a word of two letters, a function word, a particle, a role or office word, a month or a
            weekday ("del", "Della", "ottobre");
          - capitalized as a name is written ("Gili osserva"), never in capitals alone, where headings and
            acronyms are;
          - in lowercase anywhere when a text wrote it in lowercase as the name ("ciao ste," and then "ste"
            alone on the signature line), or when it has three or four letters ("Gio" in the minutes, then
            "sentire gio" in a chat): the nicknames of chats and internal email;
          - otherwise in lowercase only after an article, a title or a greeting ("la sig.ra martina"), a common
            word of the shipped list (ctx.common) only after an article ("la serena"), and neither when the
            project's texts write the word in lowercase elsewhere (`ordinary`, see `lowercase_words`), so
            "evidenziare in rosso" keeps its colour;
          - a word that is also a municipality never after a place preposition: "fatto Usseglio" is the
            person, "Comune di Avigliana" stays a place.
        A word two known people share is masked all the same, under a placeholder of its own marked
        ambiguous (the pattern carries no placeholder, `assign` creates or finds it).
        """
        index, phrases_seen, words_seen = {}, set(), set()

        def add(key, pat, ph):
            index.setdefault(key, []).append((pat, ph))

        people = [ph for ph, e in self.entries.items() if e["type"] == "FULLNAME"]
        # How many known (not ambiguous) people carry each word: a shared word fits no single placeholder.
        carriers = {}
        for ph in people:
            if not self.entries[ph].get("ambiguous"):
                for w in self.person_words(ph):
                    carriers[w] = carriers.get(w, 0) + 1
        not_place = "".join(rf"(?<!\b{p} )" for p in PLACE_PREPS)
        for ph in people:
            e = self.entries[ph]
            phrases = []
            for v in e["variants"]:
                words = TITLES.sub("", v).split()
                if len(words) > 1:
                    phrases += [words, words[::-1]] if len(words) == 2 else [words]
            if e.get("given") and e.get("surname"):
                given, surname = e["given"].split(), e["surname"].split()
                phrases += [given + surname, surname + given]
                initial = e["given"].strip()[:1].upper()
                if initial.isalpha():
                    s = r"[ \t]+".join(re.escape(w) for w in surname)
                    add(_key(surname[0]), re.compile(r"(?<![\w.])(?i:" + s + r")[ \t]+" + re.escape(initial)
                                                     + r"\.(?=[\s,;:)]|$)"), ph)
                    add(_key(surname[0]), re.compile(r"(?<![\w.])" + re.escape(initial) + r"\.[ \t]?(?i:" + s
                                                     + r")(?!\w)"), ph)
            for words in phrases:
                k = " ".join(words).casefold()
                if k not in phrases_seen:
                    phrases_seen.add(k)
                    add(_key(words[0]), _phrase_pattern(" ".join(words), False), ph)
            if e.get("ambiguous") or e.get("directory") or all(lone_town(v, ctx) for v in e["variants"]):
                continue
            for w in self.person_words(ph):
                if (len(w) < 3 or w in words_seen or w in STOPWORDS or w in PARTICLES or w in NOT_NAME_WORDS
                        or w in NOT_NAMES or w in CALENDAR_WORDS):
                    continue
                words_seen.add(w)
                target = ph if carriers.get(w, 0) <= 1 else None
                # The capitalized form, and any mixed-case spelling the name is written with ("DeLuca"); a
                # particle that stands before the word in the name goes with it ("Del Rosso osserva").
                forms = {_title(w)} | {t for v in e["variants"] for t in WORD.findall(v)
                                       if t.casefold() == w and not t.isupper() and not t.islower()}
                alt = "|".join(re.escape(f) for f in sorted(forms))
                parts = {p.casefold() for v in e["variants"] for p, q in zip(v.split(), v.split()[1:])
                         if q.casefold() == w and p.casefold() in PARTICLES}
                lead = ("(?:(?i:" + "|".join(re.escape(p) for p in sorted(parts)) + r")[ \t]+)?") if parts else ""
                if w in ctx.comuni:
                    add(_key(w), re.compile(not_place + r"(?<!\w)" + lead + "(?:" + alt + r")(?!\w)"), target)
                    continue
                add(_key(w), re.compile(r"(?<!\w)" + lead + "(?:" + alt + r")(?!\w)"), target)
                written_lower = any(t.islower() and t.casefold() == w for v in e["variants"] for t in WORD.findall(v))
                if w in ctx.common:
                    if w not in ordinary:
                        add(_key(w), re.compile(ARTICLE_CUE + r"(?P<v>" + re.escape(w) + r")(?!\w)"), target)
                elif written_lower or len(w) <= NICKNAME_LETTERS:
                    add(_key(w), re.compile(r"(?<!\w)" + re.escape(w) + r"(?!\w)"), target)
                elif w not in ordinary:
                    add(_key(w), re.compile(LOWER_CUE + r"(?P<v>" + re.escape(w) + r")(?!\w)"), target)
        return index


def table_candidates(text: str, patterns: dict) -> list[dict]:
    """The known names in a text. Only the patterns filed under a word the text holds run, so a census of
    thousands of people costs a few dictionary lookups per cell."""
    out = []
    for w in set(re.findall(r"[^\W\d_]+", text.lower())):
        for pat, ph in patterns.get(w, ()):
            for m in pat.finditer(text):
                s, e = m.span("v") if "v" in pat.groupindex else m.span()
                c = _span("FULLNAME", s, e, score=2.2, source="table")
                if ph:
                    c["ph"] = ph
                out.append(c)
    return out


# --------------------------------------------------------------------------- #
# Masking a project
# --------------------------------------------------------------------------- #
@dataclass
class Masked:
    """One masked text: the output, the spans with their placeholders, counts by type."""
    text: str
    spans: list[dict]
    counts: dict
    flags: list[str]


def _fits_shape(c: dict, t: str) -> bool:
    """Whether a detection of the model has the shape of its type (SHAPES, STREET_WORD); the regex net's own
    detections have it by construction."""
    if c["source"] != "model":
        return True
    value = t[c["start"]:c["end"]]
    shape = SHAPES.get(c["label"])
    if shape:
        return bool(shape.match(re.sub(r"[\s.\-]", "", value)))  # "PR" labelled as a codice fiscale
    if c["label"] == "STREET":
        return bool(STREET_WORD.match(value) or HOUSE_NUMBER_AFTER.match(t[c["end"]:c["end"] + 12]))
    return True


def _near_street(c: dict, t: str, streets: list[dict]) -> bool:
    """A postcode or house number inside a street, or after one within NEAR_STREET characters of the same
    line and clause ("via Roma 12, 10094 Giaveno", not "via Roma 12; CDC 10122")."""
    for s in streets:
        if s["start"] <= c["start"] < s["end"]:
            return True
        gap = t[s["end"]:c["start"]]
        if 0 <= c["start"] - s["end"] <= NEAR_STREET and not re.search(r"[\n;|]", gap):
            return True
    return False


def first_pass(texts: list[str], detector, ctx: Context, org: list[bool] | None = None) -> list[list[dict]]:
    """Candidates per text, before the project table: detector (tags in ctx.excluded and detections without
    their shape dropped), rules, always. In a text marked `org`, a cell that names an organisation unit, the
    model's people are set aside: there a person's name is a hospital, a ward or a town named after someone."""
    found = detector.detect_many(texts)
    org = org or [False] * len(texts)
    out = []
    for t, cands, in_org in zip(texts, found, org):
        kept = []
        for c in cands:
            if c["label"] in ctx.excluded or not _fits_shape(c, t):
                continue
            if in_org and c["label"] == "FULLNAME" and c["source"] == "model":
                continue
            if c["label"] == "EMAIL":
                c = dict(c, score=3.0)  # a whole address outranks a known name inside it
            if c["label"] == "FULLNAME" and only_role_or_office(t[c["start"]:c["end"]]):
                continue  # "Ufficio Formazione" tagged as a person
            if c["label"] == "FULLNAME" and c["source"] == "model" and re.match(r"(?i)val\s", t[c["start"]:c["end"]]):
                continue  # "VAL CHISONE": a valley
            if (c["label"] == "FULLNAME" and c["source"] == "model" and t[c["start"]:c["end"]].strip().isupper()
                    and lone_town(t[c["start"]:c["end"]], ctx)):
                continue  # "CURE DOMICILIARI ADI PINEROLO": a town in a service name or a heading
            if c["label"] == "TELEPHONENUM" and AFTER_PROT.search(t[max(0, c["start"] - 20):c["start"]]):
                continue  # "N. Prot. 0012345": a protocol number
            kept.append(c)
        streets = [c for c in kept if c["label"] == "STREET"]
        kept = [c for c in kept if c["label"] not in ("ZIPCODE", "BUILDINGNUM") or c["source"] != "model"
                or _near_street(c, t, streets)]
        kept += rule_candidates(t, ctx) + always_candidates(t, ctx)
        out.append(drop_kept(kept, keep_spans(t, ctx)))
    return out


def mask_texts(texts: list[str], detector, table: Table, ctx: Context, sources: list[str] | None = None,
               people: list[tuple] = (), org: list[bool] | None = None) -> list[Masked]:
    """Mask texts of one project with one table; `people` are the persons of tables' name columns, as
    `Table.register_people` takes them; `org` marks the cells of organisation-unit columns (see `first_pass`)."""
    sources = sources or [""] * len(texts)
    cands = first_pass(texts, detector, ctx, org)
    names = list(people)
    for t, c, src in zip(texts, cands, sources):
        for e in join_name_words(merge(c, t), t, ctx):
            v = t[e["start"]:e["end"]]
            # A town the model alone took for a person is masked where it stands, and makes no person whose
            # words would travel or who would join a directory person bearing that town as a surname.
            if e["label"] == "FULLNAME" and looks_like_name(v) and not (e["source"] == "model" and lone_town(v, ctx)):
                names.append((v, src))
    names = [n for n in names if looks_like_name(n[0])]
    table.register_people(names)
    patterns = table.known_name_patterns(ctx, lowercase_words(texts))
    results = []
    for t, c, src in zip(texts, cands, sources):
        tc = drop_kept(table_candidates(t, patterns), keep_spans(t, ctx))
        spans = join_name_words(merge(c + tc, t), t, ctx)
        out, pos, counts, flags = [], 0, {}, []
        for e in spans:
            v = t[e["start"]:e["end"]]
            alone = e["label"] == "FULLNAME" and e["source"] == "model" and lone_town(v, ctx)
            ph = e.get("ph") or table.assign(e["label"], v, src, row=alone)
            e["ph"] = ph
            label = table.entries[ph]["type"]
            counts[label] = counts.get(label, 0) + 1
            if table.entries[ph].get("ambiguous"):
                flags.append(f"{ph} is a name shared by two known people")
            out.append(t[pos:e["start"]] + ph)
            pos = e["end"]
        out.append(t[pos:])
        results.append(Masked("".join(out), spans, counts, sorted(set(flags))))
    return results


def mask_names(stems: list[str], detector, table: Table, ctx: Context) -> list[str]:
    """Masked file names: a file called after a patient must not show the name to Claude.

    Separators become spaces for detection; placeholders appear without brackets ("Relazione_FULLNAME_1").
    """
    texts = [re.sub(r"[_\-.]+", " ", s) for s in stems]
    cands = first_pass(texts, detector, ctx)
    patterns = table.known_name_patterns(ctx)
    out = []
    for t, c in zip(texts, cands):
        spans = merge(c + drop_kept(table_candidates(t, patterns), keep_spans(t, ctx)), t)
        pieces, pos = [], 0
        for e in spans:
            ph = e.get("ph") or table.assign(e["label"], t[e["start"]:e["end"]], "file name")
            pieces.append(t[pos:e["start"]] + ph.strip("[]"))
            pos = e["end"]
        pieces.append(t[pos:])
        out.append(re.sub(r"[^\w\-]+", "_", "".join(pieces)).strip("_") or "documento")
    return out


def possible_misses(text: str, spans: list[dict], ctx: Context) -> list[dict]:
    """Words a reviewer should look at: capitalized words inside a sentence and long numbers left in
    clear and absent from the lists, and lowercase words after a title or a greeting."""
    masked = [(e["start"], e["end"]) for e in spans]
    kept = keep_spans(text, ctx)
    known = {k.casefold() for k in ctx.keep} | ctx.common

    def covered(s, e):
        return any(a < e and s < b for a, b in masked + kept)

    out = []
    for m in re.finditer(r"(?<![\w.])[A-ZÀ-Ý][a-zà-ÿ']{2,}|\b[A-ZÀ-Ý]{3,}\b", text):
        s, e, w = m.start(), m.end(), m.group()
        if covered(s, e) or w.casefold() in known or w.casefold() in ctx.comuni:
            continue
        line_start = text.rfind("\n", 0, s) + 1
        line_end = text.find("\n", e)
        line = text[line_start:line_end if line_end >= 0 else len(text)]
        letters = [c for c in line if c.isalpha()]
        if w.isupper() and letters and sum(c.isupper() for c in letters) / len(letters) > 0.6:
            continue  # a heading in capitals, not a name in a sentence
        if not w.isupper() and re.search(r"(?:^|[.!?:;\n|]\s*)$", text[line_start:s]):
            continue  # first word of a sentence, a line or a cell
        out.append({"start": s, "end": e, "why": "capitalized"})
    for m in re.finditer(r"(?<![\w\[])\d[\d .\-/]{5,}\d(?![\w\]])", text):
        if not covered(m.start(), m.end()) and len(re.sub(r"\D", "", m.group())) >= 6:
            out.append({"start": m.start(), "end": m.end(), "why": "long number"})
    for m in NAME_CUES.finditer(text):
        s, e = m.start("w"), m.end("w")
        if not covered(s, e) and m.group("w").casefold() not in known:
            out.append({"start": s, "end": e, "why": "after a title"})
    return sorted(out, key=lambda x: x["start"])


def restore_text(text: str, table: Table) -> tuple[str, int, list[str]]:
    """Placeholders back to real values; returns the text, the count, and placeholders the table lacks."""
    unknown, count = [], 0

    def sub(m):
        nonlocal count
        ph = m.group(0)
        if ph in table.entries:
            count += 1
            return table.display(ph)
        unknown.append(ph)
        return ph

    out = re.sub(r"\[[A-Z_]+_\d+\]", sub, text)
    return out, count, sorted(set(unknown))
