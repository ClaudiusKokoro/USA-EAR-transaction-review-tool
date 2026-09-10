"""De minimis calculator service (Step 4).

The service computes the ratio of U.S.-origin controlled content value to the
total value of the foreign-produced item. It never states what the applicable
legal threshold is, because the threshold depends on current regulatory text
and the ECCNs involved.
"""

from __future__ import annotations

from decimal import Decimal

from app.models.review import (
    DE_MINIMIS_COMPUTED,
    DE_MINIMIS_MISSING_INPUT,
    DE_MINIMIS_MISSING_TOTAL,
    DE_MINIMIS_MISSING_VALUE,
    DE_MINIMIS_NO_CONTROLLED_US_CONTENT,
    DeMinimisComponent,
    DeMinimisResult,
)

LEGAL_WARNING = (
    "The applicable de minimis threshold is a legal determination that depends on the ECCNs, "
    "destinations, and current regulatory text. This ratio is preliminary and requires legal review; "
    "this tool never determines whether a license is required."
)

_US_ORIGIN_TERMS = {
    "us",
    "u.s.",
    "u s",
    "usa",
    "united states",
    "united states of america",
    "america",
}

_CONTROLLED_TERMS = {"yes", "true", "controlled", "y", "1", "is_controlled", "us-controlled"}
_UNCLEAR_TERMS = {"", "unknown", "n/a", "na", "tbd", "unsure"}


def _normalize(text: str | None) -> str:
    if text is None:
        return ""
    return " ".join(str(text).lower().replace("_", " ").split())


def _is_us_origin(text: str | None) -> bool:
    return _normalize(text) in _US_ORIGIN_TERMS or _normalize(text).startswith("u.s")


def _is_controlled(text: str | None) -> bool:
    normalized = _normalize(text).replace("-", " ")
    if not normalized or normalized in _UNCLEAR_TERMS:
        return False
    if normalized.startswith("no") or "ear99" in normalized:
        return False
    if normalized.startswith("yes") or "controlled" in normalized:
        return True
    return normalized in _CONTROLLED_TERMS


def _is_unclear(text: str | None) -> bool:
    normalized = _normalize(text)
    # "未回答" is kept as a legacy alias so review data saved by older,
    # bilingual versions of the tool still parses correctly.
    return normalized in _UNCLEAR_TERMS or "unknown" in normalized or "未回答" in (text or "")


def _value_of(value: Decimal | None) -> Decimal | None:
    return value if value is not None else None


def run_de_minimis(
    components: list[DeMinimisComponent | dict],
    total_foreign_product_value: Decimal | float | int | str | None = None,
) -> DeMinimisResult:
    """Calculate the preliminary U.S.-origin controlled content ratio."""

    parsed: list[DeMinimisComponent] = []
    for component in components or []:
        if isinstance(component, DeMinimisComponent):
            parsed.append(component)
        else:
            parsed.append(DeMinimisComponent.model_validate(component))

    result = DeMinimisResult(
        status=DE_MINIMIS_COMPUTED,
        components=parsed,
        total_foreign_product_value=total_foreign_product_value,
        warnings=[LEGAL_WARNING],
    )

    if total_foreign_product_value in (None, ""):
        result.status = DE_MINIMIS_MISSING_TOTAL
        result.warnings.append("The total value of the foreign-produced item was not provided, so no ratio can be calculated.")
        return result

    try:
        total_value = Decimal(str(total_foreign_product_value))
    except Exception:
        result.status = DE_MINIMIS_MISSING_TOTAL
        result.warnings.append("The total foreign-product value could not be interpreted as a number.")
        return result
    result.total_foreign_product_value = total_value

    if total_value <= 0:
        result.status = DE_MINIMIS_MISSING_TOTAL
        result.warnings.append("The total foreign-product value must be greater than zero.")
        return result

    if not parsed:
        result.status = DE_MINIMIS_MISSING_INPUT
        result.notes.append("No U.S.-origin controlled components were entered.")
        return result

    included_value = Decimal("0")
    missing_value_names: list[str] = []
    excluded: list[str] = []
    for component in parsed:
        is_us = _is_us_origin(component.origin)
        controlled = _is_controlled(component.controlled_status)
        if not is_us:
            excluded.append(
                f"{component.component_name} (origin '{component.origin or 'not provided'}' is not recognized as U.S.-origin)"
            )
            continue
        if controlled and component.component_value in (None, ""):
            missing_value_names.append(component.component_name)
            continue
        if controlled:
            included_value += component.component_value
            continue
        if _is_unclear(component.controlled_status):
            excluded.append(
                f"{component.component_name} (controlled status '{component.controlled_status or 'not provided'}' is unclear)"
            )
            result.warnings.append(
                f"Component '{component.component_name}' has an unclear controlled status and was excluded from the numerator. "
                "Confirm whether it is controlled under the EAR."
            )
        else:
            excluded.append(f"{component.component_name} (recorded as not controlled)")

    result.excluded_components = excluded
    result.controlled_us_content_value = included_value

    if missing_value_names:
        result.status = DE_MINIMIS_MISSING_VALUE
        result.warnings.append(
            "The value is missing for controlled U.S.-origin component(s): " + ", ".join(missing_value_names) + "."
        )
        result.notes.append("Add the missing component values before interpreting this calculation.")
        return result

    if included_value == 0:
        result.status = DE_MINIMIS_NO_CONTROLLED_US_CONTENT
        result.ratio = Decimal("0")
        result.ratio_percent = Decimal("0")
        result.notes.append(
            "No U.S.-origin controlled content value was included in the numerator. This can mean no such content "
            "was identified, or that all components were excluded for the reasons above."
        )
        return result

    ratio = included_value / total_value
    result.ratio = ratio
    result.ratio_percent = ratio * 100
    result.status = DE_MINIMIS_COMPUTED
    result.notes.append(
        "The ratio is: controlled U.S.-origin content value / total foreign-product value. "
        "Whether the applicable legal threshold is exceeded requires legal review."
    )
    return result
