"""
Dedicated Russian law API endpoints.

Completely separate from the Czech pipeline.
No routing through Czech collection or Czech retrieval logic.

Endpoints
---------
GET  /russia/article          — exact article lookup by law_id + article_num
POST /russia/search           — hybrid/dense/sparse/topic retrieval
POST /russia/interpreter-issue — case-text-to-evidence bridge (interpreter/language/notice)

All endpoints:
  - accept and return UTF-8 / Cyrillic text natively
  - call only the verified Russian retrieval stack (russian_laws_v1 collection)
  - perform no LLM synthesis
  - contain no agent logic

Encoding note for callers
--------------------------
curl:
    curl -X POST http://localhost:8032/api/russia/search \\
         -H "Content-Type: application/json" \\
         -d '{"query":"язык судопроизводства"}'

PowerShell (5.x / 7.x) — prefer a hashtable piped to ConvertTo-Json (Cyrillic preserved;
avoid raw string -Body with Cyrillic on PS 5.x, and avoid byte[] -Body which can trigger
chunked encoding issues):
    $body = @{ query = "переводчик в гражданском процессе" } | ConvertTo-Json -Compress
    Invoke-RestMethod -Uri http://localhost:8032/api/russia/search \\
        -Method POST -ContentType "application/json; charset=utf-8" -Body $body
"""
from __future__ import annotations

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.dependencies import (
    get_agent2_legal_strategy_service,
    get_russia_focus_taxonomy_service,
    get_russian_retrieval_service,
)
from app.modules.common.agents.agent2_legal_strategy.errors import Agent2Error
from app.modules.common.agents.agent2_legal_strategy.input_schemas import LegalStrategyAgent2Input
from app.modules.common.agents.agent2_legal_strategy.schemas import LegalStrategyAgent2Output
from app.modules.common.agents.agent2_legal_strategy.service import Agent2RunConfig
from app.modules.common.legal_taxonomy.service import FocusLegalTaxonomyService
from app.modules.russia.retrieval.taxonomy_first import taxonomy_first_search

log = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Dependency alias
# ---------------------------------------------------------------------------

def _svc(
    svc=Depends(get_russian_retrieval_service),
):
    return svc


def _taxonomy(
    tx=Depends(get_russia_focus_taxonomy_service),
):
    return tx


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class ArticleChunkOut(BaseModel):
    chunk_id: str
    law_id: str
    law_short: str
    article_num: str | None
    article_heading: str | None
    part_num: int | None
    chunk_index: int
    text: str
    is_tombstone: bool
    fragment_id: str

    model_config = {"from_attributes": True}


class ArticleLookupOut(BaseModel):
    """
    Response for GET /russia/article.

    hit=False means the article was not found in the collection at all.
    hit=True + is_tombstone=True means the article was repealed.
    hit=True + is_tombstone=False is a normal result.
    """

    hit: bool
    law_id: str
    article_num: str
    article_heading: str | None
    is_tombstone: bool
    chunks: list[ArticleChunkOut]

    model_config = {"from_attributes": True}


class SearchResultOut(BaseModel):
    score: float
    chunk_id: str
    law_id: str
    law_short: str
    article_num: str | None
    article_heading: str | None
    text: str
    is_tombstone: bool
    source: str | None = None

    model_config = {"from_attributes": True}


class SearchOut(BaseModel):
    query: str
    law_id: str | None
    mode: str
    issue_flags: list[str] = []
    taxonomy_applied: bool = False
    fallback_applied: bool = False
    fallback_reason: str | None = None
    result_count: int
    results: list[SearchResultOut]


class IssueEvidenceOut(BaseModel):
    score: float
    chunk_id: str
    law_id: str
    law_short: str
    article_num: str | None
    article_heading: str | None
    text: str
    is_tombstone: bool
    source_role: str

    model_config = {"from_attributes": True}


