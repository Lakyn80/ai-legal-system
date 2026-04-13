"""Contract tests for taxonomy-first Russian search endpoint behavior."""
from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.core.dependencies import (
    get_russia_focus_taxonomy_service,
    get_russian_retrieval_service,
)
from app.main import app
from app.modules.common.legal_taxonomy.service import get_russia_focus_taxonomy_service as build_taxonomy
from app.modules.russia.retrieval.schemas import RussianSearchResult


def _result(*, law_id: str, article: str, score: float = 0.7) -> RussianSearchResult:
    return RussianSearchResult(
        score=score,
        chunk_id=f"{law_id}:{article}",
        law_id=law_id,
        law_short="TEST",
        article_num=article,
        article_heading="heading",
        part_num=None,
        chunk_index=0,
        razdel=None,
        glava="",
        text=f"text {law_id} {article}",
        fragment_id=f"{law_id}/{article}/0000",
        source_type="article",
        is_tombstone=False,
        source_file="x.txt",
    )


class FakeRussianRetrievalService:
    def __init__(self) -> None:
        self._db = {
            "local:ru/sk": [
                _result(law_id="local:ru/sk", article="80", score=0.4),
                _result(law_id="local:ru/sk", article="81", score=0.35),
                _result(law_id="local:ru/sk", article="113", score=0.31),
            ],
            "local:ru/gpk": [
                _result(law_id="local:ru/gpk", article="113", score=0.45),
                _result(law_id="local:ru/gpk", article="9", score=0.2),
                _result(law_id="local:ru/gpk", article="162", score=0.21),
                _result(law_id="local:ru/gpk", article="10", score=0.99),
                _result(law_id="local:ru/gpk", article="327.1", score=0.95),
                _result(law_id="local:ru/gpk", article="425", score=0.94),
                _result(law_id="local:ru/gpk", article="427.3", score=0.93),
                _result(law_id="local:ru/gpk", article="63.1", score=0.92),
            ],
            "local:ru/echr": [_result(law_id="local:ru/echr", article="6", score=0.1)],
            "local:ru/gk/1": [
                _result(law_id="local:ru/gk/1", article="260", score=0.9),
                _result(law_id="local:ru/gk/1", article="279", score=0.98),
                _result(law_id="local:ru/gk/1", article="286", score=0.97),
                _result(law_id="local:ru/gk/1", article="274", score=0.96),
            ],
        }

    def hybrid_search(self, query: str, law_id: str | None = None, top_k: int = 10, **_: object):
        if law_id is not None:
            return self._db.get(law_id, [])[:top_k]
        # Unconstrained fallback intentionally contains high-scoring unrelated GK row.
        out = self._db["local:ru/gk/1"] + self._db["local:ru/sk"] + self._db["local:ru/gpk"]
        return out[:top_k]

    def search(self, query: str, law_id: str | None = None, top_k: int = 10):
        return self.hybrid_search(query, law_id=law_id, top_k=top_k)

    def sparse_search(self, query: str, law_id: str | None = None, top_k: int = 10):
        rows = self.hybrid_search(query, law_id=law_id, top_k=top_k)
        return [replace(r, score=r.score + 0.05) for r in rows]

    def topic_search(self, query: str, top_k: int = 10):
        return (self._db["local:ru/gpk"] + self._db["local:ru/sk"] + self._db["local:ru/gk/1"])[:top_k]


class EmptyRussianRetrievalService:
    """Simulates live index failure: retrieval always returns no chunks."""

    def hybrid_search(self, query: str, law_id: str | None = None, top_k: int = 10, **_: object):
        return []

    def search(self, query: str, law_id: str | None = None, top_k: int = 10):
        return []

    def sparse_search(self, query: str, law_id: str | None = None, top_k: int = 10):
        return []

    def topic_search(self, query: str, top_k: int = 10):
        return []


@pytest.fixture
def client():
    startup_handlers = list(app.router.on_startup)
    app.router.on_startup.clear()
    app.dependency_overrides[get_russian_retrieval_service] = lambda: FakeRussianRetrievalService()
    app.dependency_overrides[get_russia_focus_taxonomy_service] = lambda: build_taxonomy()
    try:
        with TestClient(app) as tc:
            yield tc
    finally:
        app.dependency_overrides.clear()
        app.router.on_startup[:] = startup_handlers


