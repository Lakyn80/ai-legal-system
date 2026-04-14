from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ClaimCheck:
    law: str
    article: str
    claim_type: str
    claim_text: str
    article_excerpt: str
    verdict: str
    reason: str


def _extract_response_json(raw_text: str) -> dict[str, Any]:
    marker = "=== RESPONSE JSON ==="
    idx = raw_text.find(marker)
    if idx == -1:
        raise ValueError("Marker '=== RESPONSE JSON ===' not found in output log.")
    payload = raw_text[idx + len(marker):]
    start = payload.find("{")
    if start == -1:
        raise ValueError("No JSON object found after response marker.")

    depth = 0
    end = -1
    in_str = False
    escape = False
    for i, ch in enumerate(payload[start:], start=start):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        raise ValueError("Could not detect end of RESPONSE JSON object.")
    block = payload[start : end + 1]
    return json.loads(block)


def _find_law_files(corpus_root: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for p in corpus_root.rglob("*.txt"):
        n = p.name.lower()
        if "гражданский процессуальный кодекс" in n and "гпк" not in out:
            out["гпк"] = p
        if "конвенция о защите прав человека" in n and "екпч" not in out:
            out["екпч"] = p
        if "семейный кодекс" in n and "ск" not in out:
            out["ск"] = p
    return out


def _map_law_to_key(law: str) -> str | None:
    l = law.lower().strip()
    if "гпк" in l or "civil procedure" in l:
        return "гпк"
    if "екпч" in l or "echr" in l or "конвенция" in l:
        return "екпч"
    if "ск" in l or "семейный" in l or "family" in l:
        return "ск"
    return None


def _extract_article(text: str, article_num: str) -> str:
    # Matches e.g. "Статья 9", "Статья 390.1", optional trailing dot
    escaped_num = re.escape(article_num)
    pattern = re.compile(
        rf"^\s*Статья\s+{escaped_num}\.?\s*.*?(?=^\s*Статья\s+\d+(?:\.\d+)?\.?\s*|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(text)
    if not m:
        return ""
    return m.group(0).strip()


def _trim_excerpt(text: str, max_len: int = 700) -> str:
    one = " ".join(text.split())
    return one[:max_len] + ("..." if len(one) > max_len else "")


_DOCTRINAL_RULES: list[tuple] = [
    # (law_pattern, article, claim_keywords, verdict, reason)
    # ГПК 438 — ТОЛЬКО возобновление исполнительного производства. НИКОГДА не basis for
    # appellate deadline restoration. ГПК 112 is the correct basis.
    (
        "гпк", "438",
        ["appeal deadline", "апел", "срок обжалован", "восстановл", "deadline restor", "пропущ"],
        "MISMATCH",
        "GPK 438 governs renewal of enforcement proceedings (исполнительное производство), NOT "
        "restoration of appeal deadlines. Use GPK 112 for deadline restoration.",
    ),
    # ГПК 329 — form of appellate court ruling; NOT the basis for reversal grounds or service
    (
        "гпк", "329",
        ["service", "notice", "извещ", "вручен", "foreign service", "reversal ground", "отмен"],
        "SUSPECT",
        "GPK 329 describes the form of the appellate ruling (содержание апелляционного определения). "
        "Use GPK 330 for reversal grounds, GPK 113 for notice. GPK 329 is not a service/notice/reversal anchor.",
    ),
    # ЕКПЧ ст.5 — свобода и личная неприкосновенность; not for civil procedure notice/service
    (
        "екпч", "5",
        ["civil", "notice", "service", "извещ", "граждан", "alimony", "переводч"],
        "SUSPECT",
        "ECHR Art. 5 concerns liberty and personal security (arrest/detention), not civil procedure "
        "notice/service/interpreter rights. Use ECHR Art. 6 for fair-trial support in civil cases.",
    ),
    # ГПК 328 — appellate court powers, not reversal grounds
    (
        "гпк", "328",
        ["reversal ground", "основани", "отмен", "mandatory reversal", "notice defect"],
        "SUSPECT",
        "GPK 328 lists appellate court powers (affirm/modify/reverse). "
        "GPK 330 lists the specific grounds for reversal. Use 330 as the anchor for reversal arguments.",
    ),
    # Prevent GK (civil code) from appearing as primary procedural basis
    (
        "гк рф", None,
        ["notice", "service", "interpreter", "переводч", "извещ", "алимент"],
        "SUSPECT",
        "GK РФ (Civil Code) is not a procedural law. Procedural notice/service/interpreter claims must "
        "be anchored in GPK, not in the Civil Code.",
    ),
]


def _evaluate_claim(law: str, article: str, claim: str, article_text: str) -> tuple[str, str]:
    if not article_text:
        return ("MISMATCH", "Article text not found in corpus.")

    low_claim = claim.lower()
    low_law = law.lower()

    for rule_law, rule_article, rule_keywords, rule_verdict, rule_reason in _DOCTRINAL_RULES:
        if rule_law not in low_law:
            continue
        if rule_article is not None and article != rule_article:
            continue
        if any(kw in low_claim for kw in rule_keywords):
            return (rule_verdict, rule_reason)

    return ("OK", "No direct contradiction detected against article text.")


def _collect_claims(agent2_output: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    claims: list[tuple[str, str, str, str]] = []
    for row in agent2_output.get("primary_legal_basis", []):
        prov = row.get("provision", {})
        claims.append((str(prov.get("law", "")), str(prov.get("article", "")), "primary_legal_basis", str(row.get("why_it_matters", ""))))
    for row in agent2_output.get("supporting_legal_basis", []):
        prov = row.get("provision", {})
        claims.append((str(prov.get("law", "")), str(prov.get("article", "")), "supporting_legal_basis", str(row.get("how_it_reinforces", ""))))
    for row in agent2_output.get("fact_to_law_mapping", []):
        for prov in row.get("legal_provisions", []):
            claims.append((str(prov.get("law", "")), str(prov.get("article", "")), "fact_to_law_mapping", str(row.get("comment", ""))))
    return claims


def run(agent_output_log: Path, corpus_root: Path) -> int:
    raw = agent_output_log.read_text(encoding="utf-8", errors="replace")
    response = _extract_response_json(raw)
    output = response.get("output")
    if not isinstance(output, dict):
        raise ValueError("RESPONSE JSON does not contain Agent2 'output' object.")

    law_files = _find_law_files(corpus_root)
    if "гпк" not in law_files:
        raise FileNotFoundError("GPK corpus file not found in Ruske_zakony.")
    if "екпч" not in law_files:
        raise FileNotFoundError("ECHR corpus file not found in Ruske_zakony.")
    # SK is optional — validation proceeds without it but SK claims get SUSPECT verdict

    corpus_texts = {
        key: path.read_text(encoding="utf-16")
        for key, path in law_files.items()
    }

    checks: list[ClaimCheck] = []
    for law, article, claim_type, claim_text in _collect_claims(output):
        key = _map_law_to_key(law)
        if key is None:
            checks.append(
                ClaimCheck(
                    law=law,
                    article=article,
                    claim_type=claim_type,
                    claim_text=claim_text,
                    article_excerpt="",
                    verdict="SUSPECT",
                    reason="Law not mapped to known corpus file in this validator.",
                )
            )
            continue
        article_text = _extract_article(corpus_texts[key], article)
        verdict, reason = _evaluate_claim(law, article, claim_text, article_text)
        checks.append(
            ClaimCheck(
                law=law,
                article=article,
                claim_type=claim_type,
                claim_text=claim_text,
                article_excerpt=_trim_excerpt(article_text),
                verdict=verdict,
                reason=reason,
            )
        )

    print("=== VALIDATION REPORT ===")
    print(f"Input log: {agent_output_log}")
    print(f"Corpus root: {corpus_root}")
    for key, path in sorted(law_files.items()):
        print(f"Detected {key.upper()} file: {path}")
    print()

    for i, c in enumerate(checks, start=1):
        print(f"[{i}] {c.verdict}  {c.law} ст.{c.article}  ({c.claim_type})")
        print(f"CLAIM: {c.claim_text}")
        print(f"ARTICLE TEXT: {c.article_excerpt if c.article_excerpt else '(not found)'}")
        print(f"REASON: {c.reason}")
        print("-" * 80)

    counts = {"OK": 0, "SUSPECT": 0, "MISMATCH": 0}
    for c in checks:
        counts[c.verdict] = counts.get(c.verdict, 0) + 1
    print("SUMMARY:", counts)
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Validate Agent2 legal claims against Russian corpus text.")
    parser.add_argument("--agent-output-log", required=True, help="Path to run_russia_strategy output log text file.")
    parser.add_argument(
        "--corpus-root",
        default="C:/Users/lukas/Desktop/PYTHON_PROJECTS_DESKTOP/PYTHON_PROJECTS/ai-legal-system/Ruske_zakony",
        help="Path to Ruske_zakony corpus root.",
    )
    args = parser.parse_args()
    try:
        return run(Path(args.agent_output_log), Path(args.corpus_root))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
