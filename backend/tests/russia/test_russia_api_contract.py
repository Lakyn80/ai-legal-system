"""
Contract tests for dedicated Russian HTTP routes.

Runs without Qdrant: `get_russian_retrieval_service` is overridden with a fake.
Integration tests with real data live in `test_russia_api.py` (Docker / CI with stack).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.dependencies import (
    get_agent2_legal_strategy_service,
    get_russian_case_reconstruction_service,
    get_russian_retrieval_service,
)
from app.main import app
from app.modules.common.agents.agent2_legal_strategy.errors import Agent2OutputContractError
from app.modules.common.agents.agent2_legal_strategy.extraction_schemas import LegalExtractionAgent2Output
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

    def run_extraction(self, inp, *, config=None):
        class _RunResult:
            def __init__(self):
                self.output = LegalExtractionAgent2Output.model_validate({
                    "schema_version": "agent2_legal_extraction.v1",
                    "case_id": inp.case_id,
                    "source_artifact": "",
                    "groups": [
                        {
                            "group_id": f"case::{inp.case_id}::group::judgments",
                            "group_name": "judgments",
                            "documents": [
                                {
                                    "doc_id": f"case::{inp.case_id}::doc::0",
                                    "logical_index": 0,
                                    "primary_document_id": "judgment-1",
                                    "document_type": "judgment",
                                    "document_date": "2026-04-01",
                                    "document_role": "court",
                                    "title": "Judgment",
                                    "is_core_document": True,
                                    "source_pages": ["p.1-4"],
                                    "full_text_reference": "blob://judgment-1",
                                    "summary": "Court judgment content.",
                                    "key_points": ["Notice issue discussed."],
                                    "evidence_value": "Core procedural source.",
                                    "procedural_value": "Appeal basis.",
                                }
                            ],
                        }
                    ],
                    "issues": [
                        {
                            "issue_id": f"case::{inp.case_id}::issue::notice_issue",
                            "issue_slug": "notice_issue",
                            "issue_title": "Notice Issue",
                            "factual_basis": ["No proper notice."],
                            "supporting_doc_ids": [f"case::{inp.case_id}::doc::0"],
                            "court_or_opponent_position": "",
                            "problem_description": "Notice defect alleged.",
                            "defense_argument": "Proceedings should be re-opened.",
                            "legal_basis": [],
                            "requested_consequence": "Set aside judgment.",
                            "evidence_gaps": [],
                        }
                    ],
                    "defense_blocks": [
                        {
                            "defense_id": f"case::{inp.case_id}::defense::notice_issue",
                            "issue_id": f"case::{inp.case_id}::issue::notice_issue",
                            "title": "Defense: Notice Issue",
                            "argument_markdown": "Detailed argument.",
                            "supporting_doc_ids": [f"case::{inp.case_id}::doc::0"],
                            "legal_basis_refs": [],
                        }
                    ],
                })

        return _RunResult()


class FakeCaseReconstructionService:
    def reconstruct_case_documents(self, case_id: str):
        from app.modules.common.agents.agent2_legal_strategy.input_schemas import CaseDocumentInput

        if case_id == "missing":
            raise ValueError("No chunks found for case")
        return [
            CaseDocumentInput(
                primary_document_id="doc-1",
                document_type="judgment",
                document_date="2026-04-01",
                document_role="court",
                title="Judgment",
                content="Full reconstructed text for case.",
                source_pages=["p.1", "p.2"],
                full_text_reference="qdrant://legal_case_chunks_ru_clean/C-CASE/doc-1",
            )
        ]

    def build_evidence_pack_from_chunks(self, case_id: str):
        from app.modules.common.agents.agent2_legal_strategy.input_schemas import LegalEvidencePack
        from app.modules.common.agents.agent2_legal_strategy.schemas import SourceRef

        return LegalEvidencePack(
            primary_sources=[SourceRef(law="GPK RF", article="113")],
            supporting_sources=[],
            retrieved_articles=[],
            matched_issues=[],
            retrieval_notes=["fake_reconstruction"],
        )


@pytest.fixture
def client():
    startup_handlers = list(app.router.on_startup)
    app.router.on_startup.clear()
    app.dependency_overrides[get_russian_retrieval_service] = lambda: FakeRussianRetrievalService()
    app.dependency_overrides[get_agent2_legal_strategy_service] = lambda: FakeAgent2Service()
    app.dependency_overrides[get_russian_case_reconstruction_service] = lambda: FakeCaseReconstructionService()
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
    r = client.post("/api/russia/search", json={"query": q, "mode": "hybrid", "top_k": 1})
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


def test_post_strategy_extraction_returns_grouped_output(client: TestClient):
    payload = {
        "input": {
            "case_id": "C-EX1",
            "jurisdiction": "Russia",
            "cleaned_summary": "Service and notice defects.",
            "facts": ["No notice", "Late awareness"],
            "issue_flags": ["notice_issue"],
            "claims_or_questions": ["Build extraction."],
            "legal_evidence_pack": {
                "primary_sources": [{"law": "GPK RF", "article": "113"}],
                "supporting_sources": [],
                "retrieved_articles": [{"law": "GPK RF", "article": "113", "excerpt": "Notice"}],
                "matched_issues": ["notice_issue"],
                "retrieval_notes": ["test"],
            },
            "case_documents": [
                {
                    "primary_document_id": "judgment-1",
                    "document_type": "judgment",
                    "document_date": "2026-04-01",
                    "document_role": "court",
                    "title": "Judgment",
                    "content": "Full document text",
                    "source_pages": ["p.1-4"],
                    "full_text_reference": "blob://judgment-1",
                }
            ],
        }
    }
    r = client.post("/api/russia/strategy/extraction", json=payload)
    assert r.status_code == 200
    data = r.json()["output"]
    assert data["schema_version"] == "agent2_legal_extraction.v1"
    assert data["groups"][0]["group_id"] == "case::C-EX1::group::judgments"
    assert data["groups"][0]["documents"][0]["doc_id"] == "case::C-EX1::doc::0"


def test_post_strategy_extraction_from_case_works(client: TestClient):
    payload = {
        "case_id": "C-CASE",
        "jurisdiction": "Russia",
        "issue_flags": ["notice_issue"],
        "claims_or_questions": ["Build extraction from reconstructed docs."],
    }
    r = client.post("/api/russia/strategy/extraction/from-case", json=payload)
    assert r.status_code == 200
    out = r.json()["output"]
    assert out["schema_version"] == "agent2_legal_extraction.v1"
    assert out["case_id"] == "C-CASE"


def test_post_strategy_extraction_from_case_missing_returns_422(client: TestClient):
    payload = {"case_id": "missing"}
    r = client.post("/api/russia/strategy/extraction/from-case", json=payload)
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["code"] == "case_reconstruction_failed"
