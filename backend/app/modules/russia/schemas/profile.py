from pydantic import BaseModel, Field


class RussiaJurisdictionProfile(BaseModel):
    label: str = "Russia"
    description: str = "Russian law and court-practice strategy module for disputes and court files."
    law_focus: str = "Russian statutory hierarchy and procedural requirements"
    court_focus: str = "positions of Russian courts and higher-instance guidance"
    missing_document_hints: list[str] = Field(
        default_factory=lambda: [
            "Signed contracts, amendments and annexes relevant to the claim.",
            "Procedural submissions, motions and hearing protocols.",
            "Applicable federal statutes or code provisions cited in pleadings.",
        ]
    )
