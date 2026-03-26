from app.modules.common.chunking.service import TextChunkingService


def test_chunker_returns_multiple_chunks_for_long_text():
    chunker = TextChunkingService(chunk_size=20, chunk_overlap=5)
    chunks = chunker.chunk_text("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda")
    assert len(chunks) >= 2
