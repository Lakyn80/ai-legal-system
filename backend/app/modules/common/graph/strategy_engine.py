from app.modules.common.graph.builder import StrategyGraphDependencies
from app.modules.common.graph.schemas import StrategyRequest, StrategyResponse
from app.modules.common.llm.provider import BaseLLMProvider
from app.modules.common.qdrant.retrieval_service import RetrievalService
from app.modules.registry import JurisdictionRegistry


class StrategyEngine:
    def __init__(
        self,
        registry: JurisdictionRegistry,
        retrieval_service: RetrievalService,
        llm_provider: BaseLLMProvider,
    ) -> None:
        self.registry = registry
        self.retrieval_service = retrieval_service
        self.llm_provider = llm_provider
        self._graphs: dict[str, object] = {}

    def generate(self, request: StrategyRequest) -> StrategyResponse:
        descriptor = self.registry.resolve(request.country, request.query)
        graph = self._get_graph(descriptor)
        state = graph.invoke({"request": request})
        retrieved_chunks = state.get("law_chunks", []) + state.get("court_chunks", [])
        return StrategyResponse(
            strategy=state["final_output"],
            retrieved_chunks=retrieved_chunks,
        )

    def _get_graph(self, descriptor):
        key = descriptor.country.value
        if key not in self._graphs:
            self._graphs[key] = descriptor.graph_builder(
                StrategyGraphDependencies(
                    descriptor=descriptor,
                    retrieval_service=self.retrieval_service,
                    llm_provider=self.llm_provider,
                )
            )
        return self._graphs[key]
