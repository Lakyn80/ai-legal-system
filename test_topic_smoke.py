"""Diagnostic: verify expansion reaches sparse retriever + check penalty regex."""
from app.modules.czechia.retrieval.query_analyzer import CzechQueryAnalyzer
from app.modules.czechia.retrieval.sparse_retriever import CzechLawSparseRetriever
from app.modules.czechia.retrieval.reranker import _structural_penalty

analyzer = CzechQueryAnalyzer()
sparse = CzechLawSparseRetriever(url="http://ai-legal-qdrant:6333")

# 1. Verify expansion
print("=== EXPANSION CHECK ===")
for q in ["výpověď zákoník práce", "dovolená zákoník práce délka",
          "kupní smlouva občanský zákoník", "náhrada škody občanský zákoník",
          "trestní zákoník vražda trest", "odstupné zákoník práce podmínky"]:
    from app.modules.common.query_parser import parse_query
    parsed = parse_query(q)
    u = analyzer.analyze(parsed["normalized_query"])
    print(f"Q={q!r}")
    print(f"  mode={u.query_mode} law_refs={[r.law_iri for r in u.detected_law_refs]}")
    print(f"  expanded={u.expanded_query!r}")
    print()

# 2. Verify sparse results with expansion
print("=== SPARSE WITH EXPANSION ===")
tests = [
    ("dovolená zákoník práce délka", "local:sb/2006/262",
     "dovolená zákoník práce délka dovolená § 211 § 212 § 213 § 214 § 215"),
    ("kupní smlouva občanský zákoník", "local:sb/2012/89",
     "kupní smlouva občanský zákoník kupní smlouva § 2079 § 2080 § 2085 § 2099"),
    ("trestní zákoník vražda trest", "local:sb/2009/40",
     "trestní zákoník vražda trest vražda § 140 § 141"),
]
for q, law, expanded in tests:
    hits = sparse.retrieve(expanded, law_iris=[law], top_k=5)
    print(f"Q={q!r} (expanded)")
    for h in hits[:5]:
        text = (h.get("text") or "")[:75].replace("\n", " ")
        score = h.get("_sparse_score", 0)
        print(f"  score={score:.1f} | {text}")
    print()

# 3. Penalty check for kupní smlouva junk lines
print("=== PENALTY CHECK ===")
samples = [
    "21. Část první zákona č. 367/2000 Sb., kterým se mění zákon č. 40/1964 Sb., občanský zákoník .",
    "49. Část první zákona č. 28/2011 Sb., kterým se mění zákon č. 40/1964 Sb., občanský zákoník .",
    "1. zákon č. 65/1965 Sb., zákoník práce ,",
    "16. nařízení vlády č. 108/1994 Sb.,",
    "Odstupné",
    "Zaměstnavatel může dát zaměstnanci výpověď jen z těchto důvodů:",
]
for s in samples:
    p = _structural_penalty(s)
    print(f"  penalty={p:.2f} | {s[:70]}")
