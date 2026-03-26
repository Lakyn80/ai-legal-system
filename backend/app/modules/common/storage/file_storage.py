import re
from pathlib import Path


class FileStorageService:
    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path
        self.documents_dir = self.base_path / "documents"
        self.metadata_dir = self.base_path / "metadata"
        self.documents_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

    def save_file(self, document_id: str, filename: str, content: bytes) -> str:
        safe_name = self._sanitize_filename(filename)
        suffix = Path(safe_name).suffix
        target_path = self.documents_dir / f"{document_id}{suffix}"
        target_path.write_bytes(content)
        return str(target_path)

    def metadata_path(self, document_id: str) -> Path:
        return self.metadata_dir / f"{document_id}.json"

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        cleaned = Path(filename).name
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", cleaned)
        return cleaned or "document.bin"
