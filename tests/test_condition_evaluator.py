"""Tests for the JSON rule expression evaluator."""

from __future__ import annotations

import pytest

from app.rule_evaluator import RuleExpressionError, evaluate_condition


def test_null_comparison():
    assert evaluate_condition("ultimate_end_user == null", {"ultimate_end_user": None}) is True
    assert evaluate_condition("ultimate_end_user == null", {"ultimate_end_user": "Acme"}) is False


def test_string_comparison_and_contains():
    context = {
        "product_description": "military grade radar system",
        "destination_embargoed": True,
    }
    assert evaluate_condition("contains(product_description, 'military')", context) is True
    assert evaluate_condition("contains(product_description, 'consumer')", context) is False
    assert evaluate_condition(
        "destination_embargoed == true and contains(product_description, 'radar')", context
    ) is True


def test_not_and_or():
    assert evaluate_condition("not end_use_military", {"end_use_military": False}) is True
    assert evaluate_condition(
        "end_use_military == true or aerospace == true", {"end_use_military": False, "aerospace": True}
    ) is True


def test_numeric_comparisons_and_functions():
    context = {"de_minimis_ratio": 0.12, "total": 10}
    assert evaluate_condition("de_minimis_ratio >= 0.10 and de_minimis_ratio < 1", context) is True
    assert evaluate_condition("total > 5 and total * 2 == 20", context) is True
    assert evaluate_condition("strip(str(name)) == 'Acme'", {"name": "  Acme  "}) is True


def test_isin():
    context = {"destination_country": "IR", "special": ["IR", "KP", "SY"]}
    assert evaluate_condition("isin(destination_country, special)", context) is True


def test_unknown_field_rejected():
    with pytest.raises(RuleExpressionError):
        evaluate_condition("nonexistent_field == true", {})


def test_attribute_access_rejected():
    with pytest.raises(RuleExpressionError):
        evaluate_condition("obj.field == 1", {"obj": {}})


def test_arbitrary_function_rejected():
    with pytest.raises(RuleExpressionError):
        evaluate_condition("__import__('os').getcwd() == ''", {})

