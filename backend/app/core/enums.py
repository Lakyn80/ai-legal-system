from enum import Enum


class CountryEnum(str, Enum):
    RUSSIA = "russia"
    CZECHIA = "czechia"


class DomainEnum(str, Enum):
    COURTS = "courts"
    LAW = "law"


class DocumentStatusEnum(str, Enum):
    UPLOADED = "uploaded"
    INGESTED = "ingested"
    FAILED = "failed"
