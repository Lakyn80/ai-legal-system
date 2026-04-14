"""
End-to-end test script: search → Agent 2 strategy for the Czech-Russian alimony case.

Usage:
    python backend/scripts/run_russia_strategy.py \
        --query "..." \
        --output-log path/to/output.txt

Output log includes "=== RESPONSE JSON ===" marker expected by validate_agent2_truth.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import urllib.request
    import urllib.error
except ImportError:
    pass


def _post(url: str, body: dict) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} from {url}: {detail}") from e


def _law_label(law_id: str) -> str:
    mapping = {
        "local:ru/gpk": "ГПК РФ",
        "local:ru/sk": "СК РФ",
        "local:ru/echr": "ЕКПЧ",
        "local:ru/fl115": "ФЗ-115",
        "local:ru/uk": "УК РФ",
    }
    return mapping.get(law_id, law_id)


def build_strategy_request(search_resp: dict, query: str) -> dict:
    results = search_resp.get("results", [])
    issue_flags = search_resp.get("issue_flags", [])

    # Build retrieved_articles (deduped by law+article)
    seen: set[tuple[str, str]] = set()
    retrieved_articles = []
    for r in results:
        law_label = _law_label(r.get("law_id", ""))
        art = str(r.get("article_num", ""))
        if not art or (law_label, art) in seen:
            continue
        seen.add((law_label, art))
        retrieved_articles.append({
            "law": law_label,
            "article": art,
            "excerpt": r.get("text", "")[:1200],
        })

    # Build primary_sources list from anchor/high-score results
    primary_sources = [
        {"law": a["law"], "article": a["article"], "title": None}
        for a in retrieved_articles
    ]

    evidence_pack = {
        "primary_sources": primary_sources,
        "supporting_sources": [],
        "retrieved_articles": retrieved_articles,
        "matched_issues": issue_flags,
        "retrieval_notes": [
            f"taxonomy_applied={search_resp.get('taxonomy_applied')}",
            f"fallback_reason={search_resp.get('fallback_reason')}",
        ],
    }

    return {
        "input": {
            "case_id": "test-czech-ru-alimony-001",
            "jurisdiction": "Russia",
            "cleaned_summary": query,
            "facts": [
                "Applicant is a Czech citizen residing in Czech Republic.",
                "A Russian court adjudicated an alimony case without notifying the applicant at their foreign address.",
                "No interpreter was provided during the proceedings.",
                "The applicant did not learn of the decision until enforcement proceedings began.",
            ],
            "timeline": [],
            "issue_flags": issue_flags,
            "claims_or_questions": [
                "Is the judgment subject to reversal due to absence of interpreter?",
                "Was the notice/service to a foreign address legally valid?",
                "Can the appellate deadline be restored?",
            ],
            "legal_evidence_pack": evidence_pack,
            "optional_missing_items": [],
        },
        "strict_reliability": True,
        "max_repair_attempts": 1,
    }


def run(base_url: str, query: str, output_log: Path) -> int:
    print(f"[1/3] Searching for: {query[:80]}...", file=sys.stderr)
    search_resp = _post(f"{base_url}/api/russia/search", {
        "query": query,
        "mode": "hybrid",
        "top_k": 12,
    })
    print(f"      issues: {search_resp.get('issue_flags')}", file=sys.stderr)
    print(f"      taxonomy_applied: {search_resp.get('taxonomy_applied')}", file=sys.stderr)
    print(f"      fallback_reason: {search_resp.get('fallback_reason')}", file=sys.stderr)
    arts = [(r["law_id"], r["article_num"]) for r in search_resp.get("results", [])]
    print(f"      articles: {arts}", file=sys.stderr)

    print("[2/3] Building strategy request...", file=sys.stderr)
    strategy_req = build_strategy_request(search_resp, query)

    print("[3/3] Calling /api/russia/strategy (Agent 2)...", file=sys.stderr)
    strategy_resp = _post(f"{base_url}/api/russia/strategy", strategy_req)

    log_lines = [
        "=== SEARCH RESPONSE ===",
        json.dumps(search_resp, ensure_ascii=False, indent=2),
        "",
        "=== STRATEGY REQUEST ===",
        json.dumps(strategy_req, ensure_ascii=False, indent=2),
        "",
        "=== RESPONSE JSON ===",
        json.dumps(strategy_resp, ensure_ascii=False, indent=2),
        "",
    ]
    output_log.parent.mkdir(parents=True, exist_ok=True)
    output_log.write_text("\n".join(log_lines), encoding="utf-8")
    print(f"[OK] Output log: {output_log}", file=sys.stderr)
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Run end-to-end Russia strategy test.")
    parser.add_argument(
        "--query",
        default=(
            "Я гражданин Чехии. В России без переводчика и без уведомления "
            "по моему чешскому адресу рассмотрели дело об алиментах. "
            "Как мне обжаловать решение и восстановить срок?"
        ),
    )
    parser.add_argument("--base-url", default="http://localhost:8032")
    parser.add_argument("--output-log", default="agent2_output.log")
    args = parser.parse_args()

    try:
        return run(
            base_url=args.base_url,
            query=args.query,
            output_log=Path(args.output_log),
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
