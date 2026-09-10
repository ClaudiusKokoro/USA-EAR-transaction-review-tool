"""Generate the EAR review benchmark dataset (benchmark/cases.json).

The dataset is written by hand as a compact Python description and expanded
from a clean baseline transaction, so every case only states what it varies.
Expectations are derived from the rule files in ``app/rules`` and are
deliberately conservative: a case only asserts what the rules make unambiguous.

Run:

    python benchmark/make_cases.py
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

BENCHMARK_DIR = Path(__file__).resolve().parent

BASE: dict = {
    "case_id": "",
    "title": "",
    "family": "",
    "difficulty": "easy",
    "is_control_case": False,
    "step1_transaction": {
        "transaction_name": "TEST-BASE",
        "exporter_name": "Northwind Instruments LLC",
        "exporter_country": "US",
        "buyer_name": "Rheinland Automation GmbH",
        "buyer_country": "DE",
        "consignee": "Rheinland Logistics Hub",
        "ultimate_end_user": "Bavaria Data Systems GmbH",
        "ultimate_destination": "DE",
        "transaction_value": 250000.0,
        "currency": "USD",
        "shipment_date": "2026-03-14",
        "notes": "Fictitious transaction used for benchmark testing.",
    },
    "step2_product": {
        "product_name": "NW-500 Industrial Process Controller",
        "model": "NW-500-A",
        "product_description": (
            "Programmable industrial process controller used for temperature and pressure "
            "regulation in food-processing plants; assembled in the United States from "
            "commercial-grade electronic components."
        ),
        "category": "Electronics",
        "manufacturer": "Northwind Instruments LLC",
        "country_of_manufacture": "US",
        "existing_eccn": None,
        "existing_ear_status": "EAR99",
        "product_value": 250000.0,
    },
    "step3_jurisdiction": {
        "is_us_origin": True,
        "has_us_origin_content": None,
        "us_content_value_known": None,
        "total_foreign_value_known": None,
        "us_software_used_in_production": None,
        "us_technology_used_in_production": None,
        "production_chain_known": True,
        "additional_notes": "",
    },
    "step4_deminimis": {
        "components": [],
        "total_foreign_product_value": None,
    },
    "step5_fdp": {
        "us_software_used": "",
        "us_technology_used": "",
        "foreign_production_facilities": "",
        "production_equipment": "",
        "production_process_description": "",
    },
    "step6_parties": {
        "parent_companies": [],
        "subsidiaries": [],
        "directors": [],
        "beneficial_owners": [],
    },
    "step7_end_use": {
        "declared_end_use": "Temperature and pressure regulation in a food-processing plant",
        "installation_location": "Munich, Germany",
        "industry": "Industrial automation",
        "civil_use": True,
        "military_use": False,
        "aerospace_use": False,
        "semiconductor_use": False,
        "research_use": False,
        "unknown_use": False,
        "additional_notes": "",
    },
    "expected": {},
    "known_issues": [],
    "reviewer_notes": "",
}


def _merge(target: dict, overrides: dict) -> None:
    for key, value in (overrides or {}).items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = value


def case(
    case_id: str,
    title: str,
    family: str,
    *,
    expected: dict | None = None,
    difficulty: str = "easy",
    control: bool = False,
    notes: str = "",
    known_issues: list[str] | None = None,
    step1: dict | None = None,
    step2: dict | None = None,
    step3: dict | None = None,
    step4: dict | None = None,
    step5: dict | None = None,
    step6: dict | None = None,
    step7: dict | None = None,
) -> dict:
    item = copy.deepcopy(BASE)
    item["case_id"] = case_id
    item["title"] = title
    item["family"] = family
    item["difficulty"] = difficulty
    item["is_control_case"] = control
    item["reviewer_notes"] = notes
    item["known_issues"] = list(known_issues or [])
    _merge(item["step1_transaction"], {"transaction_name": f"TEST-{case_id}", **(step1 or {})})
    _merge(item["step2_product"], step2 or {})
    _merge(item["step3_jurisdiction"], step3 or {})
    _merge(item["step4_deminimis"], step4 or {})
    _merge(item["step5_fdp"], step5 or {})
    _merge(item["step6_parties"], step6 or {})
    _merge(item["step7_end_use"], step7 or {})
    item["expected"] = expected or {}
    return item


def comp(
    name: str,
    origin: str,
    *,
    controlled: str = "Yes - controlled",
    value: float | None = None,
    eccn: str | None = None,
) -> dict:
    """Build one de minimis component row."""

    return {
        "component_name": name,
        "origin": origin,
        "eccn": eccn,
        "controlled_status": controlled,
        "component_value": value,
    }


def build_cases() -> list[dict]:
    cases: list[dict] = []

    # ------------------------------------------------------------------ clean
    clean_expected = {
        "jurisdiction_status": "POSSIBLE_EAR_JURISDICTION",
        "fdp_flag": "NO_FDP_FACTS_IDENTIFIED",
        "end_use_flags_exact": [],
        "red_flags_should_not_include": ["RF001", "RF002", "RF003", "RF004", "RF005", "RF007", "RF008", "RF009"],
        "risk_level_exact": "LOW",
        "queue_decision": "AUTO_REVIEW_COMPLETE",
    }
    cases.append(
        case(
            "CLN-01",
            "Plain-vanilla U.S.-origin EAR99 controller sold to Germany",
            "clean_control",
            expected={**clean_expected, "screening": {"Rheinland Automation GmbH": "NO_APPARENT_MATCH"}},
            control=True,
            notes="Baseline control: complete facts, no U.S. content questions, no red flags expected.",
        )
    )
    cases.append(
        case(
            "CLN-02",
            "U.S.-origin test instrument exported to Japan",
            "clean_control",
            expected=clean_expected,
            control=True,
            step1={
                "buyer_name": "Kyoto Precision Instruments KK",
                "buyer_country": "JP",
                "consignee": "Kyoto Distribution Centre",
                "ultimate_end_user": "Osaka Metrology Services KK",
                "ultimate_destination": "JP",
            },
            step2={
                "product_name": "NW-210 Bench Multimeter",
                "product_description": (
                    "Benchtop digital multimeter for calibration laboratories, shipped with "
                    "standard commercial firmware and no encryption features."
                ),
            },
            step7={"installation_location": "Osaka, Japan", "industry": "Metrology services"},
        )
    )
    cases.append(
        case(
            "CLN-03",
            "Canadian distributor purchase of U.S.-origin EAR99 parts",
            "clean_control",
            expected=clean_expected,
            control=True,
            step1={
                "buyer_name": "Toronto Industrial Supply Ltd.",
                "buyer_country": "CA",
                "consignee": "Toronto Industrial Supply Warehouse",
                "ultimate_end_user": "Ontario Food Processing Inc.",
                "ultimate_destination": "CA",
            },
            step7={"installation_location": "Toronto, Canada"},
        )
    )
    cases.append(
        case(
            "CLN-04",
            "U.S.-origin controlled ECCN item with a verified ECCN on file",
            "clean_control",
            expected={**clean_expected, "risk_level_exact": "LOW"},
            control=True,
            step2={"existing_eccn": "3A001", "existing_ear_status": "Controlled (ECCN)"},
            notes="Controlled classification is recorded, so no 'missing ECCN' points should be added.",
        )
    )
    cases.append(
        case(
            "CLN-05",
            "Ordinary commercial transaction to the United Kingdom",
            "clean_control",
            expected=clean_expected,
            control=True,
            step1={
                "buyer_name": "Bristol Machine Tools Ltd.",
                "buyer_country": "GB",
                "ultimate_end_user": "Bristol Machine Tools Ltd.",
                "ultimate_destination": "GB",
            },
            step7={"installation_location": "Bristol, United Kingdom"},
        )
    )
    cases.append(
        case(
            "CLN-06",
            "Ordinary company names must not produce screening hits",
            "clean_control",
            expected={
                **clean_expected,
                "screening": {
                    "Harbour Point Engineering Ltd.": "NO_APPARENT_MATCH",
                    "Bluewater Analytical Services": "NO_APPARENT_MATCH",
                    "Maple Ridge Fabrication Inc.": "NO_APPARENT_MATCH",
                    "Sunrise Optics KK": "NO_APPARENT_MATCH",
                    "Lakeside Calibration Partners": "NO_APPARENT_MATCH",
                },
            },
            control=True,
            step6={
                "beneficial_owners": [
                    "Harbour Point Engineering Ltd.",
                    "Bluewater Analytical Services",
                    "Maple Ridge Fabrication Inc.",
                    "Sunrise Optics KK",
                    "Lakeside Calibration Partners",
                ]
            },
            notes="False-positive probe: none of these names should be near any benchmark list entry.",
        )
    )

    # ------------------------------------------------------------ jurisdiction
    cases.append(
        case(
            "JUR-01",
            "U.S.-origin item with no ECCN recorded",
            "jurisdiction",
            expected={"jurisdiction_status": "POSSIBLE_EAR_JURISDICTION", "red_flags_should_include": []},
            step2={"existing_eccn": None, "existing_ear_status": "Not determined"},
        )
    )
    cases.append(
        case(
            "JUR-02",
            "Foreign-produced item with U.S.-origin content and known values",
            "jurisdiction",
            expected={"jurisdiction_status": "POSSIBLE_EAR_JURISDICTION"},
            step2={"country_of_manufacture": "CN", "existing_ear_status": "Not believed to be U.S.-origin"},
            step3={
                "is_us_origin": False,
                "has_us_origin_content": True,
                "us_content_value_known": True,
                "total_foreign_value_known": True,
            },
        )
    )
    cases.append(
        case(
            "JUR-03",
            "Foreign-produced item with U.S. content but unknown U.S. content value",
            "jurisdiction",
            expected={"jurisdiction_status": "JURISDICTION_REVIEW_REQUIRED", "red_flags_should_include": ["RF009"]},
            step2={"country_of_manufacture": "CN", "existing_ear_status": "Not believed to be U.S.-origin"},
            step3={
                "is_us_origin": False,
                "has_us_origin_content": True,
                "us_content_value_known": False,
                "total_foreign_value_known": True,
            },
        )
    )
    cases.append(
        case(
            "JUR-04",
            "Foreign-produced item with U.S. content but unknown total value",
            "jurisdiction",
            expected={"jurisdiction_status": "JURISDICTION_REVIEW_REQUIRED"},
            step3={
                "is_us_origin": False,
                "has_us_origin_content": True,
                "us_content_value_known": True,
                "total_foreign_value_known": False,
            },
        )
    )
    cases.append(
        case(
            "JUR-05",
            "Foreign item produced with U.S.-origin software",
            "jurisdiction",
            expected={"jurisdiction_status": "POSSIBLE_EAR_JURISDICTION"},
            step3={
                "is_us_origin": False,
                "has_us_origin_content": False,
                "us_software_used_in_production": True,
                "us_technology_used_in_production": False,
                "production_chain_known": True,
            },
        )
    )
    cases.append(
        case(
            "JUR-06",
            "Foreign item with no U.S. content and an unknown production chain",
            "jurisdiction",
            expected={"jurisdiction_status": "INSUFFICIENT_INFORMATION"},
            step3={
                "is_us_origin": False,
                "has_us_origin_content": False,
                "us_software_used_in_production": False,
                "us_technology_used_in_production": False,
                "production_chain_known": None,
            },
        )
    )
    cases.append(
        case(
            "JUR-07",
            "Origin question left unanswered",
            "jurisdiction",
            expected={"jurisdiction_status": "INSUFFICIENT_INFORMATION"},
            step3={"is_us_origin": None, "production_chain_known": None},
        )
    )
    cases.append(
        case(
            "JUR-08",
            "Foreign item with the U.S.-content question left unanswered",
            "jurisdiction",
            expected={"jurisdiction_status": "INSUFFICIENT_INFORMATION"},
            step3={"is_us_origin": False, "has_us_origin_content": None, "production_chain_known": None},
        )
    )
    cases.append(
        case(
            "JUR-09",
            "Foreign item with no U.S. nexus identified",
            "jurisdiction",
            expected={"jurisdiction_status": "JURISDICTION_REVIEW_REQUIRED"},
            step3={
                "is_us_origin": False,
                "has_us_origin_content": False,
                "us_software_used_in_production": False,
                "us_technology_used_in_production": False,
                "production_chain_known": True,
            },
        )
    )
    cases.append(
        case(
            "JUR-10",
            "U.S.-origin item whose production chain is not documented",
            "jurisdiction",
            expected={"jurisdiction_status": "POSSIBLE_EAR_JURISDICTION"},
            step3={"is_us_origin": True, "production_chain_known": None},
        )
    )

    # --------------------------------------------------------------- de minimis
    foreign_with_us_content = {
        "is_us_origin": False,
        "has_us_origin_content": True,
        "us_content_value_known": True,
        "total_foreign_value_known": True,
        "production_chain_known": True,
    }
    cases.append(
        case(
            "DM-01",
            "No components entered for a foreign-produced item",
            "deminimis",
            expected={"deminimis_status": "MISSING_INPUT"},
            step3=foreign_with_us_content,
            step4={"components": [], "total_foreign_product_value": 250000.0},
        )
    )
    cases.append(
        case(
            "DM-02",
            "Total foreign product value recorded as zero",
            "deminimis",
            expected={"deminimis_status": "MISSING_TOTAL"},
            step3=foreign_with_us_content,
            step4={
                "components": [
                    {
                        "component_name": "U.S.-origin servo driver",
                        "origin": "US",
                        "eccn": "3A001",
                        "controlled_status": "Yes - controlled",
                        "component_value": 10000.0,
                    }
                ],
                "total_foreign_product_value": 0.0,
            },
        )
    )
    cases.append(
        case(
            "DM-03",
            "Total foreign product value left blank",
            "deminimis",
            expected={"deminimis_status": "MISSING_TOTAL"},
            step3=foreign_with_us_content,
            step4={
                "components": [
                    {
                        "component_name": "U.S.-origin servo driver",
                        "origin": "US",
                        "eccn": "3A001",
                        "controlled_status": "Yes - controlled",
                        "component_value": 10000.0,
                    }
                ],
                "total_foreign_product_value": None,
            },
        )
    )
    cases.append(
        case(
            "DM-04",
            "Controlled U.S. component with no recorded value",
            "deminimis",
            expected={"deminimis_status": "MISSING_VALUE"},
            step3=foreign_with_us_content,
            step4={
                "components": [
                    {
                        "component_name": "U.S.-origin controller board",
                        "origin": "US",
                        "eccn": "3A001",
                        "controlled_status": "Yes - controlled",
                        "component_value": None,
                    }
                ],
                "total_foreign_product_value": 250000.0,
            },
        )
    )
    cases.append(
        case(
            "DM-05",
            "Only non-U.S. components recorded",
            "deminimis",
            expected={"deminimis_status": "NO_CONTROLLED_US_CONTENT", "deminimis_ratio": 0.0},
            step3=foreign_with_us_content,
            step4={
                "components": [
                    {
                        "component_name": "German servo drive",
                        "origin": "DE",
                        "eccn": "3A001",
                        "controlled_status": "Yes - controlled",
                        "component_value": 40000.0,
                    },
                    {
                        "component_name": "Japanese display panel",
                        "origin": "JP",
                        "eccn": None,
                        "controlled_status": "No - EAR99",
                        "component_value": 15000.0,
                    },
                ],
                "total_foreign_product_value": 250000.0,
            },
        )
    )
    cases.append(
        case(
            "DM-06",
            "U.S. component explicitly recorded as EAR99",
            "deminimis",
            expected={"deminimis_status": "NO_CONTROLLED_US_CONTENT", "deminimis_ratio": 0.0},
            step3=foreign_with_us_content,
            step4={
                "components": [
                    {
                        "component_name": "U.S.-origin power supply",
                        "origin": "US",
                        "eccn": None,
                        "controlled_status": "No - EAR99",
                        "component_value": 8000.0,
                    }
                ],
                "total_foreign_product_value": 250000.0,
            },
        )
    )
    cases.append(
        case(
            "DM-07",
            "Ratio at exactly the 5% review threshold",
            "deminimis",
            expected={
                "deminimis_status": "COMPUTED",
                "deminimis_ratio": 0.05,
                "red_flags_should_include": ["RF007"],
            },
            difficulty="hard",
            step3=foreign_with_us_content,
            step4={
                "components": [
                    {
                        "component_name": "U.S.-origin control module",
                        "origin": "US",
                        "eccn": "3A001",
                        "controlled_status": "Yes - controlled",
                        "component_value": 12500.0,
                    }
                ],
                "total_foreign_product_value": 250000.0,
            },
        )
    )
    cases.append(
        case(
            "DM-08",
            "Ratio just below the 5% threshold",
            "deminimis",
            expected={
                "deminimis_status": "COMPUTED",
                "deminimis_ratio": 0.049,
                "red_flags_should_not_include": ["RF007"],
            },
            difficulty="hard",
            step3=foreign_with_us_content,
            step4={
                "components": [
                    {
                        "component_name": "U.S.-origin control module",
                        "origin": "US",
                        "eccn": "3A001",
                        "controlled_status": "Yes - controlled",
                        "component_value": 12250.0,
                    }
                ],
                "total_foreign_product_value": 250000.0,
            },
        )
    )
    cases.append(
        case(
            "DM-09",
            "Component with an unclear controlled status is excluded",
            "deminimis",
            expected={"deminimis_status": "NO_CONTROLLED_US_CONTENT", "deminimis_ratio": 0.0},
            difficulty="hard",
            step3=foreign_with_us_content,
            step4={
                "components": [
                    {
                        "component_name": "U.S.-origin signal amplifier",
                        "origin": "US",
                        "eccn": None,
                        "controlled_status": "Unknown",
                        "component_value": 30000.0,
                    }
                ],
                "total_foreign_product_value": 250000.0,
            },
            notes="Unclear status must be excluded from the numerator and produce a warning.",
        )
    )
    cases.append(
        case(
            "DM-10",
            "High U.S. content ratio for a foreign-produced item",
            "deminimis",
            expected={
                "deminimis_status": "COMPUTED",
                "deminimis_ratio": 0.4,
                "red_flags_should_include": ["RF007"],
                "queue_decision_min": "COMPLIANCE_REVIEW_REQUIRED",
            },
            step3=foreign_with_us_content,
            step4={
                "components": [
                    {
                        "component_name": "U.S.-origin embedded processor board",
                        "origin": "US",
                        "eccn": "3A001",
                        "controlled_status": "Yes - controlled",
                        "component_value": 100000.0,
                    }
                ],
                "total_foreign_product_value": 250000.0,
            },
            known_issues=[
                "A 40% U.S.-content ratio scores only LOW (19/100): the risk engine caps the "
                "red-flag category at 10 points, so the size of the ratio does not raise the band.",
                "Red flag RF007 declares the action LEGAL_REVIEW_REQUIRED, but the review queue "
                "rule RQ-07 routes any red flag to COMPLIANCE_REVIEW_REQUIRED instead. The queue "
                "never reads the action field of a red flag.",
            ],
        )
    )

    # --------------------------------------------------------------------- FDP
    cases.append(
        case(
            "FDP-01",
            "U.S.-origin software and a documented production chain",
            "fdp",
            expected={"fdp_flag": "POTENTIAL_FDP_ISSUE", "red_flags_should_include": ["RF008"]},
            step5={
                "us_software_used": "U.S.-origin firmware compiler suite, version 8.2",
                "foreign_production_facilities": "Penang assembly plant, Malaysia",
                "production_equipment": "Automated optical inspection line",
                "production_process_description": "SMT assembly, firmware flashing, functional test",
            },
        )
    )
    cases.append(
        case(
            "FDP-02",
            "U.S.-origin software recorded but no production chain",
            "fdp",
            expected={"fdp_flag": "INSUFFICIENT_INFORMATION"},
            step5={"us_software_used": "U.S.-origin firmware compiler suite, version 8.2"},
        )
    )
    cases.append(
        case(
            "FDP-03",
            "Production chain documented with no U.S. inputs",
            "fdp",
            expected={"fdp_flag": "NO_FDP_FACTS_IDENTIFIED", "red_flags_should_not_include": ["RF008"]},
            step5={
                "foreign_production_facilities": "Penang assembly plant, Malaysia",
                "production_equipment": "Automated optical inspection line",
                "production_process_description": "SMT assembly, functional test",
            },
        )
    )
    cases.append(
        case(
            "FDP-04",
            "No production or U.S. input facts at all",
            "fdp",
            expected={"fdp_flag": "NO_FDP_FACTS_IDENTIFIED"},
        )
    )
    cases.append(
        case(
            "FDP-05",
            "U.S.-origin technology and foreign production facilities",
            "fdp",
            expected={"fdp_flag": "POTENTIAL_FDP_ISSUE"},
            step5={
                "us_technology_used": "U.S.-origin thin-film deposition process documentation",
                "foreign_production_facilities": "Hsinchu fabrication plant, Taiwan",
            },
        )
    )
    cases.append(
        case(
            "FDP-06",
            "U.S. software plus production equipment only",
            "fdp",
            expected={"fdp_flag": "POTENTIAL_FDP_ISSUE"},
            step5={
                "us_software_used": "U.S.-origin CAD/CAM package",
                "production_equipment": "Five-axis machining centre",
            },
        )
    )

    # --------------------------------------------------------------- screening
    cases.append(
        case(
            "SCR-01",
            "Buyer name matches a benchmark list entry exactly",
            "screening",
            expected={
                "screening": {"Vector Trading FZE": "MANUAL_VERIFICATION_REQUIRED"},
                "red_flags_should_include": ["RF005"],
                "queue_decision": "EXTERNAL_COUNSEL_REVIEW_RECOMMENDED",
            },
            step1={"buyer_name": "Vector Trading FZE"},
        )
    )
    cases.append(
        case(
            "SCR-02",
            "Buyer name matches an alias on the benchmark list",
            "screening",
            expected={
                "screening": {"VT Trading FZE": "MANUAL_VERIFICATION_REQUIRED"},
                "red_flags_should_include": ["RF005"],
            },
            step1={"buyer_name": "VT Trading FZE"},
        )
    )
    cases.append(
        case(
            "SCR-03",
            "Near-miss name one character away from a listed entity",
            "screening",
            expected={
                "screening": {"Victor Trading FZE": "POSSIBLE_MATCH"},
                "red_flags_should_include": ["RF006"],
                "red_flags_should_not_include": ["RF005"],
            },
            difficulty="hard",
            step1={"buyer_name": "Victor Trading FZE"},
            notes="Boundary probe for the fuzzy similarity band between 0.65 and 0.96.",
        )
    )
    cases.append(
        case(
            "SCR-04",
            "Similar but distinct corporate name shares a leading token",
            "screening",
            expected={"screening": {"Orion Microsystems Ltd.": "POSSIBLE_MATCH"}},
            difficulty="hard",
            step1={"buyer_name": "Orion Microsystems Ltd."},
        )
    )
    cases.append(
        case(
            "SCR-05",
            "British spelling variant of a listed entity name",
            "screening",
            expected={"screening": {"Northgate Defence Systems FZE": "MANUAL_VERIFICATION_REQUIRED"}},
            difficulty="hard",
            step1={"buyer_name": "Northgate Defence Systems FZE"},
        )
    )
    cases.append(
        case(
            "SCR-06",
            "Unrelated buyer name produces no screening hit",
            "screening",
            expected={
                "screening": {"Rheinland Automation GmbH": "NO_APPARENT_MATCH"},
                "red_flags_should_not_include": ["RF005", "RF006"],
            },
            control=True,
        )
    )
    cases.append(
        case(
            "SCR-07",
            "Parent company matches a benchmark list entry",
            "screening",
            expected={
                "screening": {"Helios Precision Works": "MANUAL_VERIFICATION_REQUIRED"},
                "red_flags_should_include": ["RF005"],
            },
            step6={"parent_companies": ["Helios Precision Works"]},
        )
    )
    cases.append(
        case(
            "SCR-08",
            "Beneficial owner matches an alias on the benchmark list",
            "screening",
            expected={"screening": {"Silverline Group": "MANUAL_VERIFICATION_REQUIRED"}},
            step6={"beneficial_owners": ["Silverline Group"]},
        )
    )
    cases.append(
        case(
            "SCR-09",
            "Consignee matches an alias on the benchmark list",
            "screening",
            expected={"screening": {"Alborz Trading": "MANUAL_VERIFICATION_REQUIRED"}},
            step1={"consignee": "Alborz Trading"},
        )
    )
    cases.append(
        case(
            "SCR-10",
            "Subsidiary matches a benchmark list entry",
            "screening",
            expected={"screening": {"Zephyr Semiconductor Corp": "MANUAL_VERIFICATION_REQUIRED"}},
            step6={"subsidiaries": ["Zephyr Semiconductor Corp"]},
        )
    )
    cases.append(
        case(
            "SCR-11",
            "Exporter itself matches a benchmark list entry",
            "screening",
            expected={
                "screening": {"Kestrel Marine Technologies": "MANUAL_VERIFICATION_REQUIRED"},
                "red_flags_should_include": ["RF005"],
                "queue_decision": "EXTERNAL_COUNSEL_REVIEW_RECOMMENDED",
            },
            step1={"exporter_name": "Kestrel Marine Technologies"},
            notes="Step 1 parties are screened too, not only the additional parties entered in Step 6.",
        )
    )

    # ------------------------------------------------------------------ end use
    cases.append(
        case(
            "EU-01",
            "Military end use selected by the reviewer",
            "end_use",
            expected={
                "end_use_flags_exact": ["military_related_indicators"],
                "red_flags_should_include": ["RF004"],
            },
            step7={
                "declared_end_use": "Integration into a mobile field communications shelter",
                "industry": "Defense electronics",
                "civil_use": False,
                "military_use": True,
            },
        )
    )
    cases.append(
        case(
            "EU-02",
            "Military terminology inside the declared end use",
            "end_use",
            expected={
                "end_use_flags_exact": ["military_related_indicators"],
                "red_flags_should_include": ["RF004"],
            },
            step7={
                "declared_end_use": "Used for missile guidance calibration in a test range",
                "industry": "Aerospace",
                "civil_use": False,
                "aerospace_use": True,
            },
        )
    )
    cases.append(
        case(
            "EU-03",
            "Declared end use too short to assess",
            "end_use",
            expected={
                "end_use_flags_exact": [
                    "insufficient_end_use_information",
                    "inconsistent_business_activity",
                    "unclear_installation_location",
                ],
                "queue_decision_min": "COMPLIANCE_REVIEW_REQUIRED",
            },
            step7={
                "declared_end_use": "testing",
                "installation_location": "",
                "industry": "",
            },
            notes=(
                "A one-word declared use with no industry also triggers the "
                "'inconsistent business activity' flag, because the industry field is empty."
            ),
        )
    )
    cases.append(
        case(
            "EU-04",
            "Declared use provided but no end-use category selected",
            "end_use",
            expected={"end_use_flags_exact": ["insufficient_end_use_information"]},
            step7={
                "declared_end_use": "Used in a laboratory for materials testing",
                "civil_use": False,
                "research_use": False,
            },
        )
    )
    cases.append(
        case(
            "EU-05",
            "Civil and military end uses selected together",
            "end_use",
            expected={
                "end_use_flags_exact": ["inconsistent_business_activity", "military_related_indicators"],
            },
            step7={
                "declared_end_use": "Dual-use communications equipment for field deployment",
                "industry": "Telecommunications",
                "civil_use": True,
                "military_use": True,
            },
        )
    )
    cases.append(
        case(
            "EU-06",
            "Installation location recorded as unknown",
            "end_use",
            expected={"end_use_flags_exact": ["unclear_installation_location"]},
            step7={"installation_location": "unknown"},
        )
    )
    cases.append(
        case(
            "EU-07",
            "Civilian industry listed while military use is selected",
            "end_use",
            expected={
                "end_use_flags_exact": ["inconsistent_business_activity", "military_related_indicators"],
            },
            step7={
                "declared_end_use": "Installed in a military training simulator",
                "industry": "Civilian consumer electronics",
                "civil_use": True,
                "military_use": True,
            },
        )
    )
    cases.append(
        case(
            "EU-08",
            "Complete and consistent civilian end-use record",
            "end_use",
            expected={"end_use_flags_exact": []},
            control=True,
        )
    )

    # -------------------------------------------------------------- destination
    cases.append(
        case(
            "DST-01",
            "Shipment to a comprehensively embargoed destination",
            "destination",
            expected={
                "red_flags_should_include": ["RF003"],
                "risk_level_min": "MODERATE",
                "queue_decision": "EXTERNAL_COUNSEL_REVIEW_RECOMMENDED",
            },
            step1={"ultimate_destination": "IR", "buyer_country": "IR", "buyer_name": "Tehran Industrial Supply"},
            known_issues=[
                "An embargoed destination case scores MODERATE (36/100), not HIGH: the destination "
                "category caps at 15 points and the red-flag category at 10 points even though the "
                "embargo red flag itself carries 25 points.",
                "The queue outcome is still correct - RQ-03 escalates any embargoed destination to "
                "EXTERNAL_COUNSEL_REVIEW_RECOMMENDED regardless of the score band.",
            ],
        )
    )
    cases.append(
        case(
            "DST-02",
            "Shipment to North Korea",
            "destination",
            expected={"red_flags_should_include": ["RF003"], "queue_decision": "EXTERNAL_COUNSEL_REVIEW_RECOMMENDED"},
            step1={"ultimate_destination": "KP", "buyer_country": "KP", "buyer_name": "Pyongyang Trading Bureau"},
        )
    )
    cases.append(
        case(
            "DST-03",
            "Shipment to a special-attention destination",
            "destination",
            expected={"red_flags_should_not_include": ["RF003"], "risk_level_min": "LOW"},
            step1={"ultimate_destination": "CN", "buyer_country": "CN", "buyer_name": "Shanghai Instrumentation Co."},
        )
    )
    cases.append(
        case(
            "DST-04",
            "Shipment to Belarus",
            "destination",
            expected={"red_flags_should_not_include": ["RF003"]},
            step1={"ultimate_destination": "BY", "buyer_country": "BY", "buyer_name": "Minsk Automation Bureau"},
        )
    )
    cases.append(
        case(
            "DST-05",
            "Ultimate destination not recorded",
            "destination",
            expected={
                "red_flags_should_include": ["RF002"],
                "risk_level_min": "MODERATE",
            },
            step1={"ultimate_destination": None},
        )
    )
    cases.append(
        case(
            "DST-06",
            "Buyer located in an embargoed country but ultimate destination is elsewhere",
            "destination",
            expected={"red_flags_should_not_include": ["RF003"]},
            difficulty="hard",
            step1={
                "buyer_country": "IR",
                "buyer_name": "Tehran Industrial Supply",
                "ultimate_destination": "DE",
            },
            notes=(
                "Documented behaviour: the embargo check uses ultimate_destination only. "
                "This case records the current behaviour so a reviewer can decide whether it is a gap."
            ),
        )
    )

    # ------------------------------------------------------------------- mixed
    cases.append(
        case(
            "MIX-01",
            "U.S. software, military end use, and an embargoed destination",
            "mixed",
            expected={
                "red_flags_should_include": ["RF003", "RF004", "RF008"],
                "risk_level_min": "HIGH",
                "queue_decision": "EXTERNAL_COUNSEL_REVIEW_RECOMMENDED",
            },
            difficulty="hard",
            step1={
                "buyer_name": "Qeshm Electronics Trading",
                "buyer_country": "IR",
                "ultimate_destination": "IR",
                "ultimate_end_user": None,
            },
            step2={
                "product_name": "Guidance Module Test Bench",
                "product_description": (
                    "Bench used to calibrate missile guidance electronics in a production "
                    "environment, with military-grade connectors and shielding."
                ),
                "existing_ear_status": "Controlled (ECCN)",
                "existing_eccn": "3A001",
            },
            step5={
                "us_software_used": "U.S.-origin signal-analysis software",
                "foreign_production_facilities": "Bandar Abbas assembly plant, Iran",
                "production_process_description": "Module assembly and calibration",
            },
            step7={
                "declared_end_use": "Calibration of missile guidance electronics for field units",
                "installation_location": "Bandar Abbas, Iran",
                "industry": "Defense electronics",
                "civil_use": False,
                "military_use": True,
            },
        )
    )
    cases.append(
        case(
            "MIX-02",
            "Screening match combined with military end use and high U.S. content",
            "mixed",
            expected={
                "red_flags_should_include": ["RF005", "RF004", "RF007"],
                "queue_decision": "EXTERNAL_COUNSEL_REVIEW_RECOMMENDED",
            },
            difficulty="hard",
            step1={"buyer_name": "Vector Trading FZE", "buyer_country": "AE", "ultimate_destination": "AE"},
            step3={
                "is_us_origin": False,
                "has_us_origin_content": True,
                "us_content_value_known": True,
                "total_foreign_value_known": True,
            },
            step4={
                "components": [
                    {
                        "component_name": "U.S.-origin signal processor",
                        "origin": "US",
                        "eccn": "3A001",
                        "controlled_status": "Yes - controlled",
                        "component_value": 90000.0,
                    }
                ],
                "total_foreign_product_value": 250000.0,
            },
            step7={
                "declared_end_use": "Integration into a military surveillance radar system",
                "industry": "Defense electronics",
                "civil_use": False,
                "military_use": True,
            },
        )
    )
    cases.append(
        case(
            "MIX-03",
            "Moderate risk mix needing compliance review",
            "mixed",
            expected={
                "risk_level_min": "MODERATE",
                "queue_decision_min": "COMPLIANCE_REVIEW_REQUIRED",
            },
            step1={"ultimate_end_user": None, "ultimate_destination": None},
        )
    )
    cases.append(
        case(
            "MIX-04",
            "Foreign item with no documented production inputs",
            "mixed",
            expected={
                "jurisdiction_status": "INSUFFICIENT_INFORMATION",
                "fdp_flag": "INSUFFICIENT_INFORMATION",
                "queue_decision_min": "LEGAL_REVIEW_REQUIRED",
            },
            step3={
                "is_us_origin": False,
                "has_us_origin_content": False,
                "production_chain_known": None,
            },
            step5={"us_software_used": "U.S.-origin simulation package"},
        )
    )
    cases.append(
        case(
            "MIX-05",
            "Embargoed destination with several missing facts",
            "mixed",
            expected={
                "red_flags_should_include": ["RF001", "RF003"],
                "red_flags_should_not_include": ["RF002"],
                "queue_decision": "EXTERNAL_COUNSEL_REVIEW_RECOMMENDED",
            },
            step1={
                "buyer_country": "SY",
                "buyer_name": "Damascus General Trading",
                "ultimate_destination": "SY",
                "ultimate_end_user": None,
            },
            notes="RF002 must not fire: the ultimate destination is recorded, only the end user is missing.",
        )
    )
    cases.append(
        case(
            "MIX-06",
            "Everything incomplete on a foreign-produced item",
            "mixed",
            expected={
                "jurisdiction_status": "INSUFFICIENT_INFORMATION",
                "risk_level_min": "MODERATE",
                "queue_decision_min": "LEGAL_REVIEW_REQUIRED",
            },
            difficulty="hard",
            step1={"ultimate_end_user": None, "ultimate_destination": None},
            step3={
                "is_us_origin": None,
                "production_chain_known": None,
            },
            step7={
                "declared_end_use": "",
                "installation_location": "",
                "industry": "",
                "civil_use": False,
            },
        )
    )
    cases.append(
        case(
            "MIX-07",
            "Maximum severity stack: embargo, list match, military use, FDP and missing facts",
            "mixed",
            expected={
                "jurisdiction_status": "INSUFFICIENT_INFORMATION",
                "deminimis_status": "COMPUTED",
                "fdp_flag": "POTENTIAL_FDP_ISSUE",
                "screening": {"Vector Trading FZE": "MANUAL_VERIFICATION_REQUIRED"},
                "red_flags_should_include": ["RF001", "RF003", "RF004", "RF005", "RF007", "RF008", "RF009"],
                "risk_level_min": "HIGH",
                "queue_decision": "EXTERNAL_COUNSEL_REVIEW_RECOMMENDED",
            },
            difficulty="hard",
            step1={
                "buyer_name": "Vector Trading FZE",
                "buyer_country": "IR",
                "ultimate_destination": "IR",
                "ultimate_end_user": None,
                "transaction_value": 2000000.0,
            },
            step2={
                "product_name": "Guidance Bench GB-9",
                "product_description": (
                    "Calibration bench for missile guidance electronics with military-grade "
                    "connectors, radar absorbing panels and ballistic test fixtures."
                ),
                "existing_eccn": "3A001",
                "existing_ear_status": "Controlled (ECCN)",
                "product_value": 2000000.0,
            },
            step3={
                "is_us_origin": None,
                "has_us_origin_content": None,
                "us_content_value_known": None,
                "total_foreign_value_known": None,
                "us_software_used_in_production": None,
                "us_technology_used_in_production": None,
                "production_chain_known": None,
            },
            step4={
                "components": [
                    {
                        "component_name": "U.S.-origin signal processor",
                        "origin": "US",
                        "eccn": "3A001",
                        "controlled_status": "Yes - controlled",
                        "component_value": 1200000.0,
                    }
                ],
                "total_foreign_product_value": 2000000.0,
            },
            step5={
                "us_software_used": "U.S.-origin signal analysis suite",
                "foreign_production_facilities": "Bandar Abbas assembly plant, Iran",
                "production_process_description": "Module assembly and calibration",
            },
            step7={
                "declared_end_use": "Calibration of missile guidance electronics for field units",
                "installation_location": "unknown",
                "industry": "",
                "civil_use": False,
                "military_use": True,
            },
            notes="Probes how far the 0-100 score can actually travel when every category is saturated.",
        )
    )

    # ---------------------------------------------------------------- boundary
    cases.append(
        case(
            "BND-01",
            "Civilian product description containing the phrase military-grade",
            "boundary",
            expected={
                "red_flags_should_include": ["RF004"],
                "queue_decision_min": "COMPLIANCE_REVIEW_REQUIRED",
            },
            difficulty="hard",
            step2={
                "product_description": (
                    "Ruggedised industrial power supply marketed with military-grade connectors "
                    "for use in civil mining vehicles and agricultural machinery."
                )
            },
            notes="Tests the keyword-based military detector against a deliberately ambiguous description.",
        )
    )
    cases.append(
        case(
            "BND-02",
            "Company name contains Defense but the business is civilian security",
            "boundary",
            expected={"red_flags_should_not_include": ["RF004", "RF005"]},
            difficulty="hard",
            step1={
                "buyer_name": "Northgate Defense Security Services GmbH",
                "buyer_country": "DE",
            },
            notes="Corporate names are not screened for military terms; only product text and end use are.",
        )
    )
    cases.append(
        case(
            "BND-03",
            "Controlled EAR status recorded with no ECCN",
            "boundary",
            expected={"red_flags_should_not_include": ["RF005"]},
            difficulty="hard",
            step2={"existing_eccn": None, "existing_ear_status": "Controlled (ECCN)"},
        )
    )
    cases.append(
        case(
            "BND-04",
            "Product and transaction values both missing",
            "boundary",
            expected={"red_flags_should_not_include": ["RF007"]},
            step1={"transaction_value": None},
            step2={"product_value": None},
        )
    )
    cases.append(
        case(
            "BND-05",
            "Every jurisdiction question left unanswered",
            "boundary",
            expected={
                "jurisdiction_status": "INSUFFICIENT_INFORMATION",
                "queue_decision_min": "LEGAL_REVIEW_REQUIRED",
            },
            step3={
                "is_us_origin": None,
                "has_us_origin_content": None,
                "us_content_value_known": None,
                "total_foreign_value_known": None,
                "us_software_used_in_production": None,
                "us_technology_used_in_production": None,
                "production_chain_known": None,
            },
        )
    )
    cases.append(
        case(
            "BND-06",
            "Screening list name nearly identical to an unrelated buyer",
            "boundary",
            expected={
                "screening": {"Vertex Advanced Materials GmbH": "MANUAL_VERIFICATION_REQUIRED"},
            },
            difficulty="hard",
            step1={"buyer_name": "Vertex Advanced Materials GmbH", "buyer_country": "CH"},
        )
    )

    # ---------------------------------------------------------------- software
    software_product = {
        "product_name": "Helios Data Platform",
        "model": "HDP-4.2",
        "product_description": (
            "Enterprise data-integration platform distributed as a downloadable installer with "
            "per-seat licences and a commercial database connector library."
        ),
        "category": "Software",
        "country_of_manufacture": "US",
        "existing_eccn": None,
        "existing_ear_status": "EAR99",
    }
    cases.append(
        case(
            "SW-01",
            "U.S.-origin commercial software licensed to Germany",
            "software",
            expected={
                "jurisdiction_status": "POSSIBLE_EAR_JURISDICTION",
                "fdp_flag": "NO_FDP_FACTS_IDENTIFIED",
                "end_use_flags_exact": [],
                "red_flags_should_not_include": ["RF004", "RF007", "RF008"],
                "risk_level_exact": "LOW",
                "queue_decision": "AUTO_REVIEW_COMPLETE",
            },
            control=True,
            step2=software_product,
            step7={
                "declared_end_use": "Internal data integration and reporting for a logistics company",
                "industry": "Logistics software",
            },
            notes="Control case for software: no encryption handling and no U.S. content questions.",
        )
    )
    cases.append(
        case(
            "SW-02",
            "U.S.-origin encryption software with a recorded 5D002 classification",
            "software",
            expected={
                "jurisdiction_status": "POSSIBLE_EAR_JURISDICTION",
                "red_flags_should_not_include": ["RF004", "RF007"],
                "risk_level_exact": "LOW",
                "queue_decision": "AUTO_REVIEW_COMPLETE",
            },
            step2={
                **software_product,
                "product_name": "Helios Secure Channel",
                "product_description": (
                    "Commercial encryption toolkit providing AES-256 transport encryption and "
                    "key management for enterprise data pipelines."
                ),
                "existing_eccn": "5D002",
                "existing_ear_status": "Controlled (ECCN)",
            },
            step1={"buyer_country": "FR", "ultimate_destination": "FR", "buyer_name": "Lyon Data Systems SAS"},
            step7={
                "declared_end_use": "Protecting internal database traffic inside a corporate network",
                "installation_location": "Lyon, France",
                "industry": "Software",
            },
            notes=(
                "The tool has no encryption-specific logic: a recorded 5D002 drives product risk, "
                "and 'encryption' is not treated as a military keyword."
            ),
        )
    )
    cases.append(
        case(
            "SW-03",
            "Foreign-produced software incorporating a U.S.-origin SDK",
            "software",
            expected={
                "jurisdiction_status": "POSSIBLE_EAR_JURISDICTION",
                "deminimis_status": "COMPUTED",
                "deminimis_ratio": 0.12,
                "red_flags_should_include": ["RF007"],
                "queue_decision_min": "COMPLIANCE_REVIEW_REQUIRED",
            },
            difficulty="medium",
            step2={
                **software_product,
                "manufacturer": "Chengdu Cloud Software Co., Ltd.",
                "country_of_manufacture": "CN",
                "existing_ear_status": "Not believed to be U.S.-origin",
            },
            step3={
                "is_us_origin": False,
                "has_us_origin_content": True,
                "us_content_value_known": True,
                "total_foreign_value_known": True,
                "production_chain_known": True,
            },
            step4={
                "components": [
                    comp("U.S.-origin analytics SDK licence", "United States", value=120000.0, eccn="5D002")
                ],
                "total_foreign_product_value": 1000000.0,
            },
            step1={"buyer_country": "AE", "ultimate_destination": "AE", "buyer_name": "Dubai Cloud Partners FZE"},
        )
    )
    cases.append(
        case(
            "SW-04",
            "U.S.-origin software used only in production of a foreign software product",
            "software",
            expected={
                "jurisdiction_status": "POSSIBLE_EAR_JURISDICTION",
                "deminimis_status": "COMPUTED",
                "deminimis_ratio": 0.2,
                "fdp_flag": "POTENTIAL_FDP_ISSUE",
                "red_flags_should_include": ["RF007", "RF008"],
                "queue_decision_min": "LEGAL_REVIEW_REQUIRED",
            },
            difficulty="hard",
            step2={
                **software_product,
                "manufacturer": "Bangalore Software Works Pvt Ltd",
                "country_of_manufacture": "IN",
                "existing_ear_status": "Not believed to be U.S.-origin",
            },
            step3={
                "is_us_origin": False,
                "has_us_origin_content": False,
                "us_software_used_in_production": True,
                "us_technology_used_in_production": False,
                "production_chain_known": True,
            },
            step4={
                "components": [
                    comp("U.S.-origin build-toolchain licence (used in production)", "US", value=200000.0)
                ],
                "total_foreign_product_value": 1000000.0,
            },
            step5={
                "us_software_used": "U.S.-origin build and packaging toolchain",
                "foreign_production_facilities": "Bengaluru development centre, India",
                "production_process_description": "Source build, signing and packaging pipeline",
            },
            known_issues=[
                "The de minimis step accepts a component row for software that was only *used in "
                "production* rather than incorporated into the item. Here that inflates the ratio to "
                "20% and triggers RF007 even though the case is really an FDP question; the tool "
                "never asks the reviewer to distinguish the two.",
            ],
        )
    )
    cases.append(
        case(
            "SW-05",
            "U.S.-origin software component recorded as EAR99",
            "software",
            expected={
                "deminimis_status": "NO_CONTROLLED_US_CONTENT",
                "deminimis_ratio": 0.0,
                "red_flags_should_not_include": ["RF007"],
            },
            step3={
                "is_us_origin": False,
                "has_us_origin_content": True,
                "us_content_value_known": True,
                "total_foreign_value_known": True,
            },
            step4={
                "components": [
                    comp("U.S.-origin UI component library", "US", controlled="No - EAR99", value=180000.0)
                ],
                "total_foreign_product_value": 1000000.0,
            },
        )
    )
    cases.append(
        case(
            "SW-06",
            "U.S.-origin software component with an unknown controlled status",
            "software",
            expected={
                "deminimis_status": "NO_CONTROLLED_US_CONTENT",
                "deminimis_ratio": 0.0,
                "red_flags_should_not_include": ["RF007"],
            },
            difficulty="hard",
            step3={
                "is_us_origin": False,
                "has_us_origin_content": True,
                "us_content_value_known": True,
                "total_foreign_value_known": True,
            },
            step4={
                "components": [
                    comp("U.S.-origin machine-learning library", "US", controlled="Unknown", value=250000.0)
                ],
                "total_foreign_product_value": 1000000.0,
            },
            notes="An unclear status must be excluded from the numerator and reported as a warning.",
        )
    )
    cases.append(
        case(
            "SW-07",
            "Encryption software exported to an embargoed destination with no end user recorded",
            "software",
            expected={
                "red_flags_should_include": ["RF001", "RF003"],
                "queue_decision": "EXTERNAL_COUNSEL_REVIEW_RECOMMENDED",
            },
            step2={
                **software_product,
                "product_name": "Helios Secure Channel",
                "existing_eccn": "5D002",
                "existing_ear_status": "Controlled (ECCN)",
            },
            step1={
                "buyer_name": "Tehran Software Distribution",
                "buyer_country": "IR",
                "ultimate_destination": "IR",
                "ultimate_end_user": None,
            },
        )
    )
    cases.append(
        case(
            "SW-08",
            "Warehouse robot software containing the word guidance",
            "software",
            expected={
                "red_flags_should_include": ["RF004"],
                "queue_decision_min": "COMPLIANCE_REVIEW_REQUIRED",
            },
            difficulty="hard",
            step2={
                **software_product,
                "product_name": "Helios Route Guidance Suite",
                "product_description": (
                    "Warehouse management software providing route guidance for autonomous "
                    "forklift vehicles inside distribution centres."
                ),
            },
            step7={
                "declared_end_use": "Route guidance for autonomous forklifts in a distribution centre",
                "industry": "Warehouse automation",
            },
            known_issues=[
                "'guidance' is on the military keyword list, so a purely civilian warehouse product "
                "raises RF004 and a military end-use flag. Flagging for human review is intentional, "
                "but it is a false positive worth knowing about.",
            ],
        )
    )
    cases.append(
        case(
            "SW-09",
            "Foreign software with U.S. content but an unknown total value",
            "software",
            expected={
                "jurisdiction_status": "JURISDICTION_REVIEW_REQUIRED",
                "deminimis_status": "MISSING_TOTAL",
                "red_flags_should_include": ["RF009"],
                "queue_decision_min": "LEGAL_REVIEW_REQUIRED",
            },
            step2={
                **software_product,
                "country_of_manufacture": "CN",
                "existing_ear_status": "Not determined",
            },
            step3={
                "is_us_origin": False,
                "has_us_origin_content": True,
                "us_content_value_known": True,
                "total_foreign_value_known": False,
            },
            step4={
                "components": [comp("U.S.-origin SDK licence", "US", value=90000.0)],
                "total_foreign_product_value": None,
            },
        )
    )
    cases.append(
        case(
            "SW-10",
            "U.S.-origin software component with no recorded value",
            "software",
            expected={
                "deminimis_status": "MISSING_VALUE",
                "red_flags_should_not_include": ["RF007"],
            },
            difficulty="hard",
            step3={
                "is_us_origin": False,
                "has_us_origin_content": True,
                "us_content_value_known": True,
                "total_foreign_value_known": True,
            },
            step4={
                "components": [comp("U.S.-origin report engine licence", "US", value=None, eccn="5D002")],
                "total_foreign_product_value": 1000000.0,
            },
            known_issues=[
                "Missing de minimis data raises no red flag of its own: with the jurisdiction "
                "questions otherwise complete this case still reaches AUTO_REVIEW_COMPLETE even "
                "though the ratio cannot be calculated.",
            ],
        )
    )
    cases.append(
        case(
            "SW-11",
            "Software licence bundled with foreign hardware just above the review threshold",
            "software",
            expected={
                "deminimis_status": "COMPUTED",
                "deminimis_ratio": 0.0667,
                "red_flags_should_include": ["RF007"],
            },
            difficulty="hard",
            step3={
                "is_us_origin": False,
                "has_us_origin_content": True,
                "us_content_value_known": True,
                "total_foreign_value_known": True,
            },
            step4={
                "components": [
                    comp("U.S.-origin firmware bundle licence", "US", value=40000.0, eccn="5D992")
                ],
                "total_foreign_product_value": 600000.0,
            },
        )
    )
    cases.append(
        case(
            "SW-12",
            "Foreign software stack built mostly on U.S.-origin components",
            "software",
            expected={
                "deminimis_status": "COMPUTED",
                "deminimis_ratio": 0.6,
                "red_flags_should_include": ["RF007"],
                "queue_decision_min": "COMPLIANCE_REVIEW_REQUIRED",
            },
            step3={
                "is_us_origin": False,
                "has_us_origin_content": True,
                "us_content_value_known": True,
                "total_foreign_value_known": True,
            },
            step4={
                "components": [
                    comp("U.S.-origin runtime licence", "US", value=350000.0),
                    comp("U.S.-origin database engine licence", "US", value=250000.0),
                    comp("Indian UI module", "IN", controlled="No - EAR99", value=400000.0),
                ],
                "total_foreign_product_value": 1000000.0,
            },
        )
    )
    cases.append(
        case(
            "SW-13",
            "U.S. origin recorded with three different spellings",
            "software",
            expected={
                "deminimis_status": "COMPUTED",
                "deminimis_ratio": 0.5,
                "red_flags_should_include": ["RF007"],
            },
            difficulty="hard",
            step3={
                "is_us_origin": False,
                "has_us_origin_content": True,
                "us_content_value_known": True,
                "total_foreign_value_known": True,
            },
            step4={
                "components": [
                    comp("Licence A", "United States", value=50000.0),
                    comp("Licence B", "USA", value=50000.0),
                    comp("Licence C", "U.S.", value=50000.0),
                ],
                "total_foreign_product_value": 300000.0,
            },
            notes="'United States', 'USA' and 'U.S.' must all be recognised as U.S.-origin.",
        )
    )
    cases.append(
        case(
            "SW-14",
            "Marketing software containing the word targeting",
            "software",
            expected={
                "red_flags_should_include": ["RF004"],
                "queue_decision_min": "COMPLIANCE_REVIEW_REQUIRED",
            },
            difficulty="hard",
            step2={
                **software_product,
                "product_name": "Helios Audience Targeting Engine",
                "product_description": (
                    "Advertising platform that performs audience targeting and campaign "
                    "optimisation for retail marketing teams."
                ),
            },
            step7={
                "declared_end_use": "Audience targeting for retail marketing campaigns",
                "industry": "Marketing technology",
            },
            known_issues=[
                "'targeting' is on the military keyword list, so commercial advertising software is "
                "flagged by RF004. Same keyword-noise pattern as SW-08.",
            ],
        )
    )
    cases.append(
        case(
            "SW-15",
            "Software delivered electronically with no consignee or shipment date",
            "software",
            expected={
                "jurisdiction_status": "POSSIBLE_EAR_JURISDICTION",
                "end_use_flags_exact": [],
                "risk_level_exact": "LOW",
                "queue_decision": "AUTO_REVIEW_COMPLETE",
            },
            control=True,
            step2=software_product,
            step1={
                "consignee": None,
                "shipment_date": None,
                "buyer_name": "Toronto Analytics Corp.",
                "buyer_country": "CA",
                "ultimate_destination": "CA",
                "notes": "Delivered by electronic download; no physical shipment.",
            },
            known_issues=[
                "The transaction model has no concept of electronic delivery: a download is captured "
                "exactly like a physical shipment, and no consignee or shipment date is required. "
                "That is a modelling limitation for software exports.",
            ],
        )
    )

    # -------------------------------------------------- advanced de minimis
    mixed_components = {
        "is_us_origin": False,
        "has_us_origin_content": True,
        "us_content_value_known": True,
        "total_foreign_value_known": True,
    }
    cases.append(
        case(
            "DMX-01",
            "Mixed component set with one controlled U.S. value missing",
            "deminimis_advanced",
            expected={
                "deminimis_status": "MISSING_VALUE",
                "red_flags_should_not_include": ["RF007"],
            },
            difficulty="hard",
            step3=mixed_components,
            step4={
                "components": [
                    comp("U.S.-origin controller", "US", value=100000.0),
                    comp("U.S.-origin sensor module", "US", value=None),
                    comp("U.S.-origin cable assembly", "US", controlled="No - EAR99", value=50000.0),
                    comp("U.S.-origin enclosure", "US", controlled="Unknown", value=70000.0),
                    comp("German drive unit", "DE", value=60000.0),
                ],
                "total_foreign_product_value": 1000000.0,
            },
            known_issues=[
                "Same gap as SW-10: an incomplete ratio raises no red flag, so a transaction with "
                "un-priceable controlled U.S. content can still auto-complete.",
            ],
        )
    )
    cases.append(
        case(
            "DMX-02",
            "Same component set with every value recorded",
            "deminimis_advanced",
            expected={
                "deminimis_status": "COMPUTED",
                "deminimis_ratio": 0.19,
                "red_flags_should_include": ["RF007"],
            },
            difficulty="hard",
            step3=mixed_components,
            step4={
                "components": [
                    comp("U.S.-origin controller", "US", value=100000.0),
                    comp("U.S.-origin sensor module", "US", value=90000.0),
                    comp("U.S.-origin cable assembly", "US", controlled="No - EAR99", value=50000.0),
                    comp("U.S.-origin enclosure", "US", controlled="Unknown", value=70000.0),
                    comp("German drive unit", "DE", value=60000.0),
                ],
                "total_foreign_product_value": 1000000.0,
            },
            notes="Only the two controlled U.S. components count: 190,000 / 1,000,000.",
        )
    )
    cases.append(
        case(
            "DMX-03",
            "Recurring decimal ratio",
            "deminimis_advanced",
            expected={"deminimis_status": "COMPUTED", "deminimis_ratio": 0.3333},
            difficulty="hard",
            step3=mixed_components,
            step4={
                "components": [comp("U.S.-origin module", "US", value=333333.33)],
                "total_foreign_product_value": 1000000.0,
            },
        )
    )
    cases.append(
        case(
            "DMX-04",
            "U.S. content value exceeds the total product value",
            "deminimis_advanced",
            expected={"deminimis_status": "COMPUTED", "deminimis_ratio": 1.6},
            difficulty="hard",
            step3=mixed_components,
            step4={
                "components": [comp("U.S.-origin subsystem", "US", value=800000.0)],
                "total_foreign_product_value": 500000.0,
            },
            known_issues=[
                "The calculator does not cap the ratio at 100%: U.S. content above the declared total "
                "produces 160% and RF007 simply fires. No validation warning flags the internally "
                "inconsistent inputs.",
            ],
        )
    )
    cases.append(
        case(
            "DMX-05",
            "Very small U.S. content share",
            "deminimis_advanced",
            expected={
                "deminimis_status": "COMPUTED",
                "deminimis_ratio": 0.001,
                "red_flags_should_not_include": ["RF007"],
            },
            step3=mixed_components,
            step4={
                "components": [comp("U.S.-origin fastener set", "US", value=1000.0)],
                "total_foreign_product_value": 1000000.0,
            },
        )
    )
    cases.append(
        case(
            "DMX-06",
            "Ratio exactly at 10%",
            "deminimis_advanced",
            expected={
                "deminimis_status": "COMPUTED",
                "deminimis_ratio": 0.10,
                "red_flags_should_include": ["RF007"],
            },
            difficulty="hard",
            step3=mixed_components,
            step4={
                "components": [comp("U.S.-origin module", "US", value=100000.0)],
                "total_foreign_product_value": 1000000.0,
            },
            notes="Every ratio >= 5% is treated identically; the 10% and 25% thresholds are not distinguished.",
        )
    )
    cases.append(
        case(
            "DMX-07",
            "Ratio exactly at 25%",
            "deminimis_advanced",
            expected={
                "deminimis_status": "COMPUTED",
                "deminimis_ratio": 0.25,
                "red_flags_should_include": ["RF007"],
            },
            difficulty="hard",
            step3=mixed_components,
            step4={
                "components": [comp("U.S.-origin module", "US", value=250000.0)],
                "total_foreign_product_value": 1000000.0,
            },
        )
    )
    cases.append(
        case(
            "DMX-08",
            "Non-U.S. components only, one with an unknown status",
            "deminimis_advanced",
            expected={"deminimis_status": "NO_CONTROLLED_US_CONTENT", "deminimis_ratio": 0.0},
            difficulty="hard",
            step3=mixed_components,
            step4={
                "components": [
                    comp("Japanese module", "JP", value=100000.0),
                    comp("Korean module", "KR", controlled="Unknown", value=90000.0),
                ],
                "total_foreign_product_value": 1000000.0,
            },
        )
    )
    cases.append(
        case(
            "DMX-09",
            "Controlled U.S. component recorded with a zero value",
            "deminimis_advanced",
            expected={"deminimis_status": "NO_CONTROLLED_US_CONTENT", "deminimis_ratio": 0.0},
            difficulty="hard",
            step3=mixed_components,
            step4={
                "components": [
                    comp(
                        "U.S.-origin bundled software licence (cost included in the item price)",
                        "US",
                        value=0.0,
                    )
                ],
                "total_foreign_product_value": 1000000.0,
            },
            known_issues=[
                "A controlled U.S. component entered with value 0 is treated as 'no controlled U.S. "
                "content' rather than as a missing value, so the ratio comes back as 0% instead of "
                "asking the reviewer for the real figure.",
            ],
        )
    )
    cases.append(
        case(
            "DMX-10",
            "Three controlled U.S. components summed for the numerator",
            "deminimis_advanced",
            expected={
                "deminimis_status": "COMPUTED",
                "deminimis_ratio": 0.27,
                "red_flags_should_include": ["RF007"],
            },
            step3=mixed_components,
            step4={
                "components": [
                    comp("U.S.-origin processor board", "US", value=120000.0),
                    comp("U.S.-origin firmware licence", "US", value=90000.0),
                    comp("U.S.-origin sensor package", "US", value=60000.0),
                    comp("Malaysian housing", "MY", controlled="No - EAR99", value=300000.0),
                ],
                "total_foreign_product_value": 1000000.0,
            },
        )
    )

    return cases


def main() -> None:
    cases = build_cases()
    payload = {
        "metadata": {
            "dataset_name": "ear_benchmark_v1",
            "version": 1,
            "case_count": len(cases),
            "screening_list": "benchmark/screening_list.csv",
            "notes": (
                "Hand-authored benchmark for the EAR Transaction Review Tool. All entities are "
                "fictitious. Expectations are derived from app/rules/*.json and app/data/country_data.json."
            ),
            "known_issues": [
                "The size of the de minimis ratio is never scored. RF007 is a boolean test (>= 5%) and "
                "the red-flag category is capped at 10 points, so ratios of 6.7%, 19%, 60% and even "
                "160% all return the same LOW 19/100 result (cases SW-11, SW-12, DMX-02, DMX-04).",
                "An incomplete de minimis calculation raises no red flag of its own. When a controlled "
                "U.S. component has no recorded value (MISSING_VALUE) the case still reaches "
                "AUTO_REVIEW_COMPLETE with LOW risk (cases SW-10 and DMX-01).",
                "Value edge cases are accepted silently: a controlled U.S. component entered with a "
                "value of 0 is read as 'no controlled U.S. content' (DMX-09), and a numerator larger "
                "than the declared total produces a 160% ratio with no validation warning (DMX-04).",
                "The red-flag category is capped at 10 points, so severe red flags (an embargoed "
                "destination, a high de minimis ratio) cannot lift the score band on their own. "
                "Routing still escalates because the queue rules read the underlying facts.",
                "Red flag findings carry an action field (for example LEGAL_REVIEW_REQUIRED) that the "
                "review queue rules never read; routing uses score bands and derived booleans only.",
                "The destination embargo check (RF003 / DST-01) reads ultimate_destination only, so a "
                "buyer in an embargoed country with an ultimate destination elsewhere does not trigger "
                "the embargo flag. Case DST-06 documents this behaviour.",
                "Software handling is keyword-only. Civilian software copy containing 'guidance' "
                "(SW-08) or 'targeting' (SW-14) raises RF004 and a military end-use flag, while "
                "encryption software is only noticed through a recorded 5D002 - the word 'encryption' "
                "is not modelled (SW-02).",
                "The de minimis step accepts a component row for software that was used in production "
                "rather than incorporated into the item, which can inflate the numerator and trigger "
                "RF007 on what is really an FDP question (SW-04).",
            ],
        },
        "cases": cases,
    }
    target = BENCHMARK_DIR / "cases.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {target} with {len(cases)} cases")
    families: dict[str, int] = {}
    for item in cases:
        families[item["family"]] = families.get(item["family"], 0) + 1
    for family, count in sorted(families.items()):
        print(f"  {family:16s} {count}")


if __name__ == "__main__":
    main()
