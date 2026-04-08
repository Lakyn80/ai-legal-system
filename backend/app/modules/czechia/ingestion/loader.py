"""
Streaming JSON loader for rag_legal_dataset.json.

Streams individual sections (law_fragments, definitions, links, terms, metadata)
one record at a time using brace-depth tracking.  The full file (~3.7 GB) is
never loaded into memory — only the current JSON object is held in a buffer.

Section order in rag_legal_dataset.json (as written by build_rag_dataset.py):
    1. law_fragments
    2. definitions
    3. links
    4. terms
    5. metadata

When reading multiple sections, open separate iterators — each call to
stream_*() opens an independent file handle and scans from the beginning.
For reading sections that appear later in the file this is slightly slower
but keeps the API simple and avoids stateful seek logic.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Generator
from pathlib import Path


def _stream_section(filepath: Path, section_key: str) -> Generator[dict, None, None]:
    """
    Stream all items from a named top-level JSON array in the dataset file.

    Advances through the file line-by-line until it finds the section header
    (e.g. '"law_fragments": ['), then yields one parsed dict per array item.
    Uses brace-depth counting to detect complete JSON objects — O(1) memory
    per item regardless of file size.
    """
    target = f'"{section_key}"'

    with filepath.open(encoding="utf-8") as f:
        # ── advance to the section ────────────────────────────────────────
        found = False
        for line in f:
            if target in line and "[" in line:
                found = True
                break

        if not found:
            print(
                f"[loader] WARNING: section '{section_key}' not found in {filepath.name}",
                file=sys.stderr,
            )
            return

        # ── parse items by brace-depth ────────────────────────────────────
        buf: list[str] = []
        depth = 0

        for line in f:
            stripped = line.strip()

            # end of this section's array
            if stripped in ("]", "],", "];"):
                break

            # skip bare commas and blank lines between items
            if not stripped or stripped == ",":
                continue

            for ch in stripped:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1

            buf.append(line)

            if depth == 0 and buf:
                text = "".join(buf).strip().rstrip(",")
                buf = []
                if text:
                    try:
                        yield json.loads(text)
                    except json.JSONDecodeError as exc:
                        print(
                            f"[loader] JSON parse error in section '{section_key}': {exc}",
                            file=sys.stderr,
                        )


def stream_law_fragments(filepath: Path) -> Generator[dict, None, None]:
    """Stream law_fragment dicts from the dataset file."""
    return _stream_section(filepath, "law_fragments")


def stream_definitions(filepath: Path) -> Generator[dict, None, None]:
    """Stream definition dicts from the dataset file."""
    return _stream_section(filepath, "definitions")


def stream_links(filepath: Path) -> Generator[dict, None, None]:
    """Stream law_link dicts from the dataset file."""
    return _stream_section(filepath, "links")


def stream_terms(filepath: Path) -> Generator[dict, None, None]:
    """Stream term dicts from the dataset file."""
    return _stream_section(filepath, "terms")


def stream_metadata(filepath: Path) -> Generator[dict, None, None]:
    """Stream metadata dicts from the dataset file."""
    return _stream_section(filepath, "metadata")
