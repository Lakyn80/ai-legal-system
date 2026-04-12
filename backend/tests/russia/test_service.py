"""
Orchestration tests for Russian law ingestion — Step 4 verification.

Tests exercise the full pipeline: loader → parser → chunk_builder → embedder →
qdrant_writer through the service.py orchestrator.

Tests require both the corpus and Qdrant to be available.
Collection russian_laws_v1 is created fresh before and cleaned up after each
test session.
"""
from __future__ import annotations

import json
import os
import tempfile
import pytest
from pathlib import Path

# ---------------------------------------------------------------------------
# Availability guards
# ---------------------------------------------------------------------------

_CORPUS_ROOT = Path("/app/Ruske_zakony")
_TK_PATH = _CORPUS_ROOT / "rest_of_the_codex_russia" / "Трудовой кодекс Российской Федерации  от 30.12.2001 N 197-ФЗ-u.txt"
_SK_PATH = _CORPUS_ROOT / "Семейный кодекс Российской Федерации  от 29.12.1995 N 223-ФЗ-u.txt"
_GK1_PATH = _CORPUS_ROOT / "Гражданский кодекс Российской Федерации (часть первая)  от 3-u.txt"

_CORPUS_AVAILABLE = _TK_PATH.exists() and _SK_PATH.exists() and _GK1_PATH.exists()

QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")


def _qdrant_reachable() -> bool:
    try:
        from app.modules.russia.ingestion.qdrant_writer import RussianLawQdrantWriter
        return RussianLawQdrantWriter(url=QDRANT_URL).health_check()
    except Exception:
        return False


_QDRANT_AVAILABLE = _CORPUS_AVAILABLE and _qdrant_reachable()

pytestmark = pytest.mark.skipif(
    not _QDRANT_AVAILABLE,
    reason="Corpus or Qdrant not available — skipping service tests",
)

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

from app.core.config import get_settings
from app.modules.common.embeddings.provider import EmbeddingService
from app.modules.russia.ingestion.chunk_builder import build_chunks
from app.modules.russia.ingestion.embedder import RussianLawEmbedder
from app.modules.russia.ingestion.loader import load_law_file
from app.modules.russia.ingestion.parser import parse_law
from app.modules.russia.ingestion.qdrant_writer import RussianLawQdrantWriter, COLLECTION_NAME
from app.modules.russia.ingestion.service import (
    ingest_law_file,
    ingest_corpus,
    FileIngestResult,
    IngestReport,
)

# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture(scope="session")
def embedding_service(settings) -> EmbeddingService:
    return EmbeddingService(
        model_name=settings.embedding_model,
        provider_name=settings.embedding_provider,
        hash_dimension=settings.embedding_hash_dimension,
    )


@pytest.fixture(scope="session")
def embedder(embedding_service: EmbeddingService) -> RussianLawEmbedder:
    return RussianLawEmbedder(embedding_service)


@pytest.fixture(scope="session")
def writer() -> RussianLawQdrantWriter:
    return RussianLawQdrantWriter(url=QDRANT_URL)


@pytest.fixture(scope="session", autouse=True)
def clean_collection(writer: RussianLawQdrantWriter):
    """Drop russian_laws_v1 before the session, clean up after."""
    from qdrant_client import QdrantClient
    client = QdrantClient(url=QDRANT_URL, timeout=30)
    if client.collection_exists(COLLECTION_NAME):
        client.delete_collection(COLLECTION_NAME)
    yield
    if client.collection_exists(COLLECTION_NAME):
        client.delete_collection(COLLECTION_NAME)


# ---------------------------------------------------------------------------
# Single-file ingest tests
# ---------------------------------------------------------------------------

def test_single_file_ingest_returns_result(embedder, writer) -> None:
    """ingest_law_file() must return a valid FileIngestResult with no error."""
    writer.ensure_collection(dimension=embedder.dimension)
    result = ingest_law_file(_SK_PATH, embedder, writer)

    assert isinstance(result, FileIngestResult)
    assert result.error is None
    assert result.was_skipped is False


def test_single_file_ingest_law_id(embedder, writer) -> None:
    """Ingesting СК РФ must produce law_id='local:ru/sk'."""
    # Collection already exists from previous test in session (idempotent)
    result = ingest_law_file(_SK_PATH, embedder, writer)
    assert result.law_id == "local:ru/sk"
    assert result.law_short == "СК РФ"


