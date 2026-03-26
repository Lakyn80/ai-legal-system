from app.core.enums import CountryEnum, DomainEnum
from app.modules.common.qdrant.retrieval_service import RetrievalService
from app.modules.common.qdrant.schemas import SearchRequest, SearchResultItem


class FakeEmbeddings:
    def embed_query(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


class FakeVectorStore:
    def __init__(self, results: list[SearchResultItem]) -> None:
        self.results = results
        self.requested_top_k: int | None = None

    def search(
        self,
        query_vector: list[float],
        top_k: int,
        country: str | None = None,
        domain: str | None = None,
        document_ids: list[str] | None = None,
        case_id: str | None = None,
    ) -> list[SearchResultItem]:
        self.requested_top_k = top_k
        return self.results


def build_result(chunk_id: str, text: str, score: float) -> SearchResultItem:
    return SearchResultItem(
        chunk_id=chunk_id,
        document_id="doc-1",
        filename="collection.json",
        country=CountryEnum.CZECHIA,
        domain=DomainEnum.LAW,
        jurisdiction_module="czechia",
        text=text,
        chunk_index=1,
        source_type="legal_collection_json",
        source="Sb_2012_89_2026-01-01_IZ",
        tags=["law"],
        score=score,
    )


def test_retrieval_service_reranks_by_lexical_overlap():
    vector_store = FakeVectorStore(
        results=[
            build_result("chunk-1", "Úplně nesouvisející pasáž o procesních náležitostech.", 0.92),
            build_result(
                "chunk-2",
                "Občanský zákoník. Tento zákon upravuje soukromá práva a povinnosti.",
                0.55,
            ),
        ]
    )
    service = RetrievalService(
        embedding_service=FakeEmbeddings(),
        vector_store=vector_store,
    )

    results = service.search(
        SearchRequest(
            query="obcansky zakonik soukroma prava a povinnosti",
            country=CountryEnum.CZECHIA,
            domain=DomainEnum.LAW,
            top_k=1,
        )
    )

    assert vector_store.requested_top_k == 4
    assert results[0].chunk_id == "chunk-2"


def test_retrieval_service_returns_hybrid_bundle():
    vector_store = FakeVectorStore(
        results=[
            build_result("chunk-1", "Procesni text bez relevance.", 0.91),
            build_result("chunk-2", "Občanský zákoník upravuje soukromá práva a povinnosti.", 0.56),
        ]
    )
    service = RetrievalService(
        embedding_service=FakeEmbeddings(),
        vector_store=vector_store,
    )

    bundle = service.retrieve(
        SearchRequest(
            query="obcansky zakonik soukroma prava a povinnosti",
            country=CountryEnum.CZECHIA,
            domain=DomainEnum.LAW,
            top_k=2,
        )
    )

    assert len(bundle.results) == 2
    assert bundle.features.keyword_coverage > 0
    assert bundle.ranked_results[0].item.chunk_id == "chunk-2"
