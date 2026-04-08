"""
Loader for locally downloaded e-Sbírka JSON packages.

Supports two sources:
- Plain JSON file:  load_local_sb_json(path)
- ZIP archive:      load_local_sb_zip(zip_path)   (no extraction to disk)

Both yield dicts with keys ``id``, ``law_iri``, ``text`` — the exact shape
expected by ``build_chunks()`` in chunk_builder.py.  No existing pipeline
files are touched.  Relation hooks are left for the phase-2 graph pass.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from typing import Iterator

# Fragment types that carry actual legal content.
# Deliberately excludes Prefix_*, Prefix, Postfix (document header/footer
# boilerplate: law number, type label, date) and Virtual_* structural nodes.
_TEXT_FRAGMENT_TYPES: frozenset[str] = frozenset({
    "Cast", "Hlava", "Dil", "Oddil", "Pododdil",
    "Nadpis_nad", "Nadpis_pod",
    "Paragraf",
    "Odstavec_Dc",
    "Pismeno_Lb",
    "Bod_Dd",
    "Odrazka_Rb",
    "Pokracovani_Text",
    "Block_Prechodne_Ustanoveni_Nov",
    "Block_Zrusovaci_Ustanoveni",
    "Block_Ucinnostni_Ustanoveni",
})

_RE_HTML = re.compile(r"<[^>]+>")
_RE_WS = re.compile(r"\s+")
_RE_PARAGRAPH = re.compile(r"§\s*(\d+[a-z]?)", re.IGNORECASE)


def _clean(xhtml: str) -> str:
    """Strip HTML tags and normalise whitespace."""
    text = _RE_HTML.sub(" ", xhtml)
    return _RE_WS.sub(" ", text).strip()


def _law_iri_from_predpis_cislo(predpis_cislo: str) -> str:
    """
    Convert 'predpisCislo' value to a stable local IRI.

    Examples:
        '40/2009 Sb.'  ->  'local:sb/2009/40'
        '89/2012 Sb.'  ->  'local:sb/2012/89'
    """
    m = re.match(r"(\d+)/(\d{4})", predpis_cislo.strip())
    if not m:
        safe = re.sub(r"[^a-zA-Z0-9_/]", "_", predpis_cislo.strip())
        return f"local:sb/{safe}"
    number, year = m.group(1), m.group(2)
    return f"local:sb/{year}/{number}"


def _iter_fragments(data: dict) -> Iterator[dict]:
    """
    Core fragment iterator shared by both load functions.

    Yields dicts with keys ``id``, ``law_iri``, ``text``.
    """
    meta = data.get("metadata") or {}
    predpis_cislo: str = meta.get("predpisCislo") or ""
    law_iri = _law_iri_from_predpis_cislo(predpis_cislo)

    current_paragraph: str | None = None

    for frag in data.get("fragmenty") or []:
        typ: str = frag.get("typ") or ""
        if typ not in _TEXT_FRAGMENT_TYPES:
            continue

        xhtml: str = frag.get("xhtml") or ""
        if not xhtml:
            continue

        text = _clean(xhtml)
        if not text:
            continue

        if typ == "Paragraf":
            match = _RE_PARAGRAPH.search(text)
            current_paragraph = match.group(1) if match else None
        else:
            match = _RE_PARAGRAPH.search(text)
            if match:
                current_paragraph = match.group(1)

        fragment_id = frag.get("fragmentId")
        yield {
            "id":      f"{law_iri}/{fragment_id}",
            "law_iri": law_iri,
            "text":    text,
            "paragraph": current_paragraph,
        }


def load_local_sb_json(path: str | Path) -> Iterator[dict]:
    """
    Read a locally downloaded e-Sbírka JSON file and yield fragment dicts.

    Each yielded dict has exactly:
        {
            "id":      "local:sb/{year}/{number}/{fragmentId}",
            "law_iri": "local:sb/{year}/{number}",
            "text":    "<cleaned text of the fragment>",
        }
    """
    path = Path(path)
    with path.open(encoding="utf-8", errors="replace") as f:
        data = json.load(f)
    yield from _iter_fragments(data)


def load_local_sb_zip(zip_path: str | Path) -> Iterator[dict]:
    """
    Read an e-Sbírka ZIP archive and yield fragment dicts without extracting
    the archive to disk.

    Finds the first entry whose name ends with ``IZ.json`` inside the ZIP.
    Raises ``FileNotFoundError`` if no such entry exists.

    Each yielded dict has the same shape as ``load_local_sb_json()``.
    """
    zip_path = Path(zip_path)
    with zipfile.ZipFile(zip_path, "r") as zf:
        # Find the IZ.json entry (may be nested inside a subfolder)
        json_entry = next(
            (e for e in zf.infolist() if e.filename.endswith("IZ.json")),
            None,
        )
        if json_entry is None:
            raise FileNotFoundError(
                f"No *IZ.json entry found inside {zip_path.name}"
            )
        with zf.open(json_entry) as raw:
            data = json.load(io.TextIOWrapper(raw, encoding="utf-8", errors="replace"))

    yield from _iter_fragments(data)
