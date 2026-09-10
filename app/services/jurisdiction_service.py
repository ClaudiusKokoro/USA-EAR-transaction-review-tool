"""EAR jurisdiction review service (Step 3).

The service deliberately never concludes that an item is or is not within EAR
jurisdiction. It classifies the recorded facts into one of three internal
review states: POSSIBLE EAR JURISDICTION, JURISDICTION REVIEW REQUIRED, or
INSUFFICIENT INFORMATION.
"""

from __future__ import annotations

from app.models.review import (
    JURISDICTION_INSUFFICIENT,
    JURISDICTION_POSSIBLE,
    JURISDICTION_REVIEW_REQUIRED,
    JurisdictionQuestionSet,
    JurisdictionReviewResult,
)

STATUS_LABELS = {
    JURISDICTION_POSSIBLE: "POSSIBLE EAR JURISDICTION",
    JURISDICTION_REVIEW_REQUIRED: "JURISDICTION REVIEW REQUIRED",
    JURISDICTION_INSUFFICIENT: "INSUFFICIENT INFORMATION",
}

PATH_LABELS = {
    "US_ORIGIN": "Item recorded as U.S.-origin",
    "FOREIGN_US_CONTENT": "Foreign-produced item with U.S.-origin content",
    "FOREIGN_US_PRODUCTION_INPUTS": "Foreign-produced item with possible U.S.-origin production inputs",
    "FOREIGN_NO_US_NEXUS": "Foreign-produced item with no U.S.-origin nexus identified from recorded facts",
    "UNKNOWN": "Jurisdiction facts incomplete",
}


def _as_questions(value: JurisdictionQuestionSet | dict) -> JurisdictionQuestionSet:
    if isinstance(value, JurisdictionQuestionSet):
        return value
    return JurisdictionQuestionSet.model_validate(value or {})


