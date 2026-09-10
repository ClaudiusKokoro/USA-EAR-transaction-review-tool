"""Tests for the EAR jurisdiction review service (Step 3)."""

from __future__ import annotations

from app.models.review import (
    JURISDICTION_INSUFFICIENT,
    JURISDICTION_POSSIBLE,
    JURISDICTION_REVIEW_REQUIRED,
)
from app.services.jurisdiction_service import run_jurisdiction_review


def _questions(**overrides):
    defaults = {
        "is_us_origin": False,
        "has_us_origin_content": False,
        "us_content_value_known": None,
        "total_foreign_value_known": True,
        "us_software_used_in_production": False,
        "us_technology_used_in_production": False,
        "production_chain_known": True,
    }
    defaults.update(overrides)
    return defaults


def test_us_origin_item_is_possible_jurisdiction():
    result = run_jurisdiction_review(_questions(is_us_origin=True))
    assert result.status == JURISDICTION_POSSIBLE
    assert "U.S.-origin" in result.summary


def test_foreign_item_with_us_content_values_known():
    result = run_jurisdiction_review(
        _questions(
            is_us_origin=False,
            has_us_origin_content=True,
            us_content_value_known=True,
            total_foreign_value_known=True,
        )
    )
    assert result.status == JURISDICTION_POSSIBLE
    assert result.path == "FOREIGN_US_CONTENT"


def test_foreign_item_with_us_content_but_missing_values_requires_review():
    result = run_jurisdiction_review(
        _questions(
            is_us_origin=False,
            has_us_origin_content=True,
            us_content_value_known=False,
            total_foreign_value_known=False,
        )
    )
    assert result.status == JURISDICTION_REVIEW_REQUIRED
    assert any("value" in item for item in result.missing_information)


def test_missing_origin_question_is_insufficient():
    result = run_jurisdiction_review(_questions(is_us_origin=None))
    assert result.status == JURISDICTION_INSUFFICIENT


def test_us_software_in_production_keeps_jurisdiction_possible():
    result = run_jurisdiction_review(
        _questions(
            is_us_origin=False,
            has_us_origin_content=False,
            us_software_used_in_production=True,
            production_chain_known=True,
        )
    )
    assert result.status == JURISDICTION_POSSIBLE
    assert result.path == "FOREIGN_US_PRODUCTION_INPUTS"


def test_foreign_item_with_no_us_nexus_still_requires_formal_review():
    # The tool must never conclude "no EAR jurisdiction"; it routes to review instead.
    result = run_jurisdiction_review(_questions())
    assert result.status == JURISDICTION_REVIEW_REQUIRED
    assert result.path == "FOREIGN_NO_US_NEXUS"


def test_status_labels_are_not_definitive():
    labels = {
        JURISDICTION_POSSIBLE: "POSSIBLE EAR JURISDICTION",
        JURISDICTION_REVIEW_REQUIRED: "JURISDICTION REVIEW REQUIRED",
        JURISDICTION_INSUFFICIENT: "INSUFFICIENT INFORMATION",
    }
    assert "possible" in labels[JURISDICTION_POSSIBLE].lower()
    assert "required" in labels[JURISDICTION_REVIEW_REQUIRED].lower()

