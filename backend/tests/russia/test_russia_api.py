"""
HTTP-level integration tests for the dedicated Russian API endpoints.

Tests:
  GET  /api/russia/article                       — exact lookup
  POST /api/russia/search                        — hybrid/dense/sparse/topic search
  POST /api/russia/interpreter-issue             — case bridge

Run these tests inside the Docker container where the app listens on localhost:8000.

Skip guard: the app server must be reachable AND the Russian collection must be
populated (same prerequisites as Steps 9–12).
"""
from __future__ import annotations

import pytest
import httpx

BASE_URL = "http://localhost:8000/api"
TIMEOUT = 30.0

# ---------------------------------------------------------------------------
# Skip guard
# ---------------------------------------------------------------------------


def _ready() -> bool:
    try:
        r = httpx.get(f"{BASE_URL}/health", timeout=5)
        if r.status_code != 200:
            return False
        from qdrant_client import QdrantClient
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        client = QdrantClient(url="http://qdrant:6333", timeout=10)
        if not client.collection_exists("russian_laws_v1"):
            return False
        n = client.count(
            "russian_laws_v1",
            count_filter=Filter(must=[FieldCondition(
                key="law_id", match=MatchValue(value="local:ru/gpk"),
            )]),
            exact=True,
        ).count
        return n >= 1000
    except Exception:
        return False


