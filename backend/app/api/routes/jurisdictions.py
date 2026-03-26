from fastapi import APIRouter, Depends

from app.core.dependencies import get_jurisdiction_registry
from app.modules.common.graph.schemas import JurisdictionInfo
from app.modules.registry import JurisdictionRegistry


router = APIRouter()


@router.get("/jurisdictions", response_model=list[JurisdictionInfo])
def list_jurisdictions(
    registry: JurisdictionRegistry = Depends(get_jurisdiction_registry),
):
    return [
        JurisdictionInfo(
            country=descriptor.country,
            label=descriptor.label,
            description=descriptor.description,
            supported_domains=list(descriptor.supported_domains),
        )
        for descriptor in registry.list_descriptors()
    ]
