"""OpenLex, a remote MCP server for claude.ai: the commands of scripts/legislation.py as connector tools.

claude.ai runs connectors from Anthropic's cloud, and its code sandbox cannot reach Normattiva, so Italian law as in
force on a date reaches a claude.ai chat only through a server like this one. Each tool builds the command line of
one legislation.py command and returns exactly what the command prints (heading, the dates of the version shown,
the link to cite, the text), so the date logic and the sources are the script's own, tested in
scripts/test_legislation.py.

Deployment: Vercel serves `app` below as a Python function (vercel.json routes every path here). The endpoint is
https://<host>/<secret>/mcp, where <secret> is the environment variable LEGISLATION_MCP_SECRET, a long random string
set in the Vercel project and never written in this repository. The server reads only public law, and the secret
path keeps strangers from spending its quota. Without the variable the endpoint is /mcp, for local tests only.

Local run: python -m uvicorn api.index:app --port 8000 (from the skill folder, with the packages of
requirements.txt installed).
"""

from __future__ import annotations

import contextlib
import io
import os
import pathlib
import sys
import threading
import urllib.parse

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import Icon

# The script lives in ../scripts; importing it reuses its parser, commands and formatting unchanged.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import legislation  # noqa: E402

SECRET = os.environ.get("LEGISLATION_MCP_SECRET", "").strip("/")
PATH = f"/{SECRET}/mcp" if SECRET else "/mcp"

INSTRUCTIONS = (
    "Italian state law (Normattiva), EU law (EUR-Lex) and Piedmont regional law (Arianna, BURP), read at the official "
    "sources. Dates are YYYY-MM-DD. Every text answer opens with the same lines (Fonte/Source, Atto/Act, "
    "Articolo/Article, Versione/Version with the date asked, Link da citare/Link to cite) and every search answers "
    "with one table (act, date, identifier, link). Cite the link given, and say which date of vigenza the text is "
    "for. A source that fails is reported as failed, never as empty."
)

# A section sign on a dark square, inline, so the server needs no file of its own for its icon.
ICON = ("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA2NCA2NCI+"
        "PHJlY3Qgd2lkdGg9IjY0IiBoZWlnaHQ9IjY0IiByeD0iMTIiIGZpbGw9IiMxZjNhNWYiLz48dGV4dCB4PSIzMiIgeT0iNDYiIGZvbnQtc2l6"
        "ZT0iNDAiIGZvbnQtZmFtaWx5PSJHZW9yZ2lhLHNlcmlmIiBmaWxsPSIjZmZmIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj7CpzwvdGV4dD48L3N2Zz4=")

server = MCPServer(name="openlex", title="OpenLex", instructions=INSTRUCTIONS, version="1.1.0",
                   icons=[Icon(src=ICON, mime_type="image/svg+xml", sizes=["any"])])

# legislation.main prints to stdout and stderr; redirecting them is process-wide, so calls run one at a time.
_lock = threading.Lock()


def run(command: str, options: dict, positional: list[str] | None = None) -> str:
    """Run one legislation.py command and return its printed output, errors included.

    options maps a flag name without dashes (underscores become dashes) to a value: None and False are left out,
    True becomes a bare flag, anything else becomes "--flag value".
    """
    argv = [command, *(positional or [])]
    for name, value in options.items():
        if value is None or value is False:
            continue
        flag = "--" + name.replace("_", "-")
        argv += [flag] if value is True else [flag, str(value)]
    out, err = io.StringIO(), io.StringIO()
    with _lock, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = legislation.main(argv)
        except SystemExit as stop:  # argparse rejects an argument with SystemExit(2)
            code = stop.code if isinstance(stop.code, int) else 2
    text = out.getvalue().strip()
    if code:
        text = (text + "\n\n" if text else "") + f"Failed (exit {code}): {err.getvalue().strip() or 'no message'}"
    return text or "No output."


@server.tool()
def it_search(type: str | None = None, year: int | None = None, number: str | None = None,
              title: str | None = None, text: str | None = None, limit: int = 10) -> str:
    """Search Italian state acts on Normattiva. type is L, DLGS, DL, DPR, DPCM, RD, DM, COST or Normattiva's label;
    title and text are words to find. Returns each act with its codice redazionale and Gazzetta Ufficiale date."""
    return run("it-search", {"type": type, "year": year, "number": number, "title": title, "text": text,
                             "limit": limit})