@pytest.fixture
def client_empty_retrieval():
    startup_handlers = list(app.router.on_startup)
    app.router.on_startup.clear()
    app.dependency_overrides[get_russian_retrieval_service] = lambda: EmptyRussianRetrievalService()
    app.dependency_overrides[get_russia_focus_taxonomy_service] = lambda: build_taxonomy()
    try:
        with TestClient(app) as tc:
            yield tc
    finally:
        app.dependency_overrides.clear()
        app.router.on_startup[:] = startup_handlers


def test_alimenty_routes_to_sk(client: TestClient):
    r = client.post("/api/russia/search", json={"query": "алименты", "mode": "hybrid", "top_k": 5})
    assert r.status_code == 200
    d = r.json()
    assert d["taxonomy_applied"] is True
    assert "alimony_issue" in d["issue_flags"]
    assert d["results"], "expected taxonomy-guided results"
    assert all(item["law_id"] == "local:ru/sk" for item in d["results"])


def test_notice_routes_to_gpk_113(client: TestClient):
    r = client.post("/api/russia/search", json={"query": "без уведомления о заседании", "mode": "hybrid", "top_k": 5})
    assert r.status_code == 200
    d = r.json()
    assert d["taxonomy_applied"] is True
    assert "notice_issue" in d["issue_flags"]
    arts = {item["article_num"] for item in d["results"]}
    assert "113" in arts
    assert all(item["law_id"] == "local:ru/gpk" for item in d["results"])


def test_interpreter_routes_to_gpk_9_162(client: TestClient):
    r = client.post("/api/russia/search", json={"query": "без переводчика в суде", "mode": "hybrid", "top_k": 5})
    assert r.status_code == 200
    d = r.json()
    assert d["taxonomy_applied"] is True
    assert "interpreter_issue" in d["issue_flags"] or "language_issue" in d["issue_flags"]
    arts = {item["article_num"] for item in d["results"]}
    assert "9" in arts or "162" in arts
    assert all(item["law_id"] == "local:ru/gpk" for item in d["results"])


def test_language_query_excludes_unrelated_gpk_in_top3(client: TestClient):
    r = client.post(
        "/api/russia/search",
        json={"query": "я не понимал язык судебного заседания", "mode": "hybrid", "top_k": 5},
    )
    assert r.status_code == 200
    d = r.json()
    top3 = d["results"][:3]
    top3_articles = {x["article_num"] for x in top3}
    assert top3_articles & {"9", "162"}
    assert not (top3_articles & {"425", "427.3", "63.1"})


def test_notice_query_excludes_unrelated_articles_in_top3(client: TestClient):
    r = client.post(
        "/api/russia/search",
        json={"query": "я не был уведомлен о судебном заседании", "mode": "hybrid", "top_k": 5},
    )
    assert r.status_code == 200
    d = r.json()
    top3 = d["results"][:3]
    top3_articles = {x["article_num"] for x in top3}
    assert "113" in {x["article_num"] for x in d["results"]}
    assert not (top3_articles & {"10", "327.1", "279"})


def test_combined_notice_alimony_routes_to_sk_and_gpk_without_gk(client: TestClient):
    q = "суд взыскал алименты без моего участия и без уведомления"
    r = client.post("/api/russia/search", json={"query": q, "mode": "hybrid", "top_k": 6})
    assert r.status_code == 200
    d = r.json()
    laws = {x["law_id"] for x in d["results"]}
    assert "local:ru/sk" in laws
    assert "local:ru/gpk" in laws
    top3_articles = {x["article_num"] for x in d["results"][:3]}
    assert not (top3_articles & {"286", "274"})


