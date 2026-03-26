import json

from app.modules.common.querying.schemas import QueryContext
from app.modules.common.qdrant.schemas import HybridSearchResponse


SEARCH_EXPLANATION_SYSTEM_PROMPT = """
You are a legal retrieval analyst.
Answer only from the supplied legal evidence.
Do not invent sources.
Return a compact explanation that stays grounded in the retrieved chunks.
""".strip()


def build_search_explanation_prompt(query_context: QueryContext, retrieval: HybridSearchResponse) -> str:
    payload = {
        "query": query_context.raw_query,
        "jurisdiction": query_context.jurisdiction.value,
        "domain": query_context.domain.value if query_context.domain else "mixed",
        "query_type": query_context.query_type.value,
        "sources": [
            {
                "chunk_id": result.chunk_id,
                "document_id": result.document_id,
                "filename": result.filename,
                "source": result.source,
                "score": result.score,
                "text": result.text,
            }
            for result in retrieval.results[:4]
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