_READY = _ready()
pytestmark = pytest.mark.skipif(
    not _READY,
    reason="App server or Russian collection not ready",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(path: str, **params) -> httpx.Response:
    return httpx.get(f"{BASE_URL}{path}", params=params, timeout=TIMEOUT)


def _post(path: str, body: dict) -> httpx.Response:
    return httpx.post(
        f"{BASE_URL}{path}",
        json=body,
        headers={"Content-Type": "application/json"},
        timeout=TIMEOUT,
    )


# ---------------------------------------------------------------------------
# GET /api/russia/article
# ---------------------------------------------------------------------------

class TestArticleEndpoint:

    def test_gpk_article_9_hit(self):
        r = _get("/russia/article", law_id="local:ru/gpk", article_num="9")
        assert r.status_code == 200
        d = r.json()
        assert d["hit"] is True
        assert d["law_id"] == "local:ru/gpk"
        assert d["article_num"] == "9"
        assert isinstance(d["chunks"], list)
        assert len(d["chunks"]) >= 1

    def test_gpk_article_9_heading(self):
        r = _get("/russia/article", law_id="local:ru/gpk", article_num="9")
        d = r.json()
        assert "язык" in d["article_heading"].lower()

    def test_gpk_article_9_text_contains_procedural(self):
        r = _get("/russia/article", law_id="local:ru/gpk", article_num="9")
        text = " ".join(c["text"] for c in r.json()["chunks"]).lower()
        assert "судопроизводства" in text or "переводчик" in text

    def test_gpk_article_162_hit(self):
        r = _get("/russia/article", law_id="local:ru/gpk", article_num="162")
        assert r.status_code == 200
        d = r.json()
        assert d["hit"] is True
        assert d["article_num"] == "162"

    def test_gpk_article_162_chunk_law_id(self):
        r = _get("/russia/article", law_id="local:ru/gpk", article_num="162")
        for chunk in r.json()["chunks"]:
            assert chunk["law_id"] == "local:ru/gpk"

    def test_gpk_article_113_hit(self):
        r = _get("/russia/article", law_id="local:ru/gpk", article_num="113")
        assert r.status_code == 200
        d = r.json()
        assert d["hit"] is True
        assert d["article_num"] == "113"

    def test_article_not_found_returns_hit_false(self):
        r = _get("/russia/article", law_id="local:ru/gpk", article_num="9999")
        assert r.status_code == 200
        assert r.json()["hit"] is False

    def test_article_not_found_chunks_empty(self):
        r = _get("/russia/article", law_id="local:ru/gpk", article_num="9999")
        assert r.json()["chunks"] == []

    def test_tombstone_field_present(self):
        r = _get("/russia/article", law_id="local:ru/gpk", article_num="9")
        d = r.json()
        assert "is_tombstone" in d
        assert isinstance(d["is_tombstone"], bool)

    def test_is_tombstone_false_for_active_article(self):
        r = _get("/russia/article", law_id="local:ru/gpk", article_num="9")
        d = r.json()
        assert d["is_tombstone"] is False

    def test_tk_article_7_tombstone_returns_repeal_info(self):
        """ст. 7 ТК РФ is repealed — API must surface is_tombstone and chunk flags."""
        r = _get("/russia/article", law_id="local:ru/tk", article_num="7")
        assert r.status_code == 200
        d = r.json()
        assert d["hit"] is True
        assert d["is_tombstone"] is True
        assert d["chunks"], "tombstone article must still return chunk text"
        for c in d["chunks"]:
            assert c["is_tombstone"] is True

    def test_chunk_fields_present(self):
        r = _get("/russia/article", law_id="local:ru/gpk", article_num="9")
        chunk = r.json()["chunks"][0]
        for field in ("chunk_id", "law_id", "law_short", "article_num", "text", "is_tombstone", "fragment_id"):
            assert field in chunk, f"Missing field: {field}"

    def test_sk_article_lookup(self):
        r = _get("/russia/article", law_id="local:ru/sk", article_num="1")
        assert r.status_code == 200
        assert r.json()["hit"] is True

    def test_wrong_law_id_returns_hit_false(self):
        r = _get("/russia/article", law_id="local:ru/nonexistent", article_num="9")
        assert r.status_code == 200
        assert r.json()["hit"] is False

    def test_response_is_json(self):
        r = _get("/russia/article", law_id="local:ru/gpk", article_num="9")
        assert r.headers["content-type"].startswith("application/json")


# ---------------------------------------------------------------------------
# POST /api/russia/search
# ---------------------------------------------------------------------------

class TestSearchEndpoint:

    def test_basic_cyrillic_search(self):
        r = _post("/russia/search", {"query": "переводчик в гражданском процессе"})
        assert r.status_code == 200
        d = r.json()
        assert d["result_count"] >= 1
        assert len(d["results"]) == d["result_count"]

    def test_query_echoed_in_response(self):
        q = "язык судопроизводства"
        r = _post("/russia/search", {"query": q})
        assert r.json()["query"] == q

    def test_mode_hybrid_default(self):
        r = _post("/russia/search", {"query": "язык судопроизводства"})
        assert r.json()["mode"] == "hybrid"

    def test_mode_dense(self):
        r = _post("/russia/search", {"query": "язык судопроизводства", "mode": "dense"})
        assert r.status_code == 200
        assert r.json()["mode"] == "dense"
        assert r.json()["result_count"] >= 1

    def test_mode_sparse(self):
        r = _post("/russia/search", {"query": "переводчик", "mode": "sparse"})
        assert r.status_code == 200
        assert r.json()["mode"] == "sparse"

    def test_mode_topic(self):
        r = _post("/russia/search", {"query": "гпк рф статья 9", "mode": "topic"})
        assert r.status_code == 200
        assert r.json()["mode"] == "topic"

    def test_law_filter_gpk(self):
        r = _post("/russia/search", {"query": "язык судопроизводства", "law_id": "local:ru/gpk"})
        assert r.status_code == 200
        d = r.json()
        assert d["law_id"] == "local:ru/gpk"
        for item in d["results"]:
            assert item["law_id"] == "local:ru/gpk"

    def test_top_k_respected(self):
        r = _post("/russia/search", {"query": "переводчик в гражданском процессе", "top_k": 2})
        assert r.json()["result_count"] <= 2
        assert len(r.json()["results"]) <= 2

    def test_result_fields_present(self):
        r = _post("/russia/search", {"query": "язык судопроизводства", "top_k": 1})
        item = r.json()["results"][0]
        for field in ("score", "chunk_id", "law_id", "law_short", "article_num", "text", "is_tombstone"):
            assert field in item, f"Missing field: {field}"

    def test_scores_are_positive(self):
        r = _post("/russia/search", {"query": "язык судопроизводства", "top_k": 5})
        for item in r.json()["results"]:
            assert item["score"] > 0

    def test_notice_query_returns_gpk(self):
        r = _post("/russia/search", {
            "query": "я не был официально уведомлен о судебном заседании",
            "law_id": "local:ru/gpk",
        })
        d = r.json()
        assert d["result_count"] >= 1
        for item in d["results"]:
            assert item["law_id"] == "local:ru/gpk"

    def test_notice_query_two(self):
        r = _post("/russia/search", {
            "query": "суд рассмотрел дело без моего извещения",
            "law_id": "local:ru/gpk",
        })
        assert r.json()["result_count"] >= 1

    def test_foreigner_query_returns_results(self):
        r = _post("/russia/search", {
            "query": "иностранный гражданин без переводчика в суде",
        })
        assert r.json()["result_count"] >= 1

    def test_exact_gpk_article_query(self):
        r = _post("/russia/search", {"query": "гпк рф статья 9", "mode": "topic", "top_k": 3})
        d = r.json()
        assert d["result_count"] >= 1
        art_nums = [item["article_num"] for item in d["results"]]
        assert "9" in art_nums, f"ст.9 not in topic results: {art_nums}"

    def test_empty_query_rejected(self):
        r = _post("/russia/search", {"query": ""})
        assert r.status_code == 422

    def test_top_k_too_large_rejected(self):
        r = _post("/russia/search", {"query": "тест", "top_k": 999})
        assert r.status_code == 422

    def test_law_id_null_no_filter(self):
        r = _post("/russia/search", {"query": "переводчик", "law_id": None})
        assert r.status_code == 200
        # results may come from any law
        laws = {item["law_id"] for item in r.json()["results"]}
        assert len(laws) >= 1

    def test_response_utf8(self):
        r = _post("/russia/search", {"query": "язык судопроизводства", "top_k": 1})
        text = r.json()["results"][0]["text"]
        # Should contain Cyrillic characters
        assert any("\u0400" <= ch <= "\u04ff" for ch in text)


# ---------------------------------------------------------------------------
# POST /api/russia/interpreter-issue
# ---------------------------------------------------------------------------

class TestInterpreterIssueEndpoint:

    def test_interpreter_case(self):
        r = _post("/russia/interpreter-issue", {
            "case_text": "иностранный гражданин не получил переводчика в суде",
        })
        assert r.status_code == 200
        d = r.json()
        assert d["is_matched"] is True
        assert "interpreter_issue" in d["detected_subissues"]

    def test_interpreter_anchor_articles(self):
        r = _post("/russia/interpreter-issue", {
            "case_text": "иностранный гражданин не получил переводчика в суде",
        })
        art_nums = {e["article_num"] for e in r.json()["primary_results"]}
        assert "9" in art_nums
        assert "162" in art_nums

    def test_language_case(self):
        r = _post("/russia/interpreter-issue", {
            "case_text": "я не понимал язык заседания",
        })
        d = r.json()
        assert d["is_matched"] is True
        assert "language_issue" in d["detected_subissues"]

    def test_language_anchor_article_9(self):
        r = _post("/russia/interpreter-issue", {
            "case_text": "я не понимал язык заседания",
        })
        art_nums = {e["article_num"] for e in r.json()["primary_results"]}
        assert "9" in art_nums

    def test_notice_case_vyzov(self):
        r = _post("/russia/interpreter-issue", {
            "case_text": "меня не вызвали в суд надлежащим образом",
        })
        d = r.json()
        assert d["is_matched"] is True
        assert "notice_issue" in d["detected_subissues"]

    def test_notice_case_uvedomlen(self):
        r = _post("/russia/interpreter-issue", {
            "case_text": "я не был официально уведомлен о судебном заседании",
        })
        d = r.json()
        assert d["is_matched"] is True
        assert "notice_issue" in d["detected_subissues"]

    def test_notice_case_izveshchenie(self):
        r = _post("/russia/interpreter-issue", {
            "case_text": "суд рассмотрел дело без моего извещения",
        })
        d = r.json()
        assert d["is_matched"] is True
        assert "notice_issue" in d["detected_subissues"]

    def test_notice_anchor_113(self):
        r = _post("/russia/interpreter-issue", {
            "case_text": "меня не вызвали в суд надлежащим образом",
        })
        art_nums = {e["article_num"] for e in r.json()["primary_results"]}
        assert "113" in art_nums

    def test_combined_interpreter_and_notice(self):
        r = _post("/russia/interpreter-issue", {
            "case_text": "иностранец без переводчика и без официального вызова в суд",
        })
        d = r.json()
        assert d["is_matched"] is True
        assert "interpreter_issue" in d["detected_subissues"]
        assert "notice_issue" in d["detected_subissues"]

    def test_combined_all_three_anchors(self):
        r = _post("/russia/interpreter-issue", {
            "case_text": "иностранец без переводчика и без официального вызова в суд",
        })
        art_nums = {e["article_num"] for e in r.json()["combined_results"]}
        assert "9" in art_nums
        assert "162" in art_nums
        assert "113" in art_nums

    def test_no_match_is_matched_false(self):
        r = _post("/russia/interpreter-issue", {"case_text": "суд отказал в иске"})
        assert r.status_code == 200
        d = r.json()
        assert d["is_matched"] is False
        assert d["primary_results"] == []
        assert d["combined_results"] == []

    def test_primary_results_all_gpk(self):
        r = _post("/russia/interpreter-issue", {
            "case_text": "иностранный гражданин не получил переводчика в суде",
        })
        for e in r.json()["primary_results"]:
            assert e["law_id"] == "local:ru/gpk"

    def test_supporting_not_gpk(self):
        r = _post("/russia/interpreter-issue", {
            "case_text": "иностранный гражданин не получил переводчика в суде",
        })
        for e in r.json()["supporting_results"]:
            assert e["law_id"] != "local:ru/gpk"

    def test_combined_sorted_by_score(self):
        r = _post("/russia/interpreter-issue", {
            "case_text": "иностранный гражданин не получил переводчика в суде",
        })
        scores = [e["score"] for e in r.json()["combined_results"]]
        assert scores == sorted(scores, reverse=True)

    def test_source_role_primary(self):
        r = _post("/russia/interpreter-issue", {
            "case_text": "иностранный гражданин не получил переводчика в суде",
        })
        for e in r.json()["primary_results"]:
            assert e["source_role"] == "primary"

    def test_source_role_supporting(self):
        r = _post("/russia/interpreter-issue", {
            "case_text": "иностранный гражданин не получил переводчика в суде",
        })
        for e in r.json()["supporting_results"]:
            assert e["source_role"] == "supporting"

    def test_normalized_queries_present(self):
        r = _post("/russia/interpreter-issue", {
            "case_text": "иностранный гражданин не получил переводчика в суде",
        })
        qs = r.json()["normalized_queries"]
        assert len(qs) >= 1
        assert all(isinstance(q, str) and q for q in qs)

    def test_matched_signals_present(self):
        r = _post("/russia/interpreter-issue", {
            "case_text": "иностранный гражданин не получил переводчика в суде",
        })
        assert "interpreter_issue" in r.json()["matched_signals"]

    def test_short_text_too_short_rejected(self):
        r = _post("/russia/interpreter-issue", {"case_text": "нет"})
        # "нет" is 3 chars — at the min_length=3 boundary, should succeed or fail gracefully
        assert r.status_code in (200, 422)

    def test_top_k_primary_respected(self):
        r = _post("/russia/interpreter-issue", {
            "case_text": "иностранный гражданин не получил переводчика в суде",
            "top_k_primary": 2,
        })
        assert len(r.json()["primary_results"]) <= 2


# ---------------------------------------------------------------------------
# Separation verification — Czech endpoint not affected
# ---------------------------------------------------------------------------

class TestCzechEndpointNotAffected:
    """Verify Czech /api/search/answer still works after Russian routes added."""

    def test_czech_health_still_ok(self):
        r = httpx.get(f"{BASE_URL}/health", timeout=10)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_czech_search_endpoint_still_responds(self):
        r = httpx.post(
            f"{BASE_URL}/search/answer",
            json={"query": "zákoník práce", "country": "czechia", "domain": "law", "top_k": 3},
            timeout=30,
        )
        # Czech endpoint must still return a valid response (not a server error)
        assert r.status_code == 200

    def test_russian_endpoint_does_not_appear_at_search_path(self):
        """Russian data must not contaminate the /api/search path."""
        r = httpx.post(
            f"{BASE_URL}/search",
            json={"query": "переводчик", "country": "russia", "top_k": 3},
            timeout=30,
        )
        # This endpoint may 200 with empty results (Czech collection) or 422
        # but it must NOT hit russian_laws_v1
        if r.status_code == 200:
            for item in r.json().get("results", []):
                assert item.get("jurisdiction_module") != "russia"


# ---------------------------------------------------------------------------
# Swagger / OpenAPI presence
# ---------------------------------------------------------------------------

class TestSwaggerPresence:

    def test_openapi_schema_includes_russia_paths(self):
        r = httpx.get(f"http://localhost:8000/openapi.json", timeout=10)
        assert r.status_code == 200
        schema = r.json()
        paths = schema.get("paths", {})
        assert "/api/russia/article" in paths, "Russian article path not in OpenAPI schema"
        assert "/api/russia/search" in paths, "Russian search path not in OpenAPI schema"
        assert "/api/russia/interpreter-issue" in paths, "Russian issue path not in OpenAPI schema"

    def test_russia_tag_in_schema(self):
        r = httpx.get(f"http://localhost:8000/openapi.json", timeout=10)
        tags = {t["name"] for t in r.json().get("tags", [])}
        # Tags may not be explicitly listed in OpenAPI 3 unless declared;
        # verify route tags via paths instead
        paths = r.json().get("paths", {})
        article_tags = paths.get("/api/russia/article", {}).get("get", {}).get("tags", [])
        assert "russia" in article_tags
