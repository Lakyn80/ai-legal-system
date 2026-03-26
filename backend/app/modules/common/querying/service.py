from app.core.enums import CountryEnum, DomainEnum
from app.modules.common.querying.classifier import QueryClassifier
from app.modules.common.querying.normalizer import QueryNormalizer
from app.modules.common.querying.schemas import QueryContext
from app.modules.registry import JurisdictionRegistry


class QueryProcessingService:
    def __init__(
        self,
        registry: JurisdictionRegistry,
        normalizer: QueryNormalizer | None = None,
        classifier: QueryClassifier | None = None,
    ) -> None:
        self.registry = registry
        self.normalizer = normalizer or QueryNormalizer()
        self.classifier = classifier or QueryClassifier()

    def process(
        self,
        query: str,
        requested_country: CountryEnum | None = None,
        requested_domain: DomainEnum | None = None,
    ) -> QueryContext:
        descriptor = self.registry.resolve(requested_country, query)
        normalized_query = self.normalizer.normalize(query)
        keyword_terms = self.normalizer.keyword_terms(query)
        query_type = self.classifier.classify(normalized_query, keyword_terms)
        detected_domain = requested_domain or self.classifier.detect_domain(
            normalized_query,
            keyword_terms,
            query_type,
        )
        citation_patterns = self.classifier.find_citation_patterns(normalized_query)

        return QueryContext(
            raw_query=query,
            normalized_query=normalized_query,
            query_hash=self.normalizer.hash_query(normalized_query),
            query_type=query_type,
            domain=detected_domain,
            jurisdiction=descriptor.country,
            citation_patterns=citation_patterns,
            keyword_terms=keyword_terms,
            expects_deterministic_answer=query_type.value in {"exact_statute", "case_lookup"},
        )
