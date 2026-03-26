from app.core.enums import CountryEnum, DomainEnum
from app.modules.common.querying.schemas import QueryType
from app.modules.common.querying.service import QueryProcessingService
from app.modules.registry import JurisdictionRegistry


def build_service() -> QueryProcessingService:
    return QueryProcessingService(registry=JurisdictionRegistry())


def test_query_processing_detects_exact_statute():
    service = build_service()

    context = service.process("§ 655 občanský zákoník")

    assert context.query_type == QueryType.EXACT_STATUTE
    assert context.domain == DomainEnum.LAW
    assert context.jurisdiction == CountryEnum.CZECHIA
    assert context.expects_deterministic_answer is True


def test_query_processing_detects_case_lookup():
    service = build_service()

    context = service.process("sp. zn. 23 Cdo 123/2023 rozhodnutí Nejvyššího soudu")

    assert context.query_type == QueryType.CASE_LOOKUP
    assert context.domain == DomainEnum.COURTS


def test_query_processing_detects_strategy_query():
    service = build_service()

    context = service.process("Navrhni strategii sporu o vypořádání společného jmění manželů")

    assert context.query_type == QueryType.STRATEGY
    assert context.domain is None
    assert context.expects_deterministic_answer is False
