import json
import zipfile
from pathlib import Path

from app.modules.common.parsing.legal_collection import LegalCollectionParser


def build_collection_payload() -> dict:
    return {
        "metadata": {
            "castkaCislo": 33,
            "predpisCislo": 89,
            "rocnik": 2012,
            "datumUcinnostiZneniOd": "2026-01-01",
        },
        "fragmenty": [
            {
                "fragmentId": "frag-1",
                "hloubka": 1,
                "typ": "Heading",
                "xhtml": "<h1>Občanský zákoník</h1>",
                "souboroveDokumenty": [],
            },
            {
                "fragmentId": "frag-2",
                "hloubka": 2,
                "typ": "Paragraph",
                "xhtml": "<p>§ 1 Tento zákon upravuje soukromá práva a povinnosti.</p>",
                "souboroveDokumenty": [],
            },
        ],
    }


def test_parse_json_file_extracts_legal_collection_text(tmp_path: Path):
    parser = LegalCollectionParser()
    payload = build_collection_payload()
    target = tmp_path / "collection.json"
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    text = parser.parse_json_file(target)

    assert "89/2012 Sb." in text
    assert "Občanský zákoník" in text
    assert "§ 1 Tento zákon upravuje soukromá práva a povinnosti." in text


def test_parse_zip_file_uses_embedded_json(tmp_path: Path):
    parser = LegalCollectionParser()
    payload = build_collection_payload()
    target = tmp_path / "collection.zip"
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr(
            "Sb_2012_89/Sb_2012_89_2026-01-01_IZ.json",
            json.dumps(payload, ensure_ascii=False),
        )

    text = parser.parse_zip_file(target)

    assert "Source file: Sb_2012_89/Sb_2012_89_2026-01-01_IZ.json" in text
    assert "Legal collection item: 89/2012 Sb." in text


def test_parse_json_file_falls_back_to_plain_json_for_generic_payload(tmp_path: Path):
    parser = LegalCollectionParser()
    target = tmp_path / "generic.json"
    target.write_text(json.dumps({"foo": "bar"}, ensure_ascii=False), encoding="utf-8")

    text = parser.parse_json_file(target)

    assert '"foo": "bar"' in text