class InterpreterIssueOut(BaseModel):
    """
    Response for POST /russia/interpreter-issue.

    is_matched=False means the case description did not contain enough
    interpreter/language/notice signals (no results returned).
    """

    case_text: str
    is_matched: bool
    detected_issue: str | None
    detected_subissues: list[str]
    matched_signals: dict[str, list[str]]
    normalized_queries: list[str]
    primary_results: list[IssueEvidenceOut]
    supporting_results: list[IssueEvidenceOut]
    combined_results: list[IssueEvidenceOut]


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

SearchMode = Literal["hybrid", "dense", "sparse", "topic"]


class SearchRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        examples=["переводчик в гражданском процессе"],
        description="Search query in Russian",
    )
    law_id: str | None = Field(
        default=None,
        examples=["local:ru/gpk"],
        description="Optional law filter. E.g. local:ru/gpk, local:ru/echr, local:ru/fl115",
    )
    top_k: int = Field(default=5, ge=1, le=25)
    mode: SearchMode = Field(
        default="hybrid",
        description="Retrieval mode: hybrid (default) | dense | sparse | topic",
    )


class InterpreterIssueRequest(BaseModel):
    case_text: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        examples=["иностранный гражданин не получил переводчика в суде"],
        description=(
            "Short natural-language case description in Russian. "
            "Covers interpreter, language-of-proceedings, and notice/summons issues."
        ),
    )
    top_k_primary: int = Field(default=8, ge=1, le=20)
    top_k_support: int = Field(default=3, ge=0, le=10)


class StrategyRequest(BaseModel):
    input: LegalStrategyAgent2Input
    strict_reliability: bool = Field(
        default=True,
        description="Disallow unsupported legal conclusions when evidence is thin.",
    )
    max_repair_attempts: int = Field(
        default=1,
        ge=0,
        le=2,
        description="How many contract-repair retries are allowed after invalid citation output.",
    )


class StrategyOut(BaseModel):
    output: LegalStrategyAgent2Output


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chunk_to_out(chunk) -> ArticleChunkOut:
    return ArticleChunkOut(
        chunk_id=chunk.chunk_id,
        law_id=chunk.law_id,
        law_short=chunk.law_short,
        article_num=chunk.article_num,
        article_heading=chunk.article_heading,
        part_num=chunk.part_num,
        chunk_index=chunk.chunk_index,
        text=chunk.text,
        is_tombstone=chunk.is_tombstone,
        fragment_id=chunk.fragment_id,
    )


def _result_to_out(r) -> SearchResultOut:
    return SearchResultOut(
        score=r.score,
        chunk_id=r.chunk_id,
        law_id=r.law_id,
        law_short=r.law_short,
        article_num=r.article_num,
        article_heading=r.article_heading,
        text=r.text,
        is_tombstone=r.is_tombstone,
        source=getattr(r, "source_type", None),
    )


def _evidence_to_out(e) -> IssueEvidenceOut:
    return IssueEvidenceOut(
        score=e.score,
        chunk_id=e.chunk_id,
        law_id=e.law_id,
        law_short=e.law_short,
        article_num=e.article_num,
        article_heading=e.article_heading,
        text=e.text,
        is_tombstone=e.is_tombstone,
        source_role=e.source_role,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/russia/article",
    response_model=ArticleLookupOut,
    summary="Exact Russian law article lookup",
    description=(
        "Look up a Russian law article by law_id and article number. "
        "Returns the full article text split into chunks. "
        "Tombstone articles (repealed) are returned with is_tombstone=True. "
        "Returns hit=False (HTTP 200) when the article is not found — not a 404."
    ),
    tags=["russia"],
)
def get_article(
    law_id: Annotated[
        str,
        Query(
            description="Law identifier. E.g. local:ru/gpk, local:ru/sk, local:ru/tk, local:ru/echr, local:ru/fl115",
            examples=["local:ru/gpk"],
        ),
    ],
    article_num: Annotated[
        str,
        Query(
            description="Article number as a string. E.g. '9', '162', '113', '19.1'",
            examples=["9"],
        ),
    ],
    part_num: Annotated[
        int | None,
        Query(description="Optional part (paragraph) number within the article"),
    ] = None,
    svc=Depends(_svc),
) -> ArticleLookupOut:
    log.debug("russia.article law_id=%r article_num=%r", law_id, article_num)
    result = svc.get_article(law_id, article_num, part_num)
    return ArticleLookupOut(
        hit=result.hit,
        law_id=result.law_id,
        article_num=result.article_num,
        article_heading=result.article_heading,
        is_tombstone=result.is_tombstone,
        chunks=[_chunk_to_out(c) for c in result.chunks],
    )


