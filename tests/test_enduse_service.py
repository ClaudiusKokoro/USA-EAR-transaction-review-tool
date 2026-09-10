"""Tests for the end-use review service (Step 7)."""

from __future__ import annotations

from app.models.review import END_USE_FLAG_INSUFFICIENT, END_USE_FLAG_LOCATION
from app.services.enduse_service import run_end_use_review


def test_clean_civil_use_has_no_flags():
    result = run_end_use_review(
        {
            "declared_end_use": "Retail sale of consumer electronics in authorized stores",
            "installation_location": "1 Orchard Road, Singapore",
            "industry": "Consumer electronics",
            "civil_use": True,
        }
    )
    assert result.flags == []


def test_missing_declared_use_and_location():
    result = run_end_use_review(
        {
            "declared_end_use": "",
            "installation_location": "",
            "industry": "",
            "unknown_use": True,
        }
    )
    keys = {flag.key for flag in result.flags}
    assert END_USE_FLAG_INSUFFICIENT in keys
    assert END_USE_FLAG_LOCATION in keys


def test_military_terms_detected():
    result = run_end_use_review(
        {
            "declared_end_use": "Integration into military radar targeting system",
            "installation_location": "Government facility, Paris",
            "industry": "Defense",
        }
    )
    keys = {flag.key for flag in result.flags}
    assert "military_related_indicators" in keys


def test_civil_and_military_selection_is_inconsistent():
    result = run_end_use_review(
        {
            "declared_end_use": "Distribution of networking equipment",
            "installation_location": "Industrial park, Singapore",
            "industry": "Telecommunications",
            "civil_use": True,
            "military_use": True,
        }
    )
    keys = {flag.key for flag in result.flags}
    assert "inconsistent_business_activity" in keys

