"""Result models produced by the review services."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from pydantic import Field, field_validator

from app.models.base import ToolModel
from app.models.party import PartyScreeningResult, PartyToScreen
from app.models.product import ProductInformation
from app.models.transaction import TransactionIntake

# --- Step 3: EAR jurisdiction -------------------------------------------------
JURISDICTION_POSSIBLE = "POSSIBLE_EAR_JURISDICTION"
JURISDICTION_REVIEW_REQUIRED = "JURISDICTION_REVIEW_REQUIRED"
JURISDICTION_INSUFFICIENT = "INSUFFICIENT_INFORMATION"

JURISDICTION_STATUS_OPTIONS = [
    JURISDICTION_POSSIBLE,
    JURISDICTION_REVIEW_REQUIRED,
    JURISDICTION_INSUFFICIENT,
]


class JurisdictionQuestionSet(ToolModel):
    is_us_origin: bool | None = None
    has_us_origin_content: bool | None = None
    us_content_value_known: bool | None = None
    total_foreign_value_known: bool | None = None
    us_software_used_in_production: bool | None = None
    us_technology_used_in_production: bool | None = None
    production_chain_known: bool | None = None
    additional_notes: str = ""


class JurisdictionReviewResult(ToolModel):
    status: str
    status_label: str = ""
    path: str = ""
    summary: str = ""
    reasons: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


# --- Step 4: De Minimis -------------------------------------------------------
DE_MINIMIS_COMPUTED = "COMPUTED"
DE_MINIMIS_NO_CONTROLLED_US_CONTENT = "NO_CONTROLLED_US_CONTENT"
DE_MINIMIS_MISSING_VALUE = "MISSING_VALUE"
DE_MINIMIS_MISSING_TOTAL = "MISSING_TOTAL"
DE_MINIMIS_MISSING_INPUT = "MISSING_INPUT"


class DeMinimisComponent(ToolModel):
    component_name: str = Field(..., min_length=1, max_length=300)
    origin: str | None = Field(default=None, max_length=100)
    eccn: str | None = Field(default=None, max_length=20)
    controlled_status: str = Field(default="Unknown", max_length=40)
    component_value: Decimal | None = Field(default=None, ge=0)
    # Whether the component is incorporated into the item (counts for de minimis) or
    # was only used in the production process (an FDP question). None = not recorded.
    incorporated: bool | None = None

    @field_validator("component_name", "origin", "eccn", mode="before")
    @classmethod
    def _clean(cls, value):
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None

    @field_validator("component_value", mode="before")
    @classmethod
    def _blank_value(cls, value):
        if value in ("", None):
            return None
        return value

    @field_validator("eccn", mode="after")
    @classmethod
    def _upper_eccn(cls, value):
        return value.upper() if value else value

    @field_validator("incorporated", mode="before")
    @classmethod
    def _blank_bool(cls, value):
        if value in ("", None):
            return None
        if isinstance(value, bool):
            return value
        text = str(value).strip().casefold()
        if text.startswith("unknown") or text in {"n/a", "na", "tbd"}:
            return None
        if text.startswith("yes") or text.startswith("true"):
            return True
        if text.startswith("no") or text.startswith("false"):
            return False
        return None


class DeMinimisResult(ToolModel):
    status: str = DE_MINIMIS_MISSING_INPUT
    components: list[DeMinimisComponent] = Field(default_factory=list)
    controlled_us_content_value: Decimal | None = None
    total_foreign_product_value: Decimal | None = None
    ratio: Decimal | None = None
    ratio_percent: Decimal | None = None
    excluded_components: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


# --- Step 5: FDP review -------------------------------------------------------
FDP_NO_FACTS = "NO_FDP_FACTS_IDENTIFIED"
FDP_POTENTIAL = "POTENTIAL_FDP_ISSUE"
FDP_INSUFFICIENT = "INSUFFICIENT_INFORMATION"

FDP_FLAG_OPTIONS = [FDP_NO_FACTS, FDP_POTENTIAL, FDP_INSUFFICIENT]


class FDPReviewInput(ToolModel):
    us_software_used: str = Field(default="", max_length=2000)
    us_technology_used: str = Field(default="", max_length=2000)
    foreign_production_facilities: str = Field(default="", max_length=3000)
    production_equipment: str = Field(default="", max_length=3000)
    production_process_description: str = Field(default="", max_length=5000)


class DependencyMapEntry(ToolModel):
    layer: str
    details: str
    source: str = ""


class FDPReviewResult(ToolModel):
    flag: str = FDP_NO_FACTS
    flag_label: str = "NO FDP FACTS IDENTIFIED"
    dependency_map: list[DependencyMapEntry] = Field(default_factory=list)
    summary: str = ""
    missing_information: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


# --- Step 7: End use review ---------------------------------------------------
END_USE_FLAG_INSUFFICIENT = "insufficient_end_use_information"
END_USE_FLAG_INCONSISTENT = "inconsistent_business_activity"
END_USE_FLAG_MILITARY = "military_related_indicators"
END_USE_FLAG_LOCATION = "unclear_installation_location"


class EndUseFlag(ToolModel):
    key: str
    label: str
    detail: str
    requires_review: bool = True


class EndUseReviewInput(ToolModel):
    declared_end_use: str = Field(default="", max_length=4000)
    installation_location: str = Field(default="", max_length=2000)
    industry: str = Field(default="", max_length=200)
    civil_use: bool = False
    military_use: bool = False
    aerospace_use: bool = False
    semiconductor_use: bool = False
    research_use: bool = False
    unknown_use: bool = False
    additional_notes: str = Field(default="", max_length=3000)


class EndUseReviewResult(ToolModel):
    input: EndUseReviewInput
    flags: list[EndUseFlag] = Field(default_factory=list)
    summary: str = ""


# --- Step 8/9: Red flags and risk ---------------------------------------------
class RedFlagFinding(ToolModel):
    rule_id: str
    name: str
    risk_points: Decimal = Decimal("0")
    action: str = "REVIEW"
    explanation: str = ""
    condition: str = ""


class RedFlagResult(ToolModel):
    findings: list[RedFlagFinding] = Field(default_factory=list)
    total_points: Decimal = Decimal("0")
    rule_count: int = 0


class RiskFinding(ToolModel):
    rule_id: str
    name: str
    points: Decimal = Decimal("0")
    explanation: str = ""


class RiskCategoryScore(ToolModel):
    key: str
    label: str
    max_points: Decimal
    points: Decimal = Decimal("0")
    findings: list[RiskFinding] = Field(default_factory=list)
    explanation_lines: list[str] = Field(default_factory=list)


class RiskAssessment(ToolModel):
    categories: dict[str, RiskCategoryScore] = Field(default_factory=dict)
    total: Decimal = Decimal("0")
    max_total: Decimal = Decimal("100")
    level: str = "NOT_RUN"
    level_label: str = "Not run"
    methodology: str = ""


class ReviewQueueDecision(ToolModel):
    decision: str = "AUTO_REVIEW_COMPLETE"
    decision_label: str = "AUTO REVIEW COMPLETE"
    matched_rule_id: str = ""
    matched_rule_name: str = ""
    explanation: str = ""
    rationale: list[str] = Field(default_factory=list)


# --- Report bundle ------------------------------------------------------------
class ReviewBundle(ToolModel):
    transaction: TransactionIntake | None = None
    product: ProductInformation | None = None
    jurisdiction_questions: JurisdictionQuestionSet | None = None
    jurisdiction: JurisdictionReviewResult | None = None
    deminimis: DeMinimisResult | None = None
    fdp: FDPReviewResult | None = None
    parties: list[PartyToScreen] = Field(default_factory=list)
    screening: list[PartyScreeningResult] = Field(default_factory=list)
    end_use: EndUseReviewResult | None = None
    red_flags: RedFlagResult | None = None
    risk: RiskAssessment | None = None
    queue: ReviewQueueDecision | None = None
    legal_review_notes: str = ""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
