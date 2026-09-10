"""End-use review service (Step 7)."""

from __future__ import annotations

from app.models.review import (
    END_USE_FLAG_INCONSISTENT,
    END_USE_FLAG_INSUFFICIENT,
    END_USE_FLAG_LOCATION,
    END_USE_FLAG_MILITARY,
    EndUseFlag,
    EndUseReviewInput,
    EndUseReviewResult,
)

# Terms that are strong enough to indicate a military or defense context on their own.
STRONG_MILITARY_TERMS = {
    "military",
    "military-grade",
    "defense",
    "defence",
    "defense-grade",
    "weapon",
    "weapons",
    "armament",
    "munitions",
    "ammunition",
    "missile",
    "missiles",
    "warhead",
    "combat",
    "firearm",
    "rifle",
    "artillery",
    "torpedo",
    "ballistic",
    "armored",
    "armoured",
    "warship",
    "night vision",
}

# Words that are commonly used in civilian software and consumer products. They are
# only treated as military indicators when a strong term appears in the same text
# (for example "audience targeting" versus "missile targeting").
WEAK_MILITARY_TERMS = {
    "guidance",
    "targeting",
    "radar",
    "drone",
    "uav",
    "rocket",
    "naval",
    "camouflage",
}

# Backwards-compatible union of every term, for callers that only need the vocabulary.
MILITARY_TERMS = STRONG_MILITARY_TERMS | WEAK_MILITARY_TERMS


def military_terms_found(text: str | None) -> list[str]:
    """Return the military terms in ``text``, ignoring weak terms without context."""

    lowered = " ".join(str(text or "").split()).casefold()
    if not lowered:
        return []
    strong_hits = sorted(term for term in STRONG_MILITARY_TERMS if term in lowered)
    if not strong_hits:
        return []
    weak_hits = sorted(term for term in WEAK_MILITARY_TERMS if term in lowered)
    return strong_hits + weak_hits


def contains_military_indicators(text: str | None) -> bool:
    return bool(military_terms_found(text))

VAGUE_LOCATION_TERMS = {"unknown", "n/a", "na", "tbd", "to be determined", "various", "anywhere", "not sure"}
INDUSTRY_KEYS = {
    "aerospace": {"aerospace", "aviation", "aircraft", "defense", "defence", "space", "satellite"},
    "military": {"military", "defense", "defence", "armed", "defence industry"},
    "semiconductor": {"semiconductor", "chip", "wafer", "microelectronic", "electronics"},
    "telecom": {"telecom", "telecommunication", "network", "wireless"},
}


def _clean(value: str | None) -> str:
    return " ".join((value or "").split()).casefold()


def _has_any_use_selected(input_: EndUseReviewInput) -> bool:
    return bool(
        input_.civil_use
        or input_.military_use
        or input_.aerospace_use
        or input_.semiconductor_use
        or input_.research_use
        or input_.unknown_use
    )


def run_end_use_review(value: EndUseReviewInput | dict) -> EndUseReviewResult:
    review_input = value if isinstance(value, EndUseReviewInput) else EndUseReviewInput.model_validate(value or {})
    flags: list[EndUseFlag] = []

    declared = _clean(review_input.declared_end_use)
    location = _clean(review_input.installation_location)
    industry = _clean(review_input.industry)

    military_text_hits = military_terms_found(" ".join(part for part in (declared, industry) if part))
    military_selected = review_input.military_use or review_input.aerospace_use

    # 1. Insufficient end-use information.
    if not declared or len(declared.split()) < 4:
        flags.append(
            EndUseFlag(
                key=END_USE_FLAG_INSUFFICIENT,
                label="Insufficient end-use information",
                detail=(
                    "The declared end use is missing or too general to support an end-use assessment. "
                    "Describe the actual use of the item by the end user."
                ),
            )
        )
    elif not _has_any_use_selected(review_input):
        flags.append(
            EndUseFlag(
                key=END_USE_FLAG_INSUFFICIENT,
                label="Insufficient end-use information",
                detail="No end-use category was selected even though a declared use was entered.",
            )
        )

    # 2. Inconsistent business activity.
    inconsistent_reasons: list[str] = []
    if declared and not industry:
        inconsistent_reasons.append("the buyer/exporter industry was not recorded")
    if (review_input.civil_use and review_input.military_use) or (
        review_input.civil_use and review_input.aerospace_use and "civil" not in declared
    ):
        inconsistent_reasons.append("both civil and military/aerospace end uses were selected without explanation")
    if industry and any(term in industry for term in ("civilian", "civil", "consumer")):
        if review_input.military_use or military_text_hits:
            inconsistent_reasons.append("the recorded industry is civilian while military-related indicators are present")
    if inconsistent_reasons:
        flags.append(
            EndUseFlag(
                key=END_USE_FLAG_INCONSISTENT,
                label="Inconsistent business activity",
                detail="The end-use or business activity facts appear inconsistent: " + "; ".join(inconsistent_reasons) + ".",
            )
        )

    # 3. Military-related indicators.
    if military_text_hits or military_selected:
        detail = "Military- or defense-related indicators were found"
        if military_text_hits:
            detail += " in the following term(s): " + ", ".join(sorted(set(military_text_hits))[:8]) + "."
        else:
            detail += " through the selected end-use category."
        flags.append(EndUseFlag(key=END_USE_FLAG_MILITARY, label="Military-related indicators", detail=detail))

    # 4. Unclear installation location.
    if not location:
        flags.append(
            EndUseFlag(
                key=END_USE_FLAG_LOCATION,
                label="Unclear installation location",
                detail="No installation location was provided.",
            )
        )
    elif location in VAGUE_LOCATION_TERMS or (len(location.split()) < 2 and not any(char.isdigit() for char in location)):
        flags.append(
            EndUseFlag(
                key=END_USE_FLAG_LOCATION,
                label="Unclear installation location",
                detail=f"The installation location '{review_input.installation_location.strip()}' is too vague to verify.",
            )
        )

    if flags:
        summary = "End-use review identified " + str(len(flags)) + " flag(s) requiring attention."
    else:
        summary = "No end-use flags were raised by the recorded facts and rules."
    return EndUseReviewResult(input=review_input, flags=flags, summary=summary)
