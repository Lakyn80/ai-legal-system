"""Stress tests for Czech law retrieval and answer grounding."""
import json
import sys
import urllib.request
import urllib.error
import re

BASE = "http://localhost:8000/api"

TESTS = [
    # (query, expected_doc_fragment, category)
    # -- exact lookup (law + paragraph) --
    ("§ 52 zákoník práce", "262/2006", "exact"),
    ("§ 55 zákoník práce", "262/2006", "exact"),
    ("§ 56 zákoník práce", "262/2006", "exact"),
    ("zákon 262/2006 § 52", "262/2006", "exact"),
    # -- labor topic --
    ("výpověď zákoník práce", "262/2006", "labor"),
    ("odstupné zákoník práce podmínky", "262/2006", "labor"),
    ("dovolená zákoník práce délka", "262/2006", "labor"),
    ("pracovní smlouva zákoník práce náležitosti", "262/2006", "labor"),
    ("zkušební doba délka", "262/2006", "labor"),
    # -- labor natural language --
    ("mám nárok na odstupné při nadbytečnosti", "262/2006", "labor"),
    ("kdy může zaměstnavatel dát výpověď", "262/2006", "labor"),
    ("jak dlouhá je výpovědní doba", "262/2006", "labor"),
    ("mohou mě propustit ve zkušební době", "262/2006", "labor"),
    # -- labor broad / situational --
    ("v práci mi neposkytli přestávku", "262/2006", "broad"),
    ("zaměstnavatel mi dluhuje mzdu", "262/2006", "broad"),
    # -- legal but out-of-scope --
    ("kupní smlouva", "labor_gate", "out_of_scope"),
    ("rozvod", "labor_gate", "out_of_scope"),
    ("vražda", "labor_gate", "out_of_scope"),
    ("správní řízení", "labor_gate", "out_of_scope"),
    ("daňové přiznání", "labor_gate", "out_of_scope"),
    # -- non-legal --
    ("kolik je hodin", "labor_gate", "non_legal"),
    ("počasí Praha zítra", None, "irrelevant"),
    ("recept na svíčkovou", None, "irrelevant"),
    ("python programming tutorial", None, "irrelevant"),
    # -- ambiguous --
    ("§ 52", "labor_gate", "ambiguous"),
    ("§ 1", "labor_gate", "ambiguous"),
    ("výpověď", "labor_gate", "ambiguous"),
    ("nárok", "labor_gate", "ambiguous"),
    ("mzda", "labor_gate", "ambiguous"),
    ("dovolená", "labor_gate", "ambiguous"),
]

ANSWER_TESTS = [
    {
        "query": "§ 52 zákoník práce",
        "expected_doc": "262/2006",
        "required_any": ["výpověď", "důvody výpovědi", "zaměstnavatel"],
        "forbidden": ["okamžité zrušení pracovního poměru"],
    },
    {
        "query": "výpovědní doba zákoník práce",
        "expected_doc": "262/2006",
        "required_any": ["výpovědní doba", "2 měsíce", "dva měsíce"],
        "top_chunk_must_be_substantive": True,
    },
    {
        "query": "pracovní smlouva zákoník práce náležitosti",
        "expected_doc": "262/2006",
        "required_any": [
            "pracovní smlouva musí obsahovat",
            "druh práce",
            "místo výkonu práce",
            "den nástupu",
        ],
        "top_chunk_must_be_substantive": True,
    },
    {
        "query": "mám nárok na odstupné při nadbytečnosti",
        "expected_doc": "262/2006",
        "required_any": ["odstupné", "nadbytečnost", "výpověď"],
        "top_chunk_must_be_substantive": True,
    },
]

_STRUCTURAL_INDEX_RE = re.compile(
    r"^\d{1,3}\.\s+(?:z[aá]kon|na[rř][íi]zen[íi]|vyhl[áa][šs]ka|sd[eě]len[íi])",
    re.IGNORECASE | re.UNICODE,
)
_STRUCTURAL_SECTION_RE = re.compile(
    r"^(?:část|hlava|díl|oddíl|pododdíl|kapitola)\b",
    re.IGNORECASE | re.UNICODE,
)
_HEADING_VERB_HINTS = (
    "je", "jsou", "má", "ma", "musí", "musi", "může", "muze", "lze",
    "činí", "cini", "obsahuje", "obsahovat", "upravuje", "vzniká",
    "vznika", "zaniká", "zanika", "trvá", "trva",
)


