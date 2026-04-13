import pytest

from app.modules.czechia.retrieval.labor_gate import LaborGate


@pytest.mark.parametrize(
    ("query", "expected_bucket"),
    [
        ("kolik je hodin", "non_legal"),
        ("počasí Praha zítra", "non_legal"),
        ("kupní smlouva", "legal_out_of_scope"),
        ("rozvod", "legal_out_of_scope"),
        ("vražda", "legal_out_of_scope"),
        ("správní řízení", "legal_out_of_scope"),
        ("daňové přiznání", "legal_out_of_scope"),
        ("§ 52", "ambiguous"),
        ("§ 1", "ambiguous"),
        ("výpověď", "ambiguous"),
        ("nárok", "ambiguous"),
        ("mzda", "ambiguous"),
        ("dovolená", "ambiguous"),
        ("§ 52 zákoník práce", "labor_in_domain"),
        ("zákon 262/2006 § 52", "labor_in_domain"),
        ("výpověď zákoník práce", "labor_in_domain"),
        ("mám nárok na odstupné při výpovědi pro nadbytečnost", "labor_in_domain"),
        ("jak dlouhá je výpovědní doba", "labor_in_domain"),
        ("můžou mě propustit ve zkušební době", "labor_in_domain"),
    ],
)
def test_labor_gate_buckets_queries(query: str, expected_bucket: str) -> None:
    decision = LaborGate().evaluate(query)

    assert decision.bucket == expected_bucket
    assert decision.allows_retrieval is (expected_bucket == "labor_in_domain")

