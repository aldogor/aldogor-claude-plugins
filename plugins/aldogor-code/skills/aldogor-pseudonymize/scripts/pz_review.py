"""The review page: originals and masked copies side by side, for the user to read in a browser.

It is written into the private folder, which the deny rules keep from Claude, because it shows the
original text. Each detection is marked with its placeholder and its source (model, regex, rule,
table, always); possible misses are marked apart. The placeholders a run used are listed by how often
they occur, with every spelling linked to them, so that a word masked by mistake ("del", forty times)
and a wrong link between two people show at once. Each document ends with a fixed sample of its masked
values, on which the user counts the wrong ones for the gate.
"""

import html
import json
from pathlib import Path

COLORS = {"FULLNAME": "#f4c7c3", "CF": "#c9daf8", "TS": "#c9daf8", "IBAN": "#c9daf8", "BIRTHDATE": "#d9ead3",
          "TELEPHONENUM": "#fce5cd", "EMAIL": "#fce5cd", "STREET": "#ead1dc", "BUILDINGNUM": "#ead1dc",
          "ZIPCODE": "#ead1dc", "DOCID": "#d0e0e3"}
MISS = "#fff2a8"


def _marked(text: str, spans: list[dict], misses: list[dict]) -> str:
    """The original with detections and possible misses highlighted."""
    marks = [(s["start"], s["end"], "span", s) for s in spans] + [(m["start"], m["end"], "miss", m) for m in misses]
    marks.sort(key=lambda m: (m[0], m[2] != "span"))
    out, pos = [], 0
    for start, end, kind, m in marks:
        if start < pos:
            continue
        out.append(html.escape(text[pos:start]))
        frag = html.escape(text[start:end])
        if kind == "span":
            color = COLORS.get(m["label"], "#e0e0e0")
            out.append(f'<mark style="background:{color}" title="{html.escape(m["ph"])} ({m["source"]})">{frag}</mark>')
        else:
            out.append(f'<mark style="background:{MISS};outline:1px dashed #b58900" title="possible miss: {m["why"]}">{frag}</mark>')
        pos = end
    out.append(html.escape(text[pos:]))
    return "".join(out)


def build(review_dir: Path, table, out_path: Path) -> int:
    """Write the review page from the per-file records of the last run; returns the number of files."""
    records = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(review_dir.glob("*.json")) if not p.name.startswith("_")]
    run = review_dir / "_run.json"
    run_data = json.loads(run.read_text(encoding="utf-8")) if run.exists() else {}
    added, frequency = set(run_data.get("added", [])), run_data.get("frequency", {})
    parts = [
        "<!doctype html><html lang='it'><head><meta charset='utf-8'><title>Revisione pseudonimizzazione</title>",
        "<style>body{font:14px/1.5 system-ui,sans-serif;margin:16px;color:#222;background:#fff}"
        "h2{margin-top:2em;border-bottom:1px solid #ccc}.cols{display:grid;grid-template-columns:1fr 1fr;gap:16px}"
        "pre{white-space:pre-wrap;background:#fafafa;border:1px solid #ddd;padding:8px}"
        "table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:2px 6px;vertical-align:top}"
        ".flag{color:#a61c00}</style></head><body>",
        "<h1>Revisione della pseudonimizzazione</h1>",
        "<p>Pagina locale: contiene i testi originali e non va condivisa. Controllare che ogni persona e ogni "
        "identificativo sia coperto, che i segnaposto colleghino le persone giuste, e le parole evidenziate in "
        "giallo (possibili omissioni). Le correzioni vanno in <code>pseudonymize-private/always.txt</code> "
        "(da mascherare sempre) e in <code>.pseudonymize/keep.txt</code> (da lasciare in chiaro); poi si "
        "rilancia <code>mask</code>.</p>",
    ]
    used = sorted((ph for ph in frequency if ph in table.entries), key=lambda ph: (-frequency[ph], ph))
    if used:
        parts.append("<h2>Segnaposto usati in questa esecuzione, dal più frequente</h2>"
                     "<p>In cima stanno le parole mascherate più spesso: una parola comune in cima (una preposizione, "
                     "un mese, un luogo) indica un errore.</p>"
                     "<table><tr><th>Segnaposto</th><th>Volte</th><th>Grafie collegate</th><th>Note</th></tr>")
        for ph in used:
            e = table.entries[ph]
            notes = []
            if ph in added:
                notes.append("nuovo")
            if e.get("ambiguous"):
                notes.append("<span class='flag'>nome condiviso da più persone note</span>")
            if e.get("directory"):
                notes.append("da un elenco: solo nome e cognome completi")
            parts.append(f"<tr><td>{html.escape(ph)}</td><td>{frequency[ph]}</td>"
                         f"<td>{html.escape(' | '.join(e['variants']))}</td><td>{'; '.join(notes)}</td></tr>")
        parts.append("</table>")
    for r in records:
        parts.append(f"<h2>{html.escape(r['original_name'])} &rarr; {html.escape(r['masked_name'])}</h2>")
        if r.get("note"):
            parts.append(f"<p class='flag'>{html.escape(r['note'])}</p>")
            continue
        for f in r.get("flags", []):
            parts.append(f"<p class='flag'>{html.escape(f)}</p>")
        if r["kind"] == "text":
            parts.append("<div class='cols'><div><h3>Originale</h3><pre>"
                         + _marked(r["original"], r["spans"], r["misses"])
                         + "</pre></div><div><h3>Copia mascherata</h3><pre>" + html.escape(r["masked"]) + "</pre></div></div>")
        else:
            parts.append("<table><tr><th>Foglio</th><th>Riga</th><th>Colonna</th><th>Originale</th><th>Mascherato</th></tr>")
            for sheet, i, j, orig, masked in r["cells"]:
                parts.append(f"<tr><td>{html.escape(sheet)}</td><td>{i + 1}</td><td>{j + 1}</td>"
                             f"<td>{html.escape(orig)}</td><td>{html.escape(masked)}</td></tr>")
            parts.append("</table>")
        sample = r.get("sample", [])
        if sample:
            parts.append(f"<h3>Campione per il conteggio: {len(sample)} mascherature a caso</h3>"
                         "<p>Contare quante non sono dati di una persona (una parola comune, un ufficio, un codice).</p><ol>")
            for orig, masked in sample:
                parts.append(f"<li>{html.escape(orig)} &rarr; {html.escape(masked)}</li>")
            parts.append("</ol>")
    parts.append("</body></html>")
    out_path.write_text("\n".join(parts), encoding="utf-8")
    return len(records)