def post_search(query: str, top_k: int = 5):
    payload = json.dumps({
        "query": query,
        "country": "czechia",
        "domain": "law",
        "top_k": top_k,
    }).encode()
    req = urllib.request.Request(
        f"{BASE}/search",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def post_search_answer(query: str, top_k: int = 3):
    payload = json.dumps({
        "query": query,
        "country": "czechia",
        "domain": "law",
        "top_k": top_k,
    }).encode()
    req = urllib.request.Request(
        f"{BASE}/search/answer",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _doc_matches(doc_id: str, expected: str) -> bool:
    """Match doc_id against expected.
    Expected format: 'NUMBER/YEAR' (e.g. '262/2006').
    doc_id format:   'local:sb/YEAR/NUMBER' (e.g. 'local:sb/2006/262').
    Also accepts direct substring match for flexibility.
    """
    if not expected or not doc_id:
        return False
    if expected in doc_id:
        return True
    # Parse 'NUMBER/YEAR' → check 'local:sb/YEAR/NUMBER'
    parts = expected.split("/")
    if len(parts) == 2:
        number, year = parts
        iri = f"local:sb/{year}/{number}"
        if iri == doc_id or iri in doc_id:
            return True
    return False


def _is_structural_text(text: str) -> bool:
    value = (text or "").strip()
    if not value:
        return True
    if _STRUCTURAL_INDEX_RE.match(value) or _STRUCTURAL_SECTION_RE.match(value):
        return True

    words = re.findall(r"\w+", value, flags=re.UNICODE)
    if len(value) < 120 and len(words) <= 12 and not re.search(r"[.!?;:]", value):
        lowered = value.lower()
        if not any(hint in lowered for hint in _HEADING_VERB_HINTS):
            return True
    return False


def check_result(data: dict, expected_doc: str | None, category: str) -> tuple[bool, str]:
    results = data.get("results", [])
    if not results:
        if expected_doc is None:
            return True, "no results (ok for irrelevant)"
        return False, "empty results"

    top = results[0]
    top_doc = top.get("document_id", "")
    top_tags = top.get("tags") or []
    top_src = top.get("source_type", "")
    top_id = top.get("chunk_id", "")
    score = top.get("score", 0.0)
    text_snippet = (top.get("text") or "")[:60].replace("\n", " ")

    if category == "clarification":
        if top_src in ("clarification", "clarification_suggestion") or "clarification" in top_id:
            return True, f"clarification OK  id={top_id!r}"
        return False, f"expected clarification, got doc={top_doc!r} src={top_src!r}"

    if category == "ambiguous":
        if top_id == "labor_gate:ambiguous":
            return True, f"ambiguous OK  id={top_id!r}"
        return False, f"expected ambiguous gate, got doc={top_doc!r} id={top_id!r}"

    if category == "out_of_scope":
        if top_id == "labor_gate:legal_out_of_scope":
            return True, f"out_of_scope OK  id={top_id!r}"
        return False, f"expected out_of_scope gate, got doc={top_doc!r} id={top_id!r}"

    if category == "non_legal":
        if top_id == "labor_gate:non_legal":
            return True, f"non_legal OK  id={top_id!r}"
        return False, f"expected non_legal gate, got doc={top_doc!r} id={top_id!r}"

    if category == "irrelevant":
        if "irrelevant_query" in top_tags or top_id in ("irrelevant_query", "no_result", "labor_gate:non_legal"):
            return True, f"irrelevant OK  tags={top_tags}"
        if score == 0.0 and top_doc == "":
            return True, "score=0 no doc (ok)"
        return False, f"expected irrelevant, got doc={top_doc!r} score={score:.3f} tags={top_tags}"

    if _doc_matches(top_doc, expected_doc):
        return True, f"doc={top_doc!r} score={score:.3f} text={text_snippet!r}"
    # Also check 2nd result
    if len(results) > 1:
        sec = results[1]
        if _doc_matches(sec.get("document_id") or "", expected_doc):
            return True, f"2nd doc={sec.get('document_id')!r} score={sec.get('score', 0):.3f}"
    return False, f"expected {expected_doc!r} got {top_doc!r} score={score:.3f} text={text_snippet!r}"


def check_answer_result(spec: dict, data: dict) -> tuple[bool, str]:
    results = data.get("results", [])
    response = data.get("response") or {}
    if not results:
        return False, "empty results"

    top = results[0]
    top_doc = top.get("document_id", "")
    if not _doc_matches(top_doc, spec["expected_doc"]):
        return False, f"expected top doc {spec['expected_doc']!r}, got {top_doc!r}"

    top_text = top.get("text") or ""
    if spec.get("top_chunk_must_be_substantive") and _is_structural_text(top_text):
        return False, f"top chunk is structural: {top_text[:80]!r}"

    summary = str(response.get("summary") or "")
    explanation = str(response.get("explanation") or "")
    answer_text = f"{summary}\n{explanation}".lower()

    required_any = [item.lower() for item in spec.get("required_any", [])]
    if required_any and not any(item in answer_text for item in required_any):
        return False, f"missing required explanation signal from {required_any!r}"

    forbidden = [item.lower() for item in spec.get("forbidden", [])]
    for phrase in forbidden:
        if phrase in answer_text:
            return False, f"forbidden phrase present: {phrase!r}"

    return True, f"doc={top_doc!r} top={top_text[:60]!r}"


def main():
    passed = 0
    failed = 0
    errors = 0
    fail_lines = []

    header = "{:<50} {:<14} {:<8}  {}".format("QUERY", "CATEGORY", "RESULT", "DETAIL")
    print(header)
    print("-" * 120)

    for query, expected_doc, category in TESTS:
        try:
            data = post_search(query)
            ok, detail = check_result(data, expected_doc, category)
        except Exception as exc:
            ok = False
            detail = f"ERROR: {exc}"
            errors += 1

        status = "PASS" if ok else "FAIL"
        line = "{:<50} {:<14} {:<8}  {}".format(query[:49], category, status, detail)
        print(line)
        if ok:
            passed += 1
        else:
            failed += 1
            fail_lines.append(line)

    print("-" * 120)
    for spec in ANSWER_TESTS:
        query = spec["query"]
        try:
            data = post_search_answer(query)
            ok, detail = check_answer_result(spec, data)
        except Exception as exc:
            ok = False
            detail = f"ERROR: {exc}"
            errors += 1

        status = "PASS" if ok else "FAIL"
        line = "{:<50} {:<14} {:<8}  {}".format(query[:49], "answer_eval", status, detail)
        print(line)
        if ok:
            passed += 1
        else:
            failed += 1
            fail_lines.append(line)

    print("\n" + "=" * 120)
    total = len(TESTS) + len(ANSWER_TESTS)
    print(f"TOTAL: {total}  PASS: {passed}  FAIL: {failed}  ERRORS: {errors}")
    if fail_lines:
        print("\nFAILED:")
        for l in fail_lines:
            print(" ", l)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
