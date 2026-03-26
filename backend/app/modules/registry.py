from app.core.enums import CountryEnum
from app.core.exceptions import JurisdictionResolutionError
from app.modules.contracts import JurisdictionDescriptor
from app.modules.czechia.services.strategy import get_czechia_descriptor
from app.modules.russia.services.strategy import get_russia_descriptor


class JurisdictionRegistry:
    def __init__(self) -> None:
        descriptors = [
            get_russia_descriptor(),
            get_czechia_descriptor(),
        ]
        self._descriptors = {descriptor.country: descriptor for descriptor in descriptors}

    def list_descriptors(self) -> list[JurisdictionDescriptor]:
        return list(self._descriptors.values())

    def get(self, country: CountryEnum) -> JurisdictionDescriptor:
        if country not in self._descriptors:
            raise JurisdictionResolutionError(f"Unsupported jurisdiction: {country}")
        return self._descriptors[country]

    def resolve(self, country: CountryEnum | None, query: str) -> JurisdictionDescriptor:
        if country is not None:
            return self.get(country)

        if any("\u0400" <= char <= "\u04ff" for char in query):
            return self.get(CountryEnum.RUSSIA)

        return self.get(CountryEnum.CZECHIA)
