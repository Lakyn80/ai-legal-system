"""98-query stress test for Czech law retrieval."""
import json
import sys
import urllib.request
import urllib.error

BASE = "http://localhost:8000/api"

TESTS = [
    # (query, expected_doc_fragment, category)
    # -- exact lookup (law + paragraph) --
    ("§ 52 zákoník práce", "262/2006", "exact"),
    ("§ 55 zákoník práce", "262/2006", "exact"),
    ("§ 56 zákoník práce", "262/2006", "exact"),
    ("§ 33 zákoník práce", "262/2006", "exact"),
    ("§ 245 zákoník práce", "262/2006", "exact"),
    ("§ 3 zákoník práce", "262/2006", "exact"),
    ("§ 35 zákoník práce", "262/2006", "exact"),
    ("§ 68 zákoník práce", "262/2006", "exact"),
    ("zákon 262/2006 § 52", "262/2006", "exact"),
    ("§ 89 občanský zákoník", "89/2012", "exact"),
    ("§ 2079 občanský zákoník", "89/2012", "exact"),
    ("§ 1 trestní zákoník", "40/2009", "exact"),
    ("§ 140 trestní zákoník", "40/2009", "exact"),
    ("§ 1 zákon o daních z příjmů", "586/1992", "exact"),
    ("§ 6 zákon o daních z příjmů", "586/1992", "exact"),
    ("zákon 586/1992 § 6", "586/1992", "exact"),
    ("zákon 500/2004 § 3", "500/2004", "exact"),
    ("zákon 90/2012 § 1", "90/2012", "exact"),
    # -- law constrained search --
    ("výpověď zákoník práce", "262/2006", "constrained"),
    ("pracovní smlouva zákoník práce náležitosti", "262/2006", "constrained"),
    ("dovolená zákoník práce délka", "262/2006", "constrained"),
    ("odstupné zákoník práce podmínky", "262/2006", "constrained"),
    ("přesčas zákoník práce maximum", "262/2006", "constrained"),
    ("kupní smlouva občanský zákoník", "89/2012", "constrained"),
    ("náhrada škody občanský zákoník", "89/2012", "constrained"),
    ("nájemní smlouva byt", "89/2012", "constrained"),
    ("dědictví občanský zákoník", "89/2012", "constrained"),
    ("trestní zákoník vražda trest", "40/2009", "constrained"),
    ("daně z příjmů fyzická osoba zákon 586/1992", "586/1992", "constrained"),
    ("správní řízení zákon 500/2004", "500/2004", "constrained"),
    ("s.r.o. zákon o obchodních korporacích", "90/2012", "constrained"),
    # -- domain search --
    ("jak dlouho trvá výpovědní doba", "262/2006", "domain"),
    ("kdy může zaměstnavatel okamžitě zrušit pracovní poměr", "262/2006", "domain"),
    ("podmínky výpovědi ze strany zaměstnavatele", "262/2006", "domain"),
    ("zaměstnanec nárok na odstupné", "262/2006", "domain"),
    ("pracovní úraz odpovědnost zaměstnavatele", "262/2006", "domain"),
    ("jak se počítá dovolená", "262/2006", "domain"),
    ("zkušební doba délka", "262/2006", "domain"),
    ("mzda minimální výše", "262/2006", "domain"),
    ("co je kupní smlouva", "89/2012", "domain"),
    ("kdy zaniká závazek", "89/2012", "domain"),
    ("daňové přiznání termín podání", "586/1992", "domain"),
    ("dan z prijmu fyzicke osoby", "586/1992", "domain"),
    ("trestny cin kradeže sazba", "40/2009", "domain"),
    ("správní orgán přezkum rozhodnutí", "500/2004", "domain"),
    ("valná hromada akciová společnost", "90/2012", "domain"),
    # -- broad search / mixed --
    ("v práci mi neposkytli přestávku", "262/2006", "broad"),
    ("zaměstnavatel mi dluhuje mzdu", "262/2006", "broad"),
    ("jsem ve zkušební době co mohu", "262/2006", "broad"),
    ("nájem bytu práva nájemce", "89/2012", "broad"),
    ("ublížení na zdraví trestní odpovědnost", "40/2009", "broad"),
    # -- bare paragraph (must return clarification) --
    ("§ 52", "clarification", "clarification"),
    ("§55", "clarification", "clarification"),
    ("§ 1", "clarification", "clarification"),
    ("§99a", "clarification", "clarification"),
    # -- nonsense / irrelevant --
    ("ahoj jak se mas", None, "irrelevant"),
    ("počasí Praha zítra", None, "irrelevant"),
    ("recept na svíčkovou", None, "irrelevant"),
    ("python programming tutorial", None, "irrelevant"),
    ("UEFA Champions League výsledky", None, "irrelevant"),
]


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

    if category == "irrelevant":
        if "irrelevant_query" in top_tags or top_id in ("irrelevant_query", "no_result"):
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

    print("\n" + "=" * 120)
    print(f"TOTAL: {len(TESTS)}  PASS: {passed}  FAIL: {failed}  ERRORS: {errors}")
    if fail_lines:
        print("\nFAILED:")
        for l in fail_lines:
            print(" ", l)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
