"""
Contract tests for dedicated Russian HTTP routes.

Runs without Qdrant: `get_russian_retrieval_service` is overridden with a fake.
Integration tests with real data live in `test_russia_api.py` (Docker / CI with stack).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.dependencies import get_agent2_legal_strategy_service, get_russian_retrieval_service
from app.main import app
from app.modules.common.agents.agent2_legal_strategy.errors import Agent2OutputContractError
from app.modules.common.agents.agent2_legal_strategy.schemas import (
    LegalStrategyAgent2Output,
    MissingEvidenceBlock,
    StrategicAssessmentBlock,
)
from app.modules.russia.retrieval.schemas import (
    ArticleLookupResult,
    RussianChunkResult,
    RussianSearchResult,
)


def _chunk(**overrides) -> RussianChunkResult:
    base = dict(
        chunk_id="chunk-1",
        law_id="local:ru/gpk",
        law_short="ГПК РФ",
        article_num="9",
        article_heading="Тестовый заголовок",
        part_num=None,
        chunk_index=0,
        razdel=None,
        glava="1",
        text="Пример текста статьи с кириллицей.",
        fragment_id="local:ru/gpk/000009/0000",
        source_type="article",
        is_tombstone=False,
        source_file="gpk.txt",
    )
    base.update(overrides)
    return RussianChunkResult(**base)


def _search_hit(**overrides) -> RussianSearchResult:
    base = dict(
        score=0.9,
        chunk_id="s1",
        law_id="local:ru/gpk",
        law_short="ГПК РФ",
        article_num="9",
        article_heading="Ст. 9",
        part_num=None,
        chunk_index=0,
        razdel=None,
        glava="1",
        text="язык судопроизводства",
        fragment_id="f1",
        source_type="article",
        is_tombstone=False,
        source_file="gpk.txt",
    )
    base.update(overrides)
    return RussianSearchResult(**base)


class FakeRussianRetrievalService:
    """Deterministic stub for API layer contract tests."""

    def get_article(
        self,
        law_id: str,
        article_num: str,
        part_num: int | None = None,
    ) -> ArticleLookupResult:
        if article_num == "9999":
            return ArticleLookupResult(
                hit=False,
                law_id=law_id,
                article_num=article_num,
                chunks=[],
                is_tombstone=False,
                article_heading="",
            )
        if article_num == "7" and law_id == "local:ru/tk":
            ch = _chunk(
                law_id="local:ru/tk",
                law_short="ТК РФ",
                article_num="7",
                text="Утратила силу.",
                source_type="tombstone",
                is_tombstone=True,
            )
            return ArticleLookupResult(
                hit=True,
                law_id=law_id,
                article_num=article_num,
                chunks=[ch],
                is_tombstone=True,
                article_heading=ch.article_heading,
            )
        ch = _chunk(law_id=law_id, article_num=article_num)
        return ArticleLookupResult(
            hit=True,
            law_id=law_id,
            article_num=article_num,
            chunks=[ch],
            is_tombstone=False,
            article_heading=ch.article_heading,
        )

    def search(self, query: str, law_id: str | None = None, top_k: int = 10):
        return [_search_hit()]

    def sparse_search(self, query: str, law_id: str | None = None, top_k: int = 10):
        return [_search_hit(score=1.2)]

    def hybrid_search(self, query: str, law_id: str | None = None, top_k: int = 10, **_: object):
        return [_search_hit(score=0.85)]

    def topic_search(self, query: str, top_k: int = 10):
        return [_search_hit(score=0.7)]


class FakeAgent2Service:
    def run(self, inp, *, config=None):
        if inp.case_id == "bad":
            raise Agent2OutputContractError("bad citation", violations=["x"])

        class _RunResult:
            def __init__(self):
                self.output = LegalStrategyAgent2Output(
                    case_theory="Core procedural defects around language and notice.",
                    primary_legal_basis=[],
                    supporting_legal_basis=[],
                    fact_to_law_mapping=[],
                    strategic_assessment=StrategicAssessmentBlock(),
                    missing_evidence_gaps=MissingEvidenceBlock(),
                    recommended_next_steps=[],
                    draft_argument_direction="The case should argue procedural guarantees were violated.",
                    insufficient_support_items=[],
                )

        return _RunResult()


@pytest.fixture
def client():
    startup_handlers = list(app.router.on_startup)
    app.router.on_startup.clear()
    app.dependency_overrides[get_russian_retrieval_service] = lambda: FakeRussianRetrievalService()
    app.dependency_overrides[get_agent2_legal_strategy_service] = lambda: FakeAgent2Service()
    try:
        with TestClient(app) as tc:
            yield tc
    finally:
        app.dependency_overrides.clear()
        app.router.on_startup[:] = startup_handlers


def test_get_article_hit_returns_json(client: TestClient):
    r = client.get(
        "/api/russia/article",
        params={"law_id": "local:ru/gpk", "article_num": "9"},
    )
    assert r.status_code == 200
    d = r.json()
    assert d["hit"] is True
    assert d["law_id"] == "local:ru/gpk"
    assert d["article_num"] == "9"
    assert len(d["chunks"]) == 1
    assert "кириллицей" in d["chunks"][0]["text"]


def test_get_article_no_hit_200_empty_chunks(client: TestClient):
    """Documented behavior: unknown article returns HTTP 200, hit=false, empty chunks."""
    r = client.get(
        "/api/russia/article",
        params={"law_id": "local:ru/gpk", "article_num": "9999"},
    )
    assert r.status_code == 200
    d = r.json()
    assert d["hit"] is False
    assert d["chunks"] == []


def test_get_article_tombstone_flags(client: TestClient):
    r = client.get(
        "/api/russia/article",
        params={"law_id": "local:ru/tk", "article_num": "7"},
    )
    assert r.status_code == 200
    d = r.json()
    assert d["hit"] is True
    assert d["is_tombstone"] is True
    assert d["chunks"][0]["is_tombstone"] is True


def test_post_search_cyrillic_query_echoed(client: TestClient):
    q = "переводчик в гражданском процессе"
    r = client.post("/api/russia/search", json={"query": q, "mode": "hybrid"})
    assert r.status_code == 200
    d = r.json()
    assert d["query"] == q
    assert d["mode"] == "hybrid"
    assert d["result_count"] == 1
    assert "язык" in d["results"][0]["text"]


def test_post_search_modes(client: TestClient):
    for mode in ("dense", "sparse", "topic", "hybrid"):
        r = client.post(
            "/api/russia/search",
            json={"query": "тест", "mode": mode, "top_k": 3},
        )
        assert r.status_code == 200
        assert r.json()["mode"] == mode


def test_post_search_law_filter_echoed(client: TestClient):
    r = client.post(
        "/api/russia/search",
        json={"query": "тест", "law_id": "local:ru/gpk", "mode": "dense"},
    )
    assert r.status_code == 200
    assert r.json()["law_id"] == "local:ru/gpk"


def test_openapi_includes_russia_paths_and_tags(client: TestClient):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json().get("paths", {})
    assert "/api/russia/article" in paths
    assert "/api/russia/search" in paths
    assert "/api/russia/interpreter-issue" in paths
    assert "/api/russia/strategy" in paths
    tags = paths["/api/russia/article"]["get"].get("tags", [])
    assert "russia" in tags


def test_post_strategy_returns_agent2_output(client: TestClient):
    payload = {
        "input": {
            "case_id": "C-1",
            "jurisdiction": "Russia",
            "cleaned_summary": "No interpreter and no notice.",
            "facts": ["Foreign citizen", "No interpreter"],
            "issue_flags": ["interpreter_issue", "notice_issue"],
            "claims_or_questions": ["Build defense strategy."],
            "legal_evidence_pack": {
                "primary_sources": [{"law": "GPK RF", "article": "9"}],
                "supporting_sources": [{"law": "ECHR", "article": "6"}],
                "retrieved_articles": [{"law": "GPK RF", "article": "9", "excerpt": "Proceedings in Russian"}],
                "matched_issues": ["interpreter_issue"],
                "retrieval_notes": ["test"],
            },
        },
        "strict_reliability": True,
        "max_repair_attempts": 1,
    }
    r = client.post("/api/russia/strategy", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert "output" in data
    assert data["output"]["case_theory"]
    assert data["output"]["draft_argument_direction"]


def test_post_strategy_contract_error_returns_422(client: TestClient):
    payload = {
        "input": {
            "case_id": "bad",
            "jurisdiction": "Russia",
            "cleaned_summary": "x",
            "legal_evidence_pack": {
                "primary_sources": [],
                "supporting_sources": [],
                "retrieved_articles": [],
                "matched_issues": [],
                "retrieval_notes": [],
            },
        }
    }
    r = client.post("/api/russia/strategy", json=payload)
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["code"] == "agent2_output_contract_violation"
