import json
import zipfile
from pathlib import Path

from app.modules.common.parsing.xhtml import strip_xhtml


class LegalCollectionParser:
    def parse_json_file(self, path: Path) -> str:
        return self.parse_json_bytes(path.read_bytes(), source_name=path.name)

    def parse_zip_file(self, path: Path) -> str:
        with zipfile.ZipFile(path) as archive:
            json_member = self._find_json_member(archive)
            if json_member is None:
                raise ValueError("ZIP archive does not contain a supported JSON legal collection.")
            payload = archive.read(json_member)
        return self.parse_json_bytes(payload, source_name=json_member)

    def parse_json_bytes(self, payload: bytes, source_name: str) -> str:
        data = json.loads(payload.decode("utf-8-sig"))
        if self._is_legal_collection(data):
            return self._render_legal_collection(data, source_name)
        return json.dumps(data, ensure_ascii=False, indent=2)

    @staticmethod
    def _find_json_member(archive: zipfile.ZipFile) -> str | None:
        json_members = [item.filename for item in archive.infolist() if item.filename.lower().endswith(".json")]
        preferred = next((item for item in json_members if "_iz.json" in item.lower()), None)
        return preferred or (json_members[0] if json_members else None)

    @staticmethod
    def _is_legal_collection(data: object) -> bool:
        return (
            isinstance(data, dict)
            and isinstance(data.get("metadata"), dict)
            and isinstance(data.get("fragmenty"), list)
        )

    def _render_legal_collection(self, data: dict, source_name: str) -> str:
        metadata = data.get("metadata", {})
        header_lines = self._build_header(metadata, source_name)
        fragment_lines = self._build_fragments(data.get("fragmenty", []))
        return "\n\n".join(
            section for section in ("\n".join(header_lines).strip(), "\n\n".join(fragment_lines).strip()) if section
        ).strip()

    @staticmethod
    def _build_header(metadata: dict, source_name: str) -> list[str]:
        predpis_cislo = metadata.get("predpisCislo")
        rocnik = metadata.get("rocnik")
        castka = metadata.get("castkaCislo")
        datum = metadata.get("datumUcinnostiZneniOd")

        lines = [f"Source file: {source_name}"]
        if predpis_cislo and rocnik:
            lines.append(f"Legal collection item: {predpis_cislo}/{rocnik} Sb.")
        if castka:
            lines.append(f"Collection issue number: {castka}")
        if datum:
            lines.append(f"Effective wording date: {datum}")
        return lines

    def _build_fragments(self, fragments: list[dict]) -> list[str]:
        rendered: list[str] = []
        for fragment in fragments:
            text = strip_xhtml(fragment.get("xhtml") or "")
            if not text:
                continue

            fragment_type = fragment.get("typ") or "Fragment"
            depth = fragment.get("hloubka")
            fragment_id = fragment.get("fragmentId")

            prefix_parts = [fragment_type]
            if depth is not None:
                prefix_parts.append(f"depth={depth}")
            if fragment_id:
                prefix_parts.append(f"id={fragment_id}")

            rendered.append(f"[{' | '.join(prefix_parts)}]\n{text}")
        return rendered