def test_single_file_ingest_chunk_count_matches_builder(embedder, writer) -> None:
    """chunks_written must equal the count that chunk_builder produces."""
    meta, raw = load_law_file(_SK_PATH)
    parse_result = parse_law(meta, raw)
    expected_chunks = len(build_chunks(parse_result))

    result = ingest_law_file(_SK_PATH, embedder, writer)
    assert result.chunks_written == expected_chunks


def test_single_file_ingest_article_count(embedder, writer) -> None:
    """article_count in result must equal parse_result.article_count."""
    meta, raw = load_law_file(_TK_PATH)
    parse_result = parse_law(meta, raw)

    result = ingest_law_file(_TK_PATH, embedder, writer)
    assert result.article_count == parse_result.article_count


def test_single_file_ingest_qdrant_count_matches(embedder, writer) -> None:
    """After ingesting TK, Qdrant point count must include TK chunks."""
    meta, raw = load_law_file(_TK_PATH)
    parse_result = parse_law(meta, raw)
    expected = len(build_chunks(parse_result))

    ingest_law_file(_TK_PATH, embedder, writer)
    # Qdrant count includes all previously ingested files in this session
    total = writer.count()
    assert total >= expected, (
        f"Expected at least {expected} points in Qdrant, got {total}"
    )


# ---------------------------------------------------------------------------
# Three-law milestone corpus ingest
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def corpus_report(embedding_service) -> IngestReport:
    """Full corpus ingest of the three milestone laws — runs once per session."""
    with tempfile.TemporaryDirectory() as tmpdir:
        checkpoint = Path(tmpdir) / "test_checkpoint.json"
        report = ingest_corpus(
            directory=_CORPUS_ROOT,
            embedding_service=embedding_service,
            qdrant_url=QDRANT_URL,
            batch_size=64,
            checkpoint_path=checkpoint,
            verbose=False,
        )
        # Store checkpoint path on report object for checkpoint tests
        report._test_checkpoint_path = checkpoint  # type: ignore[attr-defined]
        # Store checkpoint content
        if checkpoint.exists():
            report._test_checkpoint_data = json.loads(checkpoint.read_text())  # type: ignore[attr-defined]
        else:
            report._test_checkpoint_data = {}  # type: ignore[attr-defined]
        return report


def test_corpus_ingest_finds_three_files(corpus_report: IngestReport) -> None:
    """Corpus discovery must find exactly 3 .txt files for M1."""
    assert corpus_report.files_found == 3, (
        f"Expected 3 .txt files in corpus, found {corpus_report.files_found}"
    )


def test_corpus_ingest_ingests_three_laws(corpus_report: IngestReport) -> None:
    """All three milestone laws must be ingested successfully."""
    assert corpus_report.files_ingested == 3, (
        f"Expected 3 ingested files, got {corpus_report.files_ingested}"
    )
    assert corpus_report.files_failed == 0


def test_corpus_ingest_no_unrecognized_files(corpus_report: IngestReport) -> None:
    """No files in the milestone corpus should be unrecognized."""
    assert corpus_report.files_unrecognized == 0, (
        f"Expected 0 unrecognized files, got {corpus_report.files_unrecognized}"
    )


def test_corpus_ingest_total_chunk_count(corpus_report: IngestReport, embedding_service) -> None:
    """Total chunk count must match the sum of all three law chunk counts."""
    expected_total = 0
    for path in [_SK_PATH, _TK_PATH, _GK1_PATH]:
        meta, raw = load_law_file(path)
        pr = parse_law(meta, raw)
        expected_total += len(build_chunks(pr))

    assert corpus_report.total_chunks == expected_total, (
        f"Expected {expected_total} total chunks, got {corpus_report.total_chunks}"
    )


def test_corpus_ingest_qdrant_count_matches_total_chunks(
    corpus_report: IngestReport,
    writer: RussianLawQdrantWriter,
) -> None:
    """Qdrant point count must equal total chunks after full corpus ingest."""
    qdrant_count = writer.count()
    # The session has run single-file tests before corpus — but all use the
    # same collection; the corpus ingest is idempotent so count == expected total
    assert qdrant_count == corpus_report.total_chunks, (
        f"Qdrant count {qdrant_count} != corpus total_chunks {corpus_report.total_chunks}"
    )