def run_jurisdiction_review(
    questions: JurisdictionQuestionSet | dict,
) -> JurisdictionReviewResult:
    """Preliminarily classify the jurisdiction review state from recorded facts."""

    q = _as_questions(questions)
    missing: list[str] = []
    reasons: list[str] = []
    next_steps: list[str] = [
        "Review the item's classification and the current text of the EAR before relying on this preliminary assessment.",
        "If U.S.-origin content or U.S.-origin production inputs are present, complete the de minimis and Foreign Direct Product steps.",
    ]

    if q.is_us_origin is None:
        missing.append("whether the item is U.S.-origin")

    if q.is_us_origin is not True:
        if q.has_us_origin_content is None:
            missing.append("whether the item contains U.S.-origin content")
        elif q.has_us_origin_content is True:
            if q.us_content_value_known is None:
                missing.append("whether the value of U.S.-origin controlled content is known")
            elif q.us_content_value_known is False:
                missing.append("the value of the U.S.-origin controlled content")
            if q.total_foreign_value_known is None:
                missing.append("whether the total value of the foreign-produced item is known")
            elif q.total_foreign_value_known is False:
                missing.append("the total value of the foreign-produced item")
        else:
            if q.us_software_used_in_production is None:
                missing.append("whether U.S.-origin software was used in the production chain")
            if q.us_technology_used_in_production is None:
                missing.append("whether U.S.-origin technology was used in the production chain")
            if q.production_chain_known is None:
                missing.append("whether the production chain is fully known")

    if q.is_us_origin is True and q.production_chain_known is None:
        # Production-chain detail is still useful for a U.S.-origin item, but it is
        # not needed to establish the preliminary U.S.-origin state.
        next_steps.append("Record whether the production chain is known so reexport and foreign-build questions can be assessed.")

    if q.is_us_origin is None:
        return JurisdictionReviewResult(
            status=JURISDICTION_INSUFFICIENT,
            status_label=STATUS_LABELS[JURISDICTION_INSUFFICIENT],
            path="UNKNOWN",
            summary="The recorded facts are insufficient to preliminarily assess whether the item may be within EAR jurisdiction.",
            reasons=[
                "The key question of whether the item is U.S.-origin was not answered.",
            ],
            missing_information=missing,
            next_steps=next_steps,
        )

    if q.is_us_origin is True:
        reasons.append(
            "The item is recorded as U.S.-origin. U.S.-origin items are commonly within EAR jurisdiction, "
            "but whether this item is subject to the EAR and whether a license is required requires classification "
            "and review of the current regulations."
        )
        if missing:
            reasons.append("The following related facts are still missing: " + ", ".join(missing) + ".")
        return JurisdictionReviewResult(
            status=JURISDICTION_POSSIBLE,
            status_label=STATUS_LABELS[JURISDICTION_POSSIBLE],
            path="US_ORIGIN",
            summary="The item is recorded as U.S.-origin; EAR jurisdiction remains possible based on the recorded facts.",
            reasons=reasons,
            missing_information=missing,
            next_steps=next_steps,
        )

    # Foreign-produced item path.
    if q.has_us_origin_content is None:
        return JurisdictionReviewResult(
            status=JURISDICTION_INSUFFICIENT,
            status_label=STATUS_LABELS[JURISDICTION_INSUFFICIENT],
            path="UNKNOWN",
            summary="The recorded facts do not say whether the foreign-produced item contains U.S.-origin content.",
            reasons=["The question about U.S.-origin content was not answered."],
            missing_information=missing,
            next_steps=next_steps,
        )

    if q.has_us_origin_content is True:
        if q.us_content_value_known is False or q.total_foreign_value_known is False:
            reasons.append(
                "The foreign-produced item contains U.S.-origin content, but the value facts needed to run a "
                "de minimis calculation are incomplete. The preliminary jurisdiction state therefore requires "
                "a formal review."
            )
            return JurisdictionReviewResult(
                status=JURISDICTION_REVIEW_REQUIRED,
                status_label=STATUS_LABELS[JURISDICTION_REVIEW_REQUIRED],
                path="FOREIGN_US_CONTENT",
                summary="The item is foreign-produced and contains U.S.-origin content, but value facts are incomplete.",
                reasons=reasons,
                missing_information=missing,
                next_steps=[
                    "Collect the value of each U.S.-origin controlled component and the total value of the foreign-produced item.",
                    "Complete the de minimis calculation and legal review of the applicable threshold.",
                ],
            )
        reasons.append(
            "The foreign-produced item contains U.S.-origin content whose value is recorded as known. "
            "Complete the de minimis calculation; the applicable threshold is a legal determination requiring review."
        )
        return JurisdictionReviewResult(
            status=JURISDICTION_POSSIBLE,
            status_label=STATUS_LABELS[JURISDICTION_POSSIBLE],
            path="FOREIGN_US_CONTENT",
            summary="Foreign-produced item with recorded U.S.-origin content; EAR jurisdiction remains possible.",
            reasons=reasons,
            missing_information=missing,
            next_steps=next_steps,
        )

    # No U.S.-origin content recorded.
    uses_us_production_inputs = bool(q.us_software_used_in_production or q.us_technology_used_in_production)
    if q.production_chain_known is None:
        return JurisdictionReviewResult(
            status=JURISDICTION_INSUFFICIENT,
            status_label=STATUS_LABELS[JURISDICTION_INSUFFICIENT],
            path="UNKNOWN",
            summary="The production chain is not recorded as known, so possible U.S.-origin production inputs cannot be assessed.",
            reasons=[
                "A foreign-produced item without recorded U.S.-origin content can still be affected by U.S.-origin "
                "software or technology used in its production."
            ],
            missing_information=missing,
            next_steps=next_steps,
        )

    if uses_us_production_inputs:
        reasons.append(
            "U.S.-origin software or technology is recorded as used in the production of the foreign-produced item. "
            "EAR jurisdiction therefore remains possible and the Foreign Direct Product step should be completed."
        )
        return JurisdictionReviewResult(
            status=JURISDICTION_POSSIBLE,
            status_label=STATUS_LABELS[JURISDICTION_POSSIBLE],
            path="FOREIGN_US_PRODUCTION_INPUTS",
            summary="Possible U.S.-origin production inputs were recorded for a foreign-produced item.",
            reasons=reasons,
            missing_information=missing,
            next_steps=next_steps,
        )

    reasons.append(
        "No U.S.-origin nexus (content, software, or technology) was identified from the recorded facts. "
        "This tool does not determine whether the item is outside EAR jurisdiction; a formal jurisdiction review "
        "is required before relying on that conclusion."
    )
    return JurisdictionReviewResult(
        status=JURISDICTION_REVIEW_REQUIRED,
        status_label=STATUS_LABELS[JURISDICTION_REVIEW_REQUIRED],
        path="FOREIGN_NO_US_NEXUS",
        summary="No U.S.-origin nexus was identified from the recorded facts; formal review is required to close jurisdiction.",
        reasons=reasons,
        missing_information=missing,
        next_steps=next_steps,
    )


def describe_status(status: str) -> str:
    return STATUS_LABELS.get(status, status)

