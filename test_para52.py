"""Quick smoke test for §52 answer quality."""
import json
import urllib.request

payload = json.dumps({
    "query": "co říká § 52 zákoník práce",
    "country": "CZ",
    "top_k": 5
}).encode()

req = urllib.request.Request(
    "http://localhost:8000/api/v1/search/answer",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=30) as resp:
    data = json.loads(resp.read())

print("answer_type:", data.get("answer_type"))
print("summary:", data.get("summary", "")[:200])
print()
print("--- chunks ---")
for i, c in enumerate(data.get("chunks", [])[:5]):
    text = (c.get("text") or "")[:80].replace("\n", " ")
    score = c.get("score", 0)
    print(f"[{i}] score={score:.3f} | {text}")
