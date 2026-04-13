from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor

from app.core.enums import CountryEnum, DomainEnum
from app.modules.common.query_parser import parse_query
from app.modules.common.embeddings.provider import EmbeddingService
from app.modules.common.qdrant.schemas import SearchRequest, SearchResultItem
from app.modules.czechia.retrieval.ambiguity_handler import AmbiguityResult, CzechAmbiguityHandler
from app.modules.czechia.retrieval.cross_encoder_reranker import rerank as cross_encoder_rerank
from app.modules.czechia.retrieval.dense_retriever import CzechLawDenseRetriever
from app.modules.czechia.retrieval.evidence_validator import CzechLawEvidenceValidator
from app.modules.czechia.retrieval.fusion import rrf_fuse
from app.modules.czechia.retrieval.labor_gate import LaborGate
from app.modules.czechia.retrieval.query_analyzer import CzechQueryAnalyzer
from app.modules.czechia.retrieval.reranker import CzechLawReranker, diversify_by_paragraph
from app.modules.czechia.retrieval.retrieval_planner import CzechLawRetrievalPlanner
from app.modules.czechia.retrieval.schemas import CandidateBatch, EvidencePack, EvidencePackItem, QueryUnderstanding, RetrievalPlan
from app.modules.czechia.retrieval.sparse_retriever import CzechLawSparseRetriever
from app.modules.czechia.retrieval.text_utils import overlap_ratio, parse_law_iri, pick_primary_paragraph

log = logging.getLogger(__name__)


