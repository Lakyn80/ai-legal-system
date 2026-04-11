from __future__ import annotations

import re

from app.modules.common.querying.schemas import QueryContext
from app.modules.common.qdrant.schemas import HybridSearchResponse, SearchResultItem

# ---------------------------------------------------------------------------
# Structural-chunk detection
# ---------------------------------------------------------------------------
# Same family of patterns as the Czech reranker — used here to filter out
# headings and index lines before sending to the LLM, so the model works
# with substantive text only.

_INDEX_LINE_RE = re.compile(
    r"^\d{1,3}\.\s+(?:z[aá]kon|na[rř][íi]zen[íi]|vyhl[áa][šs]ka|sd[eě]len[íi])",
    re.IGNORECASE | re.UNICODE,
)
_SECTION_HEADING_RE = re.compile(
    r"^(?:část|hlava|díl|oddíl|pododdíl|kapitola)\b",
    re.IGNORECASE | re.UNICODE,
)


def is_substantive(text: str) -> bool:
    """
    Return True if the chunk contains actual legal text worth sending to the LLM.

    Rejected:
    - empty / very short (< 30 chars)
    - numbered derogation index lines  ("1. zákon č. 65/1965 Sb., ...")
    - section / chapter headings       ("ČÁST PRVNÍ", "HLAVA II")
    - anything without a verb or digit (pure heading words)

    Note: 30-char minimum (reduced from 55) keeps short but substantive clause
    sub-items like "a) ruší-li se zaměstnavatel nebo jeho část," (43 chars)
    while still rejecting bare headings like "§ 52" (4 chars).
    """
    value = (text or "").strip()
    if len(value) < 30:
        return False
    if _INDEX_LINE_RE.match(value):
        return False
    if _SECTION_HEADING_RE.match(value):
        return False
    # Must contain at least a digit (§ number, year, amount) or a verb hint.
    # Czech legal clause sub-items often use conditional -li forms (ruší-li,
    # přemísťuje-li, stane-li) which are definitively substantive content.
    if not re.search(r"\d", value) and not re.search(
        r"\b(?:je|jsou|má|může|musí|lze|byl|byla|bylo|byli|stanoví|upravuje|"
        r"určuje|zakazuje|ukládá|přísluší|vzniká|zaniká|trvá|skončí)\b"
        r"|\w+-li\b",  # Czech conditional -li suffix (ruší-li, stane-li, ...)
        value,
        re.IGNORECASE | re.UNICODE,
    ):
        return False
    return True


def pick_substantive_chunks(
    results: list[SearchResultItem],
    max_chunks: int = 3,
    max_chars_per_chunk: int = 600,
) -> list[SearchResultItem]:
    """
    Return up to `max_chunks` substantive results, text truncated to `max_chars_per_chunk`.
    Falls back to the first non-empty result if nothing passes the substantive filter.
    """
    substantive = [r for r in results if is_substantive(r.text or "")][:max_chunks]
    if not substantive:
        # graceful fallback: take first non-empty chunk even if structural
        substantive = [r for r in results if (r.text or "").strip()][:1]
    # shallow copy with truncated text so originals are not mutated
    out: list[SearchResultItem] = []
    for r in substantive:
        text = (r.text or "").strip()
        if len(text) > max_chars_per_chunk:
            text = text[:max_chars_per_chunk].rstrip() + " …"
        # pydantic model — use model_copy
        out.append(r.model_copy(update={"text": text}))
    return out


# ---------------------------------------------------------------------------
# System prompt — strict grounding rules
# ---------------------------------------------------------------------------

SEARCH_EXPLANATION_SYSTEM_PROMPT = """
Jsi právní analytik pro české právo. Tvojí jedinou funkcí je vysvětlit dotaz
na základě PŘILOŽENÝCH zdrojů.

ZÁVAZNÁ PRAVIDLA:
1. Používej VÝHRADNĚ informace, které jsou doslova obsaženy v přiložených zdrojích.
2. Pokud zdroje otázku nepokrývají nebo jsou příliš obecné, napiš to explicitně
   (např. „Přiložené úryvky toto konkrétně neupravují.").
3. NEVYMÝŠLEJ právní závěry, paragrafy ani podmínky, které nejsou v textu zdrojů.
4. Každé klíčové tvrzení v explanation musí být doložitelné přesným slovním spojením
   z jednoho ze zdrojů.
5. Pokud zdroj obsahuje relevantní text, NEVYNECHÁVEJ ho — parafrázuj jej přesně.
6. Neuváděj obecné právní poučky, pokud nejsou přímo v přiložených textech.
7. Odpovídej česky, stručně a fakticky.
""".strip()


# ---------------------------------------------------------------------------
# User prompt builder
# ---------------------------------------------------------------------------

def build_search_explanation_prompt(
    query_context: QueryContext,
    retrieval: HybridSearchResponse,
) -> str:
    """
    Build a grounding-focused user prompt.

    - Filters to top 3 substantive chunks (skips headings, index lines, etc.)
    - Formats sources as readable labeled blocks, not raw JSON
    - Adds explicit instruction to derive answer only from numbered sources
    """
    chunks = pick_substantive_chunks(retrieval.results, max_chunks=5)

    lines: list[str] = []
    lines.append(f"DOTAZ: {query_context.raw_query}")
    lines.append(f"JURISDIKCE: {query_context.jurisdiction.value}  |  DOMÉNA: {query_context.domain.value if query_context.domain else 'law'}")
    lines.append("")

    if chunks:
        lines.append(f"ZDROJE ({len(chunks)}):")
        for i, chunk in enumerate(chunks, 1):
            lines.append(f"[{i}] {chunk.filename}  (score: {chunk.score:.3f})")
            lines.append(f'    "{chunk.text}"')
            lines.append("")
    else:
        lines.append("ZDROJE: Žádné relevantní úryvky nebyly nalezeny.")
        lines.append("")

    lines.append("INSTRUKCE:")
    lines.append("Na základě POUZE výše uvedených zdrojů [1]–[" + str(len(chunks)) + "] odpověz na dotaz.")
    lines.append("• summary: 1–2 věty shrnutí přesně podle zdrojů.")
    lines.append("• explanation: podrobnější vysvětlení citující konkrétní text ze zdrojů.")
    lines.append("• key_points: seznam klíčových bodů, každý doložen zdrojem.")
    lines.append("Pokud zdroje nestačí k odpovědi, napiš to explicitně.")

    return "\n".join(lines)
