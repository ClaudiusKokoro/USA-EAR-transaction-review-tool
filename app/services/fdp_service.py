"""Foreign Direct Product (FDP) review service (Step 5)."""

from __future__ import annotations

from app.models.review import (
    FDP_INSUFFICIENT,
    FDP_NO_FACTS,
    FDP_POTENTIAL,
    DependencyMapEntry,
    FDPReviewInput,
    FDPReviewResult,
)

FLAG_LABELS = {
    FDP_NO_FACTS: "NO FDP FACTS IDENTIFIED",
    FDP_POTENTIAL: "POTENTIAL FDP ISSUE",
    FDP_INSUFFICIENT: "INSUFFICIENT INFORMATION",
}


def _lines(value: str | None) -> list[str]:
    return [line.strip() for line in (value or "").splitlines() if line.strip()]


def _clean_text(value: str | None) -> str:
    return " ".join((value or "").split())


def run_fdp_review(value: FDPReviewInput | dict) -> FDPReviewResult:
    review_input = value if isinstance(value, FDPReviewInput) else FDPReviewInput.model_validate(value or {})

    software = _clean_text(review_input.us_software_used)
    technology = _clean_text(review_input.us_technology_used)
    facilities = _lines(review_input.foreign_production_facilities)
    equipment = _lines(review_input.production_equipment)
    process = _clean_text(review_input.production_process_description)

    has_us_inputs = bool(software or technology)
    has_production_facts = bool(facilities or equipment or process)
    dependency_map: list[DependencyMapEntry] = []
    missing: list[str] = []
    notes: list[str] = []

    for index, facility in enumerate(facilities, start=1):
        dependency_map.append(DependencyMapEntry(layer="Foreign production facility", details=facility, source=f"facility {index}"))
    for index, item in enumerate(equipment, start=1):
        dependency_map.append(DependencyMapEntry(layer="Production equipment", details=item, source=f"equipment {index}"))
    if process:
        dependency_map.append(DependencyMapEntry(layer="Production process", details=process, source="process description"))
    if software:
        dependency_map.append(DependencyMapEntry(layer="U.S.-origin software (recorded)", details=software, source="Step 5 input"))
    if technology:
        dependency_map.append(DependencyMapEntry(layer="U.S.-origin technology (recorded)", details=technology, source="Step 5 input"))

    if not has_production_facts and not has_us_inputs:
        return FDPReviewResult(
            flag=FDP_NO_FACTS,
            flag_label=FLAG_LABELS[FDP_NO_FACTS],
            dependency_map=[],
            summary="No foreign-production or U.S.-origin production-input facts were provided.",
            notes=[
                "If the item is foreign-produced, record the production chain and any U.S.-origin software, "
                "technology, or equipment used in production before closing the FDP review."
            ],
        )

    if has_us_inputs and not has_production_facts:
        missing.extend(
            [
                "foreign production facilities or locations",
                "production equipment",
                "a description of the production process",
            ]
        )
        return FDPReviewResult(
            flag=FDP_INSUFFICIENT,
            flag_label=FLAG_LABELS[FDP_INSUFFICIENT],
            dependency_map=dependency_map,
            summary="U.S.-origin software or technology was recorded, but the foreign production chain was not described.",
            missing_information=missing,
            notes=[
                "Describe the foreign production facilities, equipment, and process so the dependency map can be completed."
            ],
        )

    if has_us_inputs and has_production_facts:
        notes.append(
            "A potential FDP issue exists when a foreign-produced item is produced with U.S.-origin software, "
            "technology, or certain equipment. Applicability of any Foreign Direct Product rule requires legal review."
        )
        return FDPReviewResult(
            flag=FDP_POTENTIAL,
            flag_label=FLAG_LABELS[FDP_POTENTIAL],
            dependency_map=dependency_map,
            summary="The foreign-produced item may depend on U.S.-origin production inputs; FDP rule applicability requires legal review.",
            notes=notes,
        )

    # Production facts exist but no U.S.-origin production inputs were recorded.
    return FDPReviewResult(
        flag=FDP_NO_FACTS,
        flag_label=FLAG_LABELS[FDP_NO_FACTS],
        dependency_map=dependency_map,
        summary="Foreign production facts were provided, but no U.S.-origin software or technology inputs were recorded.",
        notes=[
            "Re-confirm whether any U.S.-origin software, technology, or equipment was used in the production chain."
        ],
    )

