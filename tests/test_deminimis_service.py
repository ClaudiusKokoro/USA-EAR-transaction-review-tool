"""Tests for the de minimis calculator (Step 4)."""

from __future__ import annotations

from app.models.review import (
    DE_MINIMIS_COMPUTED,
    DE_MINIMIS_MISSING_INPUT,
    DE_MINIMIS_MISSING_TOTAL,
    DE_MINIMIS_MISSING_VALUE,
    DE_MINIMIS_NO_CONTROLLED_US_CONTENT,
)
from app.services.deminimis_service import run_de_minimis


def test_ratio_calculation():
    result = run_de_minimis(
        [
            {"component_name": "U.S. controller IC", "origin": "US", "eccn": "3A001",
             "controlled_status": "Yes - controlled", "component_value": 2500},
            {"component_name": "U.S. memory module", "origin": "United States", "eccn": "5A991",
             "controlled_status": "No - EAR99", "component_value": 500},
        ],
        total_foreign_product_value=10000,
    )
    assert result.status == DE_MINIMIS_COMPUTED
    assert float(result.controlled_us_content_value) == 2500.0
    assert float(result.ratio) == 0.25
    assert any("legal" in warning.lower() for warning in result.warnings)


def test_missing_value_returns_unknown():
    result = run_de_minimis(
        [{"component_name": "Chip A", "origin": "US", "controlled_status": "Yes", "component_value": None}],
        total_foreign_product_value=1000,
    )
    assert result.status == DE_MINIMIS_MISSING_VALUE
    assert result.ratio is None


def test_missing_total():
    result = run_de_minimis(
        [{"component_name": "Chip A", "origin": "US", "controlled_status": "Yes", "component_value": 100}],
        total_foreign_product_value=None,
    )
    assert result.status == DE_MINIMIS_MISSING_TOTAL


def test_no_us_origin_components_is_zero():
    result = run_de_minimis(
        [{"component_name": "Local housing", "origin": "CN", "controlled_status": "No - EAR99",
          "component_value": 300}],
        total_foreign_product_value=1000,
    )
    assert result.status == DE_MINIMIS_NO_CONTROLLED_US_CONTENT
    assert float(result.ratio) == 0.0


def test_no_components():
    result = run_de_minimis([], total_foreign_product_value=1000)
    assert result.status == DE_MINIMIS_MISSING_INPUT


def test_output_never_uses_definitive_language():
    result = run_de_minimis(
        [{"component_name": "Chip A", "origin": "US", "controlled_status": "Yes", "component_value": 500}],
        total_foreign_product_value=1000,
    )
    text = " ".join(result.warnings + result.notes).lower()
    assert "no license is required" not in text
    assert "legal review" in text


def test_zero_value_component_is_excluded_with_a_warning():
    result = run_de_minimis(
        [
            {
                "component_name": "Bundled U.S. licence",
                "origin": "US",
                "controlled_status": "Yes - controlled",
                "component_value": 0,
            }
        ],
        total_foreign_product_value=1000,
    )
    assert result.status == DE_MINIMIS_NO_CONTROLLED_US_CONTENT
    assert any("zero value" in warning.lower() for warning in result.warnings)
    assert result.excluded_components


def test_production_only_component_is_excluded_from_the_numerator():
    result = run_de_minimis(
        [
            {
                "component_name": "U.S. build toolchain licence",
                "origin": "US",
                "controlled_status": "Yes - controlled",
                "component_value": 200000,
                "incorporated": False,
            },
            {
                "component_name": "U.S. controller board",
                "origin": "US",
                "controlled_status": "Yes - controlled",
                "component_value": 50000,
                "incorporated": True,
            },
        ],
        total_foreign_product_value=1000000,
    )
    assert result.status == DE_MINIMIS_COMPUTED
    assert float(result.controlled_us_content_value) == 50000.0
    assert float(result.ratio) == 0.05
    assert any("production only" in warning.lower() for warning in result.warnings)


def test_ratio_above_one_hundred_percent_warns():
    result = run_de_minimis(
        [
            {
                "component_name": "U.S. subsystem",
                "origin": "US",
                "controlled_status": "Yes - controlled",
                "component_value": 800000,
            }
        ],
        total_foreign_product_value=500000,
    )
    assert result.status == DE_MINIMIS_COMPUTED
    assert float(result.ratio) == 1.6
    assert any("greater than the total value" in warning.lower() for warning in result.warnings)