@router.post(
    "/russia/search",
    response_model=SearchOut,
    summary="Russian law full-text and semantic search",
    description=(
        "Search Russian law corpus using hybrid (BM25 + dense), dense-only, "
        "sparse-only, or topic-aware retrieval. "
        "Optionally restrict to a single law with law_id. "
        "Accepts Cyrillic queries natively."
    ),
    tags=["russia"],
)
def search(
    request: SearchRequest,
    svc=Depends(_svc),
    taxonomy: FocusLegalTaxonomyService = Depends(_taxonomy),
) -> SearchOut:
    log.debug(
        "russia.search mode=%r law_id=%r query=%r",
        request.mode, request.law_id, request.query[:60],
    )

    outcome = taxonomy_first_search(
        svc=svc,
        taxonomy=taxonomy,
        mode=request.mode,
        query=request.query,
        top_k=request.top_k,
        law_id=request.law_id,
    )
    raw = outcome.results

    return SearchOut(
        query=request.query,
        law_id=request.law_id,
        mode=request.mode,
        issue_flags=outcome.issue_flags,
        taxonomy_applied=outcome.taxonomy_applied,
        fallback_applied=outcome.fallback_applied,
        fallback_reason=outcome.fallback_reason,
        result_count=len(raw),
        results=[_result_to_out(r) for r in raw],
    )


@router.post(
    "/russia/interpreter-issue",
    response_model=InterpreterIssueOut,
    summary="Interpreter / language / notice issue bridge",
    description=(
        "Analyze a case description for interpreter, language-of-proceedings, "
        "and notice/summons issues in Russian civil proceedings (ГПК РФ ст. 9, 162, 113). "
        "Returns structured GPK primary evidence + ECHR/FL-115 supporting evidence. "
        "is_matched=False if the description contains no relevant signals."
    ),
    tags=["russia"],
)
def interpreter_issue(
    request: InterpreterIssueRequest,
    svc=Depends(_svc),
) -> InterpreterIssueOut:
    from app.modules.russia.retrieval.case_bridge import CaseIssueBridge

    log.debug("russia.interpreter_issue case_text=%r", request.case_text[:80])
    bridge = CaseIssueBridge(svc)
    result = bridge.analyze(
        request.case_text,
        top_k_primary=request.top_k_primary,
        top_k_support=request.top_k_support,
    )
    return InterpreterIssueOut(
        case_text=result.case_text,
        is_matched=result.is_matched,
        detected_issue=result.detected_issue,
        detected_subissues=result.detected_subissues,
        matched_signals=result.matched_signals,
        normalized_queries=result.normalized_queries,
        primary_results=[_evidence_to_out(e) for e in result.primary_results],
        supporting_results=[_evidence_to_out(e) for e in result.supporting_results],
        combined_results=[_evidence_to_out(e) for e in result.combined_results],
    )


@router.post(
    "/russia/strategy",
    response_model=StrategyOut,
    summary="Agent 2 legal strategy from evidence pack",
    description=(
        "Runs Agent 2 over a closed evidence pack. "
        "Does not perform retrieval and does not allow legal citations outside the pack."
    ),
    tags=["russia"],
)
def strategy(
    request: StrategyRequest,
    agent2=Depends(get_agent2_legal_strategy_service),
) -> StrategyOut:
    try:
        run_result = agent2.run(
            request.input,
            config=Agent2RunConfig(
                strict_reliability=request.strict_reliability,
                max_repair_attempts=request.max_repair_attempts,
            ),
        )
    except Agent2Error as exc:
        # Controlled failure path: keep API deterministic and avoid leaking internals.
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc)}) from exc
    return StrategyOut(output=run_result.output)
