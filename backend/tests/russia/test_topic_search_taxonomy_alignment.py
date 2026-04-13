"""Ensure RussianRetrievalService.topic_search aligns with /api/russia/search taxonomy routing."""
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
from app.modules.russia.retrieval.query_analyzer import RussianQueryAnalyzer
from app.modules.russia.retrieval.retrieval_planner import RussianRetrievalPlanner
from app.modules.russia.retrieval.schemas import ArticleLookupResult, RussianSearchResult
from app.modules.russia.retrieval.service import RussianRetrievalService


def _result(*, law_id: str, article: str, score: float = 0.5) -> RussianSearchResult:
    return RussianSearchResult(
        score=score,
        chunk_id=f"{law_id}:{article}",
        law_id=law_id,
        law_short="TEST",
        article_num=article,
        article_heading="h",
        part_num=None,
        chunk_index=0,
        razdel=None,
        glava="",
        text=f"{law_id}:{article}",
        fragment_id=f"{law_id}/{article}/0",
        source_type="article",
        is_tombstone=False,
        source_file="x",
    )


class _FakeDense:
    def __init__(self, db: dict[str, list[RussianSearchResult]]) -> None:
        self._db = db

    def search(self, query: str, law_id: str | None = None, top_k: int = 10):
        if law_id is None:
            rows = self._db["local:ru/gk/1"] + self._db["local:ru/sk"] + self._db["local:ru/gpk"]
            return rows[:top_k]
        return self._db.get(law_id, [])[:top_k]


class _FakeSparse(_FakeDense):
    def search(self, query: str, law_id: str | None = None, top_k: int = 10):
        base = super().search(query, law_id=law_id, top_k=top_k)
        return [replace(r, score=r.score + 0.03) for r in base]


class _FakeExact:
    def get_article(self, law_id: str, article_num: str, part_num=None):
        return ArticleLookupResult(
            hit=False,
            law_id=law_id,
            article_num=article_num,
            chunks=[],
            is_tombstone=False,
            article_heading="",
        )


def _build_fake_service() -> RussianRetrievalService:
    db = {
        "local:ru/sk": [_result(law_id="local:ru/sk", article="80"), _result(law_id="local:ru/sk", article="81", score=0.48)],
        "local:ru/gpk": [
            _result(law_id="local:ru/gpk", article="113", score=0.46),
            _result(law_id="local:ru/gpk", article="9", score=0.41),
            _result(law_id="local:ru/gpk", article="162", score=0.40),
            _result(law_id="local:ru/gpk", article="10", score=0.99),
            _result(law_id="local:ru/gpk", article="327.1", score=0.98),
            _result(law_id="local:ru/gpk", article="425", score=0.97),
            _result(law_id="local:ru/gpk", article="427.3", score=0.96),
            _result(law_id="local:ru/gpk", article="63.1", score=0.95),
        ],
        "local:ru/gk/1": [
            _result(law_id="local:ru/gk/1", article="260", score=0.95),
            _result(law_id="local:ru/gk/1", article="279", score=0.94),
            _result(law_id="local:ru/gk/1", article="286", score=0.93),
            _result(law_id="local:ru/gk/1", article="274", score=0.92),
        ],
        "local:ru/echr": [_result(law_id="local:ru/echr", article="6", score=0.2)],
    }
    svc = RussianRetrievalService.__new__(RussianRetrievalService)
    svc._exact = _FakeExact()
    svc._dense = _FakeDense(db)
    svc._sparse = _FakeSparse(db)
    svc._analyzer = RussianQueryAnalyzer()
    svc._planner = RussianRetrievalPlanner()
    svc._taxonomy = build_taxonomy()
    return svc


@pytest.fixture
def fake_service() -> RussianRetrievalService:
    return _build_fake_service()


