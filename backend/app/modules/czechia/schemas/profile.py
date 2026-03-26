from pydantic import BaseModel, Field


class CzechiaJurisdictionProfile(BaseModel):
    label: str = "Czechia"
    description: str = "Czech law and court-practice strategy module for disputes and court files."
    law_focus: str = "Czech statutory interpretation and procedural compliance"
    court_focus: str = "positions of Czech courts including higher-instance review"
    missing_document_hints: list[str] = Field(
        default_factory=lambda: [
            "Primary contracts, appendices and communication proving obligations.",
            "Procedural orders, deadlines and court submissions.",
            "Relevant statutory provisions and explanatory context relied on by the parties.",
        ]
    )