@pytest.mark.parametrize(
    ("query", "expected_issue", "required_anchors", "allowed_top_laws"),
    [
        (
            "мне не предоставили переводчика в суде",
            "interpreter_issue",
            {("local:ru/gpk", "9"), ("local:ru/gpk", "162")},
            {"local:ru/gpk"},
        ),
        (
            "я не понимал язык судебного заседания",
            "language_issue",
            {("local:ru/gpk", "9")},
            {"local:ru/gpk"},
        ),
        (
            "я не был уведомлен о судебном заседании",
            "notice_issue",
            {("local:ru/gpk", "113")},
            {"local:ru/gpk"},
        ),
        (
            "повестка была отправлена на адрес регистрации где я не жил",
            "service_address_issue",
            {("local:ru/gpk", "113")},
            {"local:ru/gpk"},
        ),
        (
            "решение суда не было вручено",
            "notice_issue",
            {("local:ru/gpk", "113")},
            {"local:ru/gpk"},
        ),
        (
            "решение не перевели на мой язык",
            "language_issue",
            {("local:ru/gpk", "9"), ("local:ru/gpk", "162")},
            {"local:ru/gpk"},
        ),
        (
            "суд взыскал алименты без моего участия и без уведомления",
            "alimony_issue",
            {("local:ru/sk", "80"), ("local:ru/sk", "81"), ("local:ru/gpk", "113")},
            {"local:ru/sk", "local:ru/gpk"},
        ),
        (
            "приставы взыскивают задолженность по алиментам",
            "alimony_enforcement_issue",
            {("local:ru/sk", "113")},
            {"local:ru/sk"},
        ),
        (
            "я был там только как турист",
            "foreign_party_issue",
            {("local:ru/gpk", "9"), ("local:ru/gpk", "162")},
            {"local:ru/gpk"},
        ),
    ],
)
def test_supported_issue_queries_have_non_empty_anchor_results(
    client: TestClient,
    query: str,
    expected_issue: str,
    required_anchors: set[tuple[str, str]],
    allowed_top_laws: set[str],
):
    r = client.post("/api/russia/search", json={"query": query, "mode": "hybrid", "top_k": 5})
    assert r.status_code == 200
    d = r.json()
    assert expected_issue in d["issue_flags"]
    assert d["results"], "supported issue query must never return empty results"

    got = {(item["law_id"], item["article_num"]) for item in d["results"]}
    assert got & required_anchors, f"expected at least one guaranteed anchor in results for {query!r}"

    top3_laws = {item["law_id"] for item in d["results"][:3]}
    assert top3_laws <= allowed_top_laws

    # Dedup at article level: avoid duplicate chunks of the same article in top results.
    top_pairs = [(item["law_id"], item["article_num"]) for item in d["results"][:5]]
    assert len(top_pairs) == len(set(top_pairs))


def test_foreign_tourist_phrase_triggers_fallback_with_gpk_language_anchors(client: TestClient):
    r = client.post("/api/russia/search", json={"query": "я был там только как турист", "mode": "hybrid", "top_k": 5})
    assert r.status_code == 200
    d = r.json()
    assert "foreign_party_issue" in d["issue_flags"]
    assert d["results"], "foreign-party issue should still return deterministic anchor set"
    assert d["fallback_applied"] is True
    pairs = {(item["law_id"], item["article_num"]) for item in d["results"]}
    assert ("local:ru/gpk", "9") in pairs or ("local:ru/gpk", "162") in pairs


@pytest.mark.parametrize(
    ("query", "expected_issue", "required_anchor"),
    [
        ("мне не предоставили переводчика в суде", "interpreter_issue", ("local:ru/gpk", "9")),
        ("я не понимал язык судебного заседания", "language_issue", ("local:ru/gpk", "9")),
        ("я не был уведомлен о судебном заседании", "notice_issue", ("local:ru/gpk", "113")),
        ("повестка была отправлена на адрес регистрации где я не жил", "service_address_issue", ("local:ru/gpk", "113")),
        ("решение суда не было вручено", "notice_issue", ("local:ru/gpk", "113")),
        ("решение не перевели на мой язык", "language_issue", ("local:ru/gpk", "9")),
        ("суд взыскал алименты без моего участия и без уведомления", "alimony_issue", ("local:ru/sk", "80")),
        ("приставы взыскивают задолженность по алиментам", "alimony_enforcement_issue", ("local:ru/sk", "113")),
        ("я был там только как турист", "foreign_party_issue", ("local:ru/gpk", "9")),
    ],
)
def test_deterministic_anchor_injection_when_retrieval_returns_nothing(
    client_empty_retrieval: TestClient,
    query: str,
    expected_issue: str,
    required_anchor: tuple[str, str],
):
    r = client_empty_retrieval.post("/api/russia/search", json={"query": query, "mode": "hybrid", "top_k": 5})
    assert r.status_code == 200
    d = r.json()
    assert expected_issue in d["issue_flags"]
    assert d["results"], "supported issue must never be empty even when retrieval returns no chunks"
    assert d["fallback_applied"] is True
    assert d["fallback_reason"] in {
        "no_taxonomy_candidates",
        "retrieval_empty",
        "retrieval_below_threshold",
        "deterministic_anchor_injection",
    }
    pairs = {(item["law_id"], item["article_num"]) for item in d["results"]}
    assert required_anchor in pairs
    assert all(item.get("source") == "deterministic_anchor_fallback" for item in d["results"])