@server.tool()
def it_article(article: str, type: str | None = None, year: int | None = None, number: str | None = None,
               date: str | None = None, code: str | None = None, gu_date: str | None = None, group: int = 0) -> str:
    """One article of an Italian state act as in force on a date (default today), from Normattiva. article is
    e.g. 13, 2-bis, 2-septies. Name the act by type, year and number, or by code and gu_date from it_search when
    those are ambiguous; group is the idGruppo some structured codes need."""
    return run("it-article", {"type": type, "year": year, "number": number, "code": code, "gu_date": gu_date,
                              "article": article, "date": date, "group": group or None})


@server.tool()
def eu_lookup(ref: str, lang: str = "ITA") -> str:
    """Identify an EU act from a CELEX number, an ELI or a citation such as 'Regolamento (UE) 2016/679': title,
    dates, whether in force, consolidated versions."""
    return run("eu-lookup", {"lang": lang}, [ref])


@server.tool()
def eu_text(ref: str, article: str | None = None, date: str | None = None, original: bool = False,
            toc: bool = False, lang: str = "ITA") -> str:
    """Text of an EU act, consolidated as on a date (default today), or one article of it; original gives the act
    as published, toc lists the articles only."""
    return run("eu-text", {"article": article, "date": date, "original": original, "toc": toc, "lang": lang}, [ref])


@server.tool()
def eu_transpositions(ref: str, country: str = "ITA") -> str:
    """National measures transposing an EU directive, for a country (three-letter code, default ITA)."""
    return run("eu-transpositions", {"country": country}, [ref])


@server.tool()
def eu_search(words: str, type: str | None = None, lang: str = "ITA", date_from: str | None = None,
              date_to: str | None = None, limit: int = 15) -> str:
    """EU acts whose title contains all the words; type is REG, DIR or DEC."""
    return run("eu-search", {"type": type, "lang": lang, "date_from": date_from, "date_to": date_to,
                             "limit": limit}, [words])


@server.tool()
def pie_law(year: int, number: int, regulation: bool = False, date: str | None = None, article: str | None = None,
            toc: bool = False, versions: bool = False) -> str:
    """A Piedmont regional law (or regolamento, with regulation) as in force on a date, from Arianna; article is
    e.g. 3 or 3bis, toc lists the articles, versions lists every version with its validity."""
    return run("pie-law", {"year": year, "number": number, "regulation": regulation, "date": date,
                           "article": article, "toc": toc, "versions": versions})


@server.tool()
def pie_search(words: str, within: str = "title", date: str | None = None) -> str:
    """Search Piedmont regional laws on Arianna, in the title or the text (within), optionally in force on a date."""
    return run("pie-search", {"in": within, "date": date}, [words])


@server.tool()
def bur_search(words: str, start: int = 0, limit: int = 10) -> str:
    """Search the Bollettino Ufficiale della Regione Piemonte (DGR, DD, DPGR and the rest) by free text."""
    return run("bur-search", {"start": start, "limit": limit}, [words])


@server.tool()
def smoke() -> str:
    """Live check of every source: one known request to each, OK or the error. Use it when a tool fails."""
    return run("smoke", {})


# Stateless JSON responses: each POST is answered on its own, which suits a function that may start cold.
# host="0.0.0.0" leaves out the DNS-rebinding protection meant for servers bound to localhost.
mcp_app = server.streamable_http_app(
    streamable_http_path=PATH,
    stateless_http=True,
    json_response=True,
    host="0.0.0.0",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

# Vercel's rewrite (vercel.json) hands every request to this function with the path /api/index and the path that
# was called in the query parameter vercel_path; restoring it lets the MCP app match /<secret>/mcp. Run elsewhere
# (uvicorn, tests), requests arrive with their own path and no such parameter, and pass through unchanged.
ORIGINAL_PATH = "vercel_path"


async def app(scope, receive, send):
    if scope["type"] == "http":
        query = urllib.parse.parse_qs(scope.get("query_string", b"").decode())
        if ORIGINAL_PATH in query:
            path = "/" + query[ORIGINAL_PATH][0].lstrip("/")
            rest = {k: v for k, v in query.items() if k != ORIGINAL_PATH}
            scope = {**scope, "path": path, "raw_path": path.encode(),
                     "query_string": urllib.parse.urlencode(rest, doseq=True).encode()}
    await mcp_app(scope, receive, send)
