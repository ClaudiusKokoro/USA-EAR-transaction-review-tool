"""Party screening data models (Step 6)."""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field, field_validator

from app.models.base import ToolModel

SCREENING_NO_APPARENT_MATCH = "NO_APPARENT_MATCH"
SCREENING_POSSIBLE_MATCH = "POSSIBLE_MATCH"
SCREENING_MANUAL_VERIFICATION = "MANUAL_VERIFICATION_REQUIRED"

SCREENING_STATUS_OPTIONS = [
    SCREENING_NO_APPARENT_MATCH,
    SCREENING_POSSIBLE_MATCH,
    SCREENING_MANUAL_VERIFICATION,
]


class PartyToScreen(ToolModel):
    name: str = Field(..., min_length=1, max_length=300)
    role: str = Field(..., min_length=1, max_length=50)
    country: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=500)

    @field_validator("name", "role", "address", mode="before")
    @classmethod
    def _clean(cls, value):
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None


class ScreeningMatch(ToolModel):
    matched_name: str
    score: Decimal = Field(default=0, ge=0, le=1)
    match_method: str
    listed_country: str | None = None
    listed_reference: str | None = None
    listed_source: str | None = None
    listed_notes: str | None = None


class PartyScreeningResult(ToolModel):
    party: PartyToScreen
    status: str = SCREENING_NO_APPARENT_MATCH
    best_score: Decimal = Decimal("0")
    best_match: ScreeningMatch | None = None
    matches: list[ScreeningMatch] = Field(default_factory=list)
    explanation: str = ""


class ScreeningInput(ToolModel):
    parties: list[PartyToScreen] = Field(default_factory=list)


class ScreeningOutput(ToolModel):
    results: list[PartyScreeningResult] = Field(default_factory=list)
    source_files: list[str] = Field(default_factory=list)
    record_count: int = 0
