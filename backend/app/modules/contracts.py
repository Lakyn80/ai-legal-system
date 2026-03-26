from dataclasses import dataclass
from typing import Any, Callable

from app.core.enums import CountryEnum, DomainEnum


@dataclass(frozen=True)
class JurisdictionDescriptor:
    country: CountryEnum
    label: str
    description: str
    supported_domains: tuple[DomainEnum, ...]
    system_prompt: str
    law_focus: str
    court_focus: str
    missing_document_hints: tuple[str, ...]
    graph_builder: Callable[[Any], Any]
