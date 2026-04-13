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
            "local:ru/sk": [_result(law_id="local:ru/sk", article="80", score=0.4), _result(law_id="local:ru/sk", article="81", score=0.35)],
            "local:ru/gpk": [
                _result(law_id="local:ru/gpk", article="113", score=0.45),
                _result(law_id="local:ru/gpk", article="9", score=0.2),
                _result(law_id="local:ru/gpk", article="162", score=0.21),
            ],
            "local:ru/echr": [_result(law_id="local:ru/echr", article="6", score=0.1)],
            "local:ru/gk/1": [_result(law_id="local:ru/gk/1", article="260", score=0.9)],
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
