import json
import re
from dataclasses import dataclass
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.enums import DomainEnum
from app.modules.common.graph.schemas import StrategyRequest, StrategyResult
from app.modules.common.llm.provider import BaseLLMProvider
from app.modules.common.qdrant.retrieval_service import RetrievalService
from app.modules.common.qdrant.schemas import SearchRequest, SearchResultItem
from app.modules.contracts import JurisdictionDescriptor


@dataclass(frozen=True)
class StrategyGraphDependencies:
    descriptor: JurisdictionDescriptor
    retrieval_service: RetrievalService
    llm_provider: BaseLLMProvider


class StrategyState(TypedDict, total=False):
    request: StrategyRequest
    country: str
    facts: list[str]
    law_chunks: list[SearchResultItem]
    court_chunks: list[SearchResultItem]
    law_analysis: list[str]
    court_analysis: list[str]
    arguments_for_client: list[str]
    arguments_against_client: list[str]
    risks: list[str]
    recommended_actions: list[str]
    missing_documents: list[str]
    final_output: StrategyResult


def build_jurisdiction_strategy_graph(deps: StrategyGraphDependencies):
    def determine_jurisdiction(state: StrategyState) -> dict:
        request = state["request"]
        country = request.country or deps.descriptor.country
        return {
            "country": country.value,
            "facts": _extract_facts(request.query),
        }

    def retrieve_laws(state: StrategyState) -> dict:
        request = state["request"]
        results = deps.retrieval_service.search(
            SearchRequest(
                query=request.query,
                country=deps.descriptor.country,
                domain=DomainEnum.LAW,
                document_ids=request.document_ids,
                case_id=request.case_id,
                top_k=max(2, request.top_k // 2),
            )
        )
        return {"law_chunks": results}

    def retrieve_courts(state: StrategyState) -> dict:
        request = state["request"]
        results = deps.retrieval_service.search(
            SearchRequest(
                query=request.query,
                country=deps.descriptor.country,
                domain=DomainEnum.COURTS,
                document_ids=request.document_ids,
                case_id=request.case_id,
                top_k=max(2, request.top_k // 2),
            )
        )
        return {"court_chunks": results}

    def analyze_laws(state: StrategyState) -> dict:
        return {
            "law_analysis": _extract_relevant_points(
                state.get("law_chunks", []),
                state["request"].query,
                prefix=f"Relevant legal norm for {deps.descriptor.label}:",
            )
        }

    def analyze_courts(state: StrategyState) -> dict:
        return {
            "court_analysis": _extract_relevant_points(
                state.get("court_chunks", []),
                state["request"].query,
                prefix=f"Relevant court position for {deps.descriptor.label}:",
            )
        }

    def synthesize_arguments(state: StrategyState) -> dict:
        law_analysis = state.get("law_analysis", [])
        court_analysis = state.get("court_analysis", [])
        support = [
            f"Build the primary line of argument on: {item}"
            for item in (law_analysis[:3] + court_analysis[:2])
        ]
        counter = []
        if not law_analysis:
            counter.append("The record currently lacks directly relevant statutory support.")
        if not court_analysis:
            counter.append("The record currently lacks supporting judicial interpretation.")
        if state["request"].case_id is None:
            counter.append("No case identifier was supplied, so some relevant case-specific material may be missing.")

        recommended_actions = [
            f"Validate how the matter aligns with {deps.descriptor.law_focus.lower()}."
        ]
        if court_analysis:
            recommended_actions.append(
                f"Map the retrieved holdings against {deps.descriptor.court_focus.lower()}."
            )
        else:
            recommended_actions.append("Add leading court decisions before finalizing the litigation strategy.")

        return {
            "arguments_for_client": support,
            "arguments_against_client": counter,
            "recommended_actions": recommended_actions,
        }

    def assess_risks(state: StrategyState) -> dict:
        risks = []
        if len(state.get("law_chunks", [])) < 2:
            risks.append("Low volume of statutory context reduces legal certainty.")
        if len(state.get("court_chunks", [])) < 2:
            risks.append("Low volume of case-law context weakens predictive confidence.")

        missing_documents = []
        if not state["request"].document_ids:
            missing_documents.extend(deps.descriptor.missing_document_hints[:2])
        if state["request"].case_id is None:
            missing_documents.append("Case-specific filing history or procedural chronology.")

        return {
            "risks": risks,
            "missing_documents": list(dict.fromkeys(missing_documents)),
        }

    def finalize(state: StrategyState) -> dict:
        summary = _build_summary(state, deps.descriptor)
        confidence = min(
            0.95,
            0.25 + (0.08 * len(state.get("law_chunks", []))) + (0.08 * len(state.get("court_chunks", []))),
        )
        payload = {
            "jurisdiction": deps.descriptor.country.value,
            "domain": state["request"].domain.value if state["request"].domain else "mixed",
            "summary": summary,
            "facts": state.get("facts", []),
            "relevant_laws": state.get("law_analysis", []),
            "relevant_court_positions": state.get("court_analysis", []),
            "arguments_for_client": state.get("arguments_for_client", []),
            "arguments_against_client": state.get("arguments_against_client", []),
            "risks": state.get("risks", []),
            "recommended_actions": state.get("recommended_actions", []),
            "missing_documents": state.get("missing_documents", []),
            "confidence": round(confidence, 2),
        }
        result = deps.llm_provider.invoke_structured(
            system_prompt=deps.descriptor.system_prompt,
            user_prompt=json.dumps(payload, ensure_ascii=False),
            schema=StrategyResult,
        )
        return {"final_output": result}

    graph = StateGraph(StrategyState)
    graph.add_node("determine_jurisdiction", determine_jurisdiction)
    graph.add_node("retrieve_laws", retrieve_laws)
    graph.add_node("retrieve_courts", retrieve_courts)
    graph.add_node("analyze_laws", analyze_laws)
    graph.add_node("analyze_courts", analyze_courts)
    graph.add_node("synthesize_arguments", synthesize_arguments)
    graph.add_node("assess_risks", assess_risks)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "determine_jurisdiction")
    graph.add_edge("determine_jurisdiction", "retrieve_laws")
    graph.add_edge("retrieve_laws", "retrieve_courts")
    graph.add_edge("retrieve_courts", "analyze_laws")
    graph.add_edge("analyze_laws", "analyze_courts")
    graph.add_edge("analyze_courts", "synthesize_arguments")
    graph.add_edge("synthesize_arguments", "assess_risks")
    graph.add_edge("assess_risks", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


def _extract_facts(query: str) -> list[str]:
    parts = re.split(r"[.;]\s+|\n+", query)
    facts = [part.strip() for part in parts if part.strip()]
    return facts[:5] or [query.strip()]


def _extract_relevant_points(
    chunks: list[SearchResultItem],
    query: str,
    prefix: str,
    limit: int = 4,
) -> list[str]:
    query_tokens = {token for token in re.findall(r"\w+", query.lower()) if len(token) > 3}
    scored_sentences: list[tuple[int, str]] = []
    for chunk in chunks:
        sentences = re.split(r"(?<=[.!?])\s+", chunk.text)
        for sentence in sentences:
            cleaned = sentence.strip()
            if len(cleaned) < 30:
                continue
            tokens = set(re.findall(r"\w+", cleaned.lower()))
            overlap = len(tokens & query_tokens)
            scored_sentences.append((overlap, cleaned))

    scored_sentences.sort(key=lambda item: (item[0], len(item[1])), reverse=True)
    selected: list[str] = []
    for _, sentence in scored_sentences:
        candidate = f"{prefix} {sentence}"
        if candidate not in selected:
            selected.append(candidate)
        if len(selected) >= limit:
            break
    return selected


def _build_summary(state: StrategyState, descriptor: JurisdictionDescriptor) -> str:
    law_count = len(state.get("law_chunks", []))
    court_count = len(state.get("court_chunks", []))
    return (
        f"Strategy draft for {descriptor.label} was built from {law_count} legal chunks and "
        f"{court_count} court-decision chunks. Focus the next analysis cycle on {descriptor.law_focus.lower()} "
        f"and validate it against {descriptor.court_focus.lower()}."
    )
