from app.core.enums import CountryEnum, DomainEnum
from app.modules.contracts import JurisdictionDescriptor
from app.modules.russia.graph.workflow import build_russia_strategy_graph
from app.modules.russia.prompts.strategy_prompts import RUSSIA_STRATEGY_PROMPT
from app.modules.russia.schemas.profile import RussiaJurisdictionProfile


def get_russia_descriptor() -> JurisdictionDescriptor:
    profile = RussiaJurisdictionProfile()
    return JurisdictionDescriptor(
        country=CountryEnum.RUSSIA,
        label=profile.label,
        description=profile.description,
        supported_domains=(DomainEnum.COURTS, DomainEnum.LAW),
        system_prompt=RUSSIA_STRATEGY_PROMPT,
        law_focus=profile.law_focus,
        court_focus=profile.court_focus,
        missing_document_hints=tuple(profile.missing_document_hints),
        graph_builder=build_russia_strategy_graph,
    )