@pytest.fixture
def client(fake_service: RussianRetrievalService):
    startup_handlers = list(app.router.on_startup)
    app.router.on_startup.clear()
    app.dependency_overrides[get_russian_retrieval_service] = lambda: fake_service
    app.dependency_overrides[get_russia_focus_taxonomy_service] = lambda: build_taxonomy()
    try:
        with TestClient(app) as tc:
            yield tc
    finally:
        app.dependency_overrides.clear()
        app.router.on_startup[:] = startup_handlers


def _compare_alignment(query: str, fake_service: RussianRetrievalService, client: TestClient):
    svc_rows = fake_service.topic_search(query, top_k=5)
    api = client.post("/api/russia/search", json={"query": query, "mode": "topic", "top_k": 5})
    assert api.status_code == 200
    api_rows = api.json()["results"]
    assert svc_rows and api_rows
    svc_pairs = [(r.law_id, r.article_num) for r in svc_rows]
    api_pairs = [(r["law_id"], r["article_num"]) for r in api_rows]
    assert svc_pairs[0] == api_pairs[0]
    assert {p[0] for p in svc_pairs} == {p[0] for p in api_pairs}


def _compare_non_topic_alignment(query: str, mode: str, fake_service: RussianRetrievalService, client: TestClient):
    if mode == "hybrid":
        svc_rows = fake_service.hybrid_search(query, top_k=5)
    elif mode == "dense":
        svc_rows = fake_service.search(query, top_k=5)
    else:
        svc_rows = fake_service.sparse_search(query, top_k=5)

    api = client.post("/api/russia/search", json={"query": query, "mode": mode, "top_k": 5})
    assert api.status_code == 200
    api_rows = api.json()["results"]
    assert svc_rows and api_rows
    svc_pairs = [(r.law_id, r.article_num) for r in svc_rows]
    api_pairs = [(r["law_id"], r["article_num"]) for r in api_rows]
    assert svc_pairs[0] == api_pairs[0]
    assert {p[0] for p in svc_pairs} == {p[0] for p in api_pairs}


def test_alignment_alimenty(fake_service: RussianRetrievalService, client: TestClient):
    _compare_alignment("алименты", fake_service, client)


def test_alignment_notice(fake_service: RussianRetrievalService, client: TestClient):
    _compare_alignment("без уведомления", fake_service, client)


def test_alignment_interpreter(fake_service: RussianRetrievalService, client: TestClient):
    _compare_alignment("без переводчика", fake_service, client)


@pytest.mark.parametrize("query", ["алименты", "без уведомления", "без переводчика"])
@pytest.mark.parametrize("mode", ["hybrid", "dense", "sparse"])
def test_non_topic_paths_align_with_api(
    query: str,
    mode: str,
    fake_service: RussianRetrievalService,
    client: TestClient,
):
    _compare_non_topic_alignment(query, mode, fake_service, client)


def test_service_non_topic_language_excludes_unrelated_gpk(fake_service: RussianRetrievalService):
    rows = fake_service.hybrid_search("я не понимал язык судебного заседания", top_k=5)
    top3 = {r.article_num for r in rows[:3]}
    assert top3 & {"9", "162"}
    assert not (top3 & {"425", "427.3", "63.1"})


def test_service_non_topic_notice_excludes_unrelated(fake_service: RussianRetrievalService):
    rows = fake_service.hybrid_search("я не был уведомлен о судебном заседании", top_k=5)
    top3 = {r.article_num for r in rows[:3]}
    assert "113" in {r.article_num for r in rows}
    assert not (top3 & {"10", "327.1", "279"})


def test_service_non_topic_combined_notice_alimony(fake_service: RussianRetrievalService):
    rows = fake_service.hybrid_search(
        "суд взыскал алименты без моего участия и без уведомления",
        top_k=6,
    )
    laws = {r.law_id for r in rows}
    assert "local:ru/sk" in laws
    assert "local:ru/gpk" in laws
    top3 = {r.article_num for r in rows[:3]}
    assert not (top3 & {"286", "274"})