def test_corpus_ingest_processing_order_is_deterministic(corpus_report: IngestReport) -> None:
    """Results must be ordered by law_id (deterministic, not filesystem order)."""
    ingested = [r for r in corpus_report.results if not r.was_skipped and not r.error]
    law_ids = [r.law_id for r in ingested]
    assert law_ids == sorted(law_ids), (
        f"Results not in law_id order: {law_ids}"
    )


# ---------------------------------------------------------------------------
# Checkpoint tests
# ---------------------------------------------------------------------------

def test_checkpoint_written_after_corpus_ingest(corpus_report: IngestReport) -> None:
    """Checkpoint file must exist and contain all three ingested files."""
    data = corpus_report._test_checkpoint_data  # type: ignore[attr-defined]
    assert "files" in data, "Checkpoint missing 'files' key"
    assert len(data["files"]) == 3, (
        f"Expected 3 files in checkpoint, got {len(data['files'])}"
    )


def test_checkpoint_contains_law_ids(corpus_report: IngestReport) -> None:
    """Each checkpoint entry must contain law_id and chunks fields."""
    data = corpus_report._test_checkpoint_data  # type: ignore[attr-defined]
    for filename, entry in data.get("files", {}).items():
        assert "law_id" in entry, f"Checkpoint entry for {filename!r} missing law_id"
        assert "chunks" in entry, f"Checkpoint entry for {filename!r} missing chunks"
        assert entry["chunks"] > 0, f"Checkpoint entry for {filename!r} has 0 chunks"


def test_rerun_with_checkpoint_skips_all_files(embedding_service, writer) -> None:
    """A second ingest_corpus() run with an existing checkpoint must skip all files."""
    # Build checkpoint with all 3 files pre-populated
    with tempfile.TemporaryDirectory() as tmpdir:
        checkpoint_path = Path(tmpdir) / "preloaded.json"

        # First run to populate checkpoint
        report1 = ingest_corpus(
            directory=_CORPUS_ROOT,
            embedding_service=embedding_service,
            qdrant_url=QDRANT_URL,
            batch_size=64,
            checkpoint_path=checkpoint_path,
            verbose=False,
        )
        assert report1.files_ingested + report1.files_skipped_checkpoint == 3

        count_after_first = writer.count()

        # Second run — all files should be checkpointed
        report2 = ingest_corpus(
            directory=_CORPUS_ROOT,
            embedding_service=embedding_service,
            qdrant_url=QDRANT_URL,
            batch_size=64,
            checkpoint_path=checkpoint_path,
            verbose=False,
        )

        assert report2.files_skipped_checkpoint == 3, (
            f"Expected 3 checkpoint skips on second run, got {report2.files_skipped_checkpoint}"
        )
        assert report2.files_ingested == 0, (
            f"Expected 0 new ingestions on second run, got {report2.files_ingested}"
        )

        count_after_second = writer.count()
        assert count_after_second == count_after_first, (
            f"Qdrant count changed on second run: {count_after_first} → {count_after_second}"
        )


def test_rerun_without_checkpoint_does_not_increase_count(embedding_service, writer) -> None:
    """Re-ingesting a file without checkpoint must not duplicate Qdrant points (idempotent)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        checkpoint = Path(tmpdir) / "fresh.json"
        # Use a fresh checkpoint so all files are re-ingested
        count_before = writer.count()
        ingest_law_file(_SK_PATH, embedder=RussianLawEmbedder(embedding_service), writer=writer)
        count_after = writer.count()
        assert count_after == count_before, (
            f"Re-ingest of SK changed point count: {count_before} → {count_after}"
        )


# ---------------------------------------------------------------------------
# Unrecognized file handling
# ---------------------------------------------------------------------------

def test_unrecognized_file_is_skipped(embedding_service) -> None:
    """A directory containing only an unrecognized .txt file produces 0 ingested files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_dir = Path(tmpdir)
        # Create a .txt file with an unrecognized name
        (fake_dir / "some_random_document.txt").write_bytes(
            "Содержание документа".encode("utf-16")
        )
        checkpoint = fake_dir / "cp.json"
        report = ingest_corpus(
            directory=fake_dir,
            embedding_service=embedding_service,
            qdrant_url=QDRANT_URL,
            batch_size=64,
            checkpoint_path=checkpoint,
            verbose=False,
        )
        assert report.files_unrecognized == 1, (
            f"Expected 1 unrecognized file, got {report.files_unrecognized}"
        )
        assert report.files_ingested == 0
