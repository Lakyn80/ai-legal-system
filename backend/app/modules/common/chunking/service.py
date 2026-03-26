from langchain_text_splitters import RecursiveCharacterTextSplitter


class TextChunkingService:
    def __init__(self, chunk_size: int, chunk_overlap: int) -> None:
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def chunk_text(self, text: str) -> list[str]:
        cleaned = text.strip()
        if not cleaned:
            return []
        return self._splitter.split_text(cleaned)
