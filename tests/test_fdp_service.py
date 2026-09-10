"""Tests for the FDP review service (Step 5)."""

from __future__ import annotations

from app.models.review import FDP_INSUFFICIENT, FDP_NO_FACTS, FDP_POTENTIAL
from app.services.fdp_service import run_fdp_review


def test_no_facts():
    result = run_fdp_review({})
    assert result.flag == FDP_NO_FACTS
    assert result.flag_label == "NO FDP FACTS IDENTIFIED"


def test_potential_issue_with_us_software_and_production_chain():
    result = run_fdp_review(
        {
            "us_software_used": "US-origin test software v2.4",
            "foreign_production_facilities": "Factory B, Shenzhen",
            "production_equipment": "Automated test station",
            "production_process_description": "Firmware validation with US software",
        }
    )
    assert result.flag == FDP_POTENTIAL
    assert result.flag_label == "POTENTIAL FDP ISSUE"
    assert len(result.dependency_map) >= 4


def test_insufficient_chain_details():
    result = run_fdp_review(
        {
            "us_software_used": "US-origin tooling",
            "us_technology_used": "",
            "foreign_production_facilities": "",
            "production_equipment": "",
            "production_process_description": "",
        }
    )
    assert result.flag == FDP_INSUFFICIENT
    assert result.missing_information


def test_production_without_us_inputs_is_no_fdp():
    result = run_fdp_review(
        {
            "foreign_production_facilities": "Factory A, Malaysia",
            "production_process_description": "Assembly only, no U.S. inputs",
        }
    )
    assert result.flag == FDP_NO_FACTS

