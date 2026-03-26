from app.core.enums import CountryEnum, DomainEnum
from app.modules.contracts import JurisdictionDescriptor
from app.modules.czechia.graph.workflow import build_czechia_strategy_graph
from app.modules.czechia.prompts.strategy_prompts import CZECHIA_STRATEGY_PROMPT
from app.modules.czechia.schemas.profile import CzechiaJurisdictionProfile


def get_czechia_descriptor() -> JurisdictionDescriptor:
    profile = CzechiaJurisdictionProfile()
    return JurisdictionDescriptor(
        country=CountryEnum.CZECHIA,
        label=profile.label,
        description=profile.description,
        supported_domains=(DomainEnum.COURTS, DomainEnum.LAW),
        system_prompt=CZECHIA_STRATEGY_PROMPT,
        law_focus=profile.law_focus,
        court_focus=profile.court_focus,
        missing_document_hints=tuple(profile.missing_document_hints),
        graph_builder=build_czechia_strategy_graph,
    )