class CzechLawRetrievalService:
    def __init__(
        self,
        embedding_service: EmbeddingService,
        dense_retriever: CzechLawDenseRetriever,
        labor_gate: LaborGate | None = None,
    ) -> None:
        self._embedding = embedding_service
        self._dense = dense_retriever
        self._sparse = CzechLawSparseRetriever(
            url=dense_retriever.url,
            api_key=dense_retriever.api_key,
        )
        self._analyzer = CzechQueryAnalyzer()
        self._labor_gate = labor_gate or LaborGate(self._analyzer)
        self._ambiguity_handler = CzechAmbiguityHandler()
        self._planner = CzechLawRetrievalPlanner()
        self._reranker = CzechLawReranker()
        self._validator = CzechLawEvidenceValidator()

    def search(self, request: SearchRequest) -> list[SearchResultItem]:
        query = request.query.strip()
        if not query:
            return []

        parsed = parse_query(query)
        has_keywords = any(
            keyword in parsed["normalized_query"]
            for keyword in ["výpověď", "zaměstnavatel", "smlouva", "pracovní"]
        )
        is_paragraph_only = parsed["paragraph"] is not None and not parsed["law_id"]

        # Run full analysis first so we can check for law refs detected by the analyzer
        # (e.g. "zákon o daních z příjmů" not in simple parser's alias map)
        understanding = self._analyzer.analyze(parsed["normalized_query"])
        gate_decision = self._labor_gate.evaluate(
            request.query,
            understanding=understanding,
        )
        if not gate_decision.allows_retrieval:
            log.info(
                "czech labor gate blocked query bucket=%s reasons=%s query=%r",
                gate_decision.bucket,
                gate_decision.reason_codes,
                query,
            )
            return [gate_decision.to_search_result()]

        if is_paragraph_only and not has_keywords and not understanding.detected_law_refs:
            ambiguity = self._ambiguity_handler.evaluate(
                query=parsed["normalized_query"],
                paragraph=parsed["paragraph"],
                law_id=parsed["law_id"],
                has_context=bool(request.document_ids),
                context_law_hint=request.document_ids[0] if request.document_ids else None,
            )
            if ambiguity is not None and ambiguity.needs_clarification:
                log.info(
                    "czech ambiguity detected: paragraph=%s has_context=%s context_law_hint=%s",
                    parsed["paragraph"],
                    bool(request.document_ids),
                    request.document_ids[0] if request.document_ids else None,
                )
                return self._build_ambiguity_results(ambiguity, request.top_k)
        plan = self._planner.build(
            understanding=understanding,
            top_k=request.top_k,
            document_ids=request.document_ids,
            forced_paragraph=parsed["paragraph"],
            forced_law=parsed["law_id"],
        )
        evidence_pack = self._execute_plan(query=parsed["normalized_query"], understanding=understanding, plan=plan)
        validation = self._validator.validate(
            evidence_pack=evidence_pack,
            understanding=understanding,
            plan=plan,
            top_k=request.top_k,
        )

        if validation.should_broaden:
            broadened_plan = self._planner.broaden(plan=plan, understanding=understanding, top_k=request.top_k)
            broadened_pack = self._execute_plan(
                query=query,
                understanding=understanding,
                plan=broadened_plan,
            )
            validation = self._validator.validate(
                evidence_pack=broadened_pack,
                understanding=understanding,
                plan=broadened_plan,
                top_k=request.top_k,
            )

        ranked_items = validation.evidence_pack.items
        is_topic_mode = plan.mode != "exact"
        if is_topic_mode:
            ranked_items = cross_encoder_rerank(
                query=parsed["normalized_query"],
                items=ranked_items,
                top_n=10,
            )
            # Paragraph diversification: for topic/domain queries ensure coverage
            # across different paragraphs (max 2 chunks per paragraph) so the
            # answer draws from several relevant sections rather than repeating
            # one paragraph's sub-items.
            ranked_items = diversify_by_paragraph(
                items=ranked_items,
                top_k=request.top_k * 3,  # diversify over a larger pool, trim later
                max_per_paragraph=2,
            )

        items = ranked_items[: request.top_k]
        items = self._apply_keyword_boost(
            items=items,
            query_text=parsed["normalized_query"],
            is_exact=(plan.mode == "exact"),
        )

        # ── confidence / relevance gate ───────────────────────────────────────
        # Fire when the query has zero legal context signal AND results are weak.
        # Covers two cases:
        #   1. broad mode, unknown domain — same as before (off-topic / nonsense)
        #   2. domain_search mode — law identified by domain signal but returned
        #      chunks share almost no tokens with the query (garbage BM25 match)
        #      Threshold is lower (0.3) because domain queries are less specific.
        query_tokens_list = [
            t for t in understanding.keywords
            if len(t) >= 4 and t not in {"text", "data", "cast", "nebo", "jako"}
        ]

        if items and query_tokens_list:
            max_overlap = max(
                overlap_ratio(query_tokens_list, item.text or "")
                for item in items
            )
            broad_garbage = (
                plan.mode == "broad"
                and understanding.detected_domain == "unknown"
                and not understanding.detected_law_refs
                and not understanding.detected_paragraphs
                and max_overlap < 0.5
            )
            domain_garbage = (
                plan.mode == "constrained"
                and not plan.law_filter           # domain_search: preferred only, no hard filter
                and understanding.detected_domain != "unknown"
                and not understanding.detected_paragraphs
                and max_overlap < 0.3
            )
            if broad_garbage or domain_garbage:
                log.info(
                    "czech retrieval: low-overlap gate fired mode=%s domain=%s overlap=%.2f",
                    plan.mode,
                    understanding.detected_domain,
                    max_overlap,
                )
                return [self._irrelevant_query_response()]

        # ── relevance filter ──────────────────────────────────────────────────
        query_text = parsed["normalized_query"]

        def is_relevant(item: EvidencePackItem) -> bool:
            if plan.mode == "exact":
                return True
            if understanding.detected_domain != "unknown":
                return True
            text = (item.text or "").lower()
            meaningful = [w for w in query_text.split() if len(w) > 3]
            return any(w in text for w in meaningful)

        if not items or not any(is_relevant(item) for item in items):
            return [
                SearchResultItem(
                    chunk_id="no_result",
                    document_id="",
                    filename="Nenalezeno",
                    country=CountryEnum.CZECHIA,
                    domain=DomainEnum.LAW,
                    jurisdiction_module="czechia",
                    text="Nepodařilo se najít relevantní výsledek.",
                    chunk_index=0,
                    source_type="system",
                    source=None,
                    case_id=None,
                    tags=["no_result"],
                    score=0.0,
                )
            ]

        items = self._dedup_by_text(items)
        log.info(
            "czech law retrieval complete: mode=%s domain=%s results=%d",
            validation.evidence_pack.plan.mode if validation.evidence_pack.plan else plan.mode,
            understanding.detected_domain,
            len(items),
        )
        return [self._to_result(item) for item in items]

    @staticmethod
    def _dedup_by_text(items: list[EvidencePackItem]) -> list[EvidencePackItem]:
        """Remove items whose text is identical to a higher-scored item already kept."""
        seen: set[str] = set()
        result: list[EvidencePackItem] = []
        for item in items:
            key = (item.text or "").strip()
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            result.append(item)
        return result

    def _irrelevant_query_response(self) -> SearchResultItem:
        return SearchResultItem(
            chunk_id="irrelevant_query",
            document_id="",
            filename="Dotaz nesouvisí s právem",
            country=CountryEnum.CZECHIA,
            domain=DomainEnum.LAW,
            jurisdiction_module="czechia",
            text=(
                "Váš dotaz neobsahuje žádné právní pojmy. "
                "Zkuste dotaz přeformulovat — uveďte název zákona, číslo paragrafu "
                "nebo konkrétní právní situaci (např. 'výpověď zákoník práce', '§ 52', "
                "'pracovní smlouva náležitosti')."
            ),
            chunk_index=0,
            source_type="system",
            source=None,
            case_id=None,
            tags=["irrelevant_query"],
            score=0.0,
        )

    def _apply_keyword_boost(
        self,
        items: list[EvidencePackItem],
        query_text: str,
        is_exact: bool,
    ) -> list[EvidencePackItem]:
        if is_exact or not items:
            return items

        normalized_query = (query_text or "").strip().lower()
        query_terms = [
            term for term in re.findall(r"\w+", normalized_query)
            if len(term) > 3
        ]
        if not query_terms:
            return items

        phrase = " ".join(query_terms)
        for item in items:
            text = (item.text or "").lower()
            overlap_count = sum(1 for term in query_terms if term in text)
            if overlap_count:
                item.score += 0.4 * overlap_count
            if phrase and phrase in text:
                item.score += 0.8

        items.sort(key=lambda item: item.score, reverse=True)
        return items

    def _build_ambiguity_results(
        self,
        ambiguity: AmbiguityResult,
        top_k: int,
    ) -> list[SearchResultItem]:
        results = [
            SearchResultItem(
                chunk_id="clarification:message",
                document_id="",
                filename="Upřesnění dotazu",
                country=CountryEnum.CZECHIA,
                domain=DomainEnum.LAW,
                jurisdiction_module="czechia",
                text=ambiguity.message,
                chunk_index=0,
                source_type="clarification",
                source="ambiguity_handler",
                case_id=None,
                tags=[],
                score=1.0,
            )
        ]

        for index, suggestion in enumerate(ambiguity.suggestions, start=1):
            law_iri = str(suggestion.get("law_iri", ""))
            paragraph = suggestion.get("paragraph")
            results.append(
                SearchResultItem(
                    chunk_id=f"clarification:suggestion:{law_iri}:{paragraph}",
                    document_id=law_iri,
                    filename=self._iri_to_filename(law_iri),
                    country=CountryEnum.CZECHIA,
                    domain=DomainEnum.LAW,
                    jurisdiction_module="czechia",
                    text=str(suggestion.get("label", "")),
                    chunk_index=index,
                    source_type="clarification_suggestion",
                    source="ambiguity_handler",
                    case_id=None,
                    tags=[],
                    score=max(0.0, 1.0 - (index * 0.01)),
                )
            )

        return results[:top_k]

    def _execute_plan(
        self,
        query: str,
        understanding: QueryUnderstanding,
        plan: RetrievalPlan,
    ) -> EvidencePack:
        if plan.mode == "exact" and plan.paragraph_filter:
            target_laws = plan.law_filter or plan.preferred_law_iris or []
            exact_hits = self._dense.exact_lookup(
                law_iris=target_laws,
                paragraph_numbers=plan.paragraph_filter,
                limit=plan.candidate_k,
            )
            if plan.law_filter:
                exact_hits = [
                    hit for hit in exact_hits
                    if hit.get("law_iri") in plan.law_filter
                ]
            return self._build_exact_evidence_pack(exact_hits, understanding, plan)

        search_query = understanding.cleaned_query or query
        # Dense retrieval always uses the original cleaned_query for best embedding quality.
        # Sparse (BM25) retrieval uses the expanded query when available so that
        # topic triggers like "výpověď" expand to "výpověď § 52 § 53 …" and hit
        # paragraph headings instead of derogation-index lines.
        sparse_query = understanding.expanded_query or search_query
        if understanding.expanded_query:
            log.debug(
                "czech retrieval: sparse expansion active query=%r expanded=%r",
                search_query,
                understanding.expanded_query,
            )
        query_vector = self._embedding.embed_query(search_query)
        candidates = self._generate_candidates(
            search_query=search_query,
            sparse_query=sparse_query,
            query_vector=query_vector,
            understanding=understanding,
            plan=plan,
        )
        fused_hits = rrf_fuse(
            dense_hits=candidates.dense_hits,
            sparse_hits=candidates.sparse_hits,
            top_k=None,
        )
        merged_hits = self._merge_candidate_sets(
            fused_hits=fused_hits,
            exact_hits=candidates.exact_hits,
            neighbor_hits=candidates.neighbor_hits,
        )
        return self._reranker.rerank(
            candidates=merged_hits,
            understanding=understanding,
            plan=plan,
        )

    def _generate_candidates(
        self,
        search_query: str,
        query_vector: list[float],
        understanding: QueryUnderstanding,
        plan: RetrievalPlan,
        sparse_query: str | None = None,
    ) -> CandidateBatch:
        exact_hits: list[dict] = []
        target_laws_for_exact = plan.law_filter or plan.preferred_law_iris
        if target_laws_for_exact and plan.paragraph_filter:
            exact_hits = self._dense.exact_lookup(
                law_iris=target_laws_for_exact,
                paragraph_numbers=plan.paragraph_filter,
                limit=max(12, plan.candidate_k // 4),
            )

        if plan.mode == "exact":
            return CandidateBatch(
                exact_hits=exact_hits,
                dense_hits=[],
                sparse_hits=[],
                neighbor_hits=[],
            )

        # sparse_query: expanded form for BM25 (or falls back to search_query)
        _sparse_query = sparse_query or search_query

        futures = {}
        with ThreadPoolExecutor(max_workers=4) as executor:
            if plan.use_dense:
                futures["dense"] = executor.submit(
                    self._dense.retrieve,
                    query_vector=query_vector,
                    law_iris=plan.law_filter or None,
                    top_k=plan.candidate_k,
                )
            if plan.use_sparse:
                futures["sparse"] = executor.submit(
                    self._sparse.retrieve,
                    query_text=_sparse_query,
                    law_iris=plan.law_filter or None,
                    top_k=plan.candidate_k,
                )
            if plan.use_dense and plan.preferred_law_iris and not plan.law_filter:
                futures["dense_preferred"] = executor.submit(
                    self._dense.retrieve,
                    query_vector=query_vector,
                    law_iris=plan.preferred_law_iris,
                    top_k=max(12, plan.candidate_k // 2),
                )
            if plan.use_sparse and plan.preferred_law_iris and not plan.law_filter:
                futures["sparse_preferred"] = executor.submit(
                    self._sparse.retrieve,
                    query_text=_sparse_query,
                    law_iris=plan.preferred_law_iris,
                    top_k=max(12, plan.candidate_k // 2),
                )

        dense_hits = self._dedupe_hits(
            (futures.get("dense").result() if "dense" in futures else [])
            + (futures.get("dense_preferred").result() if "dense_preferred" in futures else [])
        )
        sparse_hits = self._dedupe_hits(
            (futures.get("sparse").result() if "sparse" in futures else [])
            + (futures.get("sparse_preferred").result() if "sparse_preferred" in futures else [])
        )

        anchors = self._build_anchor_list(exact_hits, dense_hits, sparse_hits)
        neighbor_hits = self._dense.expand_neighbors(
            anchors=anchors,
            window=plan.structural_window,
            limit=max(10, min(30, plan.candidate_k // 3)),
        )

        log.info(
            "czech candidates generated: exact=%d dense=%d sparse=%d neighbors=%d mode=%s",
            len(exact_hits),
            len(dense_hits),
            len(sparse_hits),
            len(neighbor_hits),
            plan.mode,
        )
        return CandidateBatch(
            exact_hits=exact_hits,
            dense_hits=dense_hits,
            sparse_hits=sparse_hits,
            neighbor_hits=neighbor_hits,
        )

    def _build_anchor_list(
        self,
        exact_hits: list[dict],
        dense_hits: list[dict],
        sparse_hits: list[dict],
    ) -> list[dict]:
        anchors = []
        anchors.extend(exact_hits[:8])
        anchors.extend(dense_hits[:6])
        anchors.extend(sparse_hits[:6])
        return self._dedupe_hits(anchors)

    def _merge_candidate_sets(
        self,
        fused_hits: list[dict],
        exact_hits: list[dict],
        neighbor_hits: list[dict],
    ) -> list[dict]:
        merged: dict[str, dict] = {}
        for bucket in (fused_hits, exact_hits, neighbor_hits):
            for hit in bucket:
                chunk_id = hit.get("chunk_id")
                if not chunk_id:
                    continue
                if chunk_id not in merged:
                    merged[chunk_id] = dict(hit)
                    continue
                self._merge_payload(merged[chunk_id], hit)
        return list(merged.values())

    def _dedupe_hits(self, hits: list[dict]) -> list[dict]:
        deduped: dict[str, dict] = {}
        for hit in hits:
            chunk_id = hit.get("chunk_id")
            if not chunk_id:
                continue
            if chunk_id not in deduped:
                deduped[chunk_id] = dict(hit)
                continue
            self._merge_payload(deduped[chunk_id], hit)
        return list(deduped.values())

    def _build_exact_evidence_pack(
        self,
        exact_hits: list[dict],
        understanding: QueryUnderstanding,
        plan: RetrievalPlan,
    ) -> EvidencePack:
        items: list[EvidencePackItem] = []
        total = max(len(exact_hits), 1)
        for index, hit in enumerate(exact_hits):
            paragraph = pick_primary_paragraph(hit)
            is_heading = bool(hit.get("_exact_heading_match"))
            score = 2.0 - (index / (total + 1))
            if is_heading:
                score += 1.0
            items.append(
                EvidencePackItem(
                    chunk_id=str(hit.get("chunk_id", "")),
                    law_iri=str(hit.get("law_iri", "")),
                    paragraph=paragraph,
                    text=str(hit.get("text", "")),
                    score=score,
                    source_metadata={
                        "fragment_id": hit.get("fragment_id"),
                        "chunk_index": int(hit.get("chunk_index", 0) or 0),
                        "source_type": hit.get("source_type", "law_fragment"),
                        "metadata_ref": hit.get("metadata_ref"),
                    },
                    validation_flags={
                        "strict_law_match": str(hit.get("law_iri", "")) in plan.law_filter,
                        "paragraph_match": paragraph in plan.paragraph_filter if paragraph else False,
                        "exact_match": True,
                        "exact_heading_match": is_heading,
                    },
                    chunk_index=int(hit.get("chunk_index", 0) or 0),
                    source_type=str(hit.get("source_type", "law_fragment")),
                    source=hit.get("metadata_ref"),
                    dense_score=float(hit.get("_dense_score", 1.0)),
                    sparse_score=0.0,
                    rrf_score=0.0,
                )
            )
        return EvidencePack(items=items, understanding=understanding, plan=plan)

    @staticmethod
    def _merge_payload(target: dict, source: dict) -> None:
        for key, value in source.items():
            if key in {"_dense_score", "_sparse_score", "_rrf_score"}:
                target[key] = max(float(target.get(key, 0.0)), float(value or 0.0))
                continue
            if key in {"_exact_match", "_structural_neighbor", "_neighbor_of_exact_match"}:
                target[key] = bool(target.get(key)) or bool(value)
                continue
            if key not in target or target[key] in (None, "", []):
                target[key] = value

    @staticmethod
    def _to_result(item: EvidencePackItem) -> SearchResultItem:
        return SearchResultItem(
            chunk_id=item.chunk_id,
            document_id=item.law_iri,
            filename=CzechLawRetrievalService._iri_to_filename(item.law_iri),
            country=CountryEnum.CZECHIA,
            domain=DomainEnum.LAW,
            jurisdiction_module="czechia",
            text=item.text,
            chunk_index=item.chunk_index,
            source_type=item.source_type,
            source=item.source,
            case_id=None,
            tags=[],
            score=float(item.score),
        )

    @staticmethod
    def _iri_to_filename(law_iri: str) -> str:
        number, year = parse_law_iri(law_iri)
        if number and year:
            return f"{number}/{year} Sb."
        return law_iri
