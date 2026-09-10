"""Tests for the Red Flag Engine (Step 8)."""

from __future__ import annotations

from app.services.redflag_service import evaluate_red_flag_rules


def _base_context() -> dict:
    return {
        "ultimate_end_user": "Verified End User Ltd",
        "ultimate_destination": "SG",
        "destination_embargoed": False,
        "buyer_country_embargoed": False,
        "product_military_terms": False,
        "product_description": "Industrial process controller",
        "has_eccn": True,
        "encryption_without_classification": False,
        "end_use_military_indicators": False,
        "screening_has_manual_verification": False,
        "screening_has_possible_match": False,
        "de_minimis_computed": False,
        "de_minimis_ratio": None,
        "fdp_potential": False,
        "jurisdiction_status": "POSSIBLE_EAR_JURISDICTION",
        "jurisdiction_path": "FOREIGN_NO_US_NEXUS",
    }


def test_no_triggers():
    result = evaluate_red_flag_rules(_base_context())
    assert result.findings == []
    assert result.total_points == 0


def test_unknown_end_user_triggers_rf001():
    context = _base_context()
    context["ultimate_end_user"] = None
    result = evaluate_red_flag_rules(context)
    assert any(finding.rule_id == "RF001" for finding in result.findings)


def test_embargo_destination_triggers_rf003():
    context = _base_context()
    context.update({"ultimate_destination": "IR", "destination_embargoed": True})
    result = evaluate_red_flag_rules(context)
    assert any(finding.rule_id == "RF003" for finding in result.findings)


def test_de_minimis_threshold_rule_requires_legal_review():
    context = _base_context()
    context.update({"de_minimis_computed": True, "de_minimis_ratio": 0.18})
    result = evaluate_red_flag_rules(context)
    finding = next((item for item in result.findings if item.rule_id == "RF007"), None)
    assert finding is not None
    assert finding.action == "LEGAL_REVIEW_REQUIRED"


def test_points_are_summed():
    context = _base_context()
    context.update(
        {
            "ultimate_end_user": None,
            "ultimate_destination": "IR",
            "destination_embargoed": True,
        }
    )
    result = evaluate_red_flag_rules(context)
    assert float(result.total_points) >= 40


def test_incomplete_de_minimis_triggers_rf010():
    context = _base_context()
    context.update({"jurisdiction_path": "FOREIGN_US_CONTENT", "de_minimis_computed": False})
    result = evaluate_red_flag_rules(context)
    assert any(finding.rule_id == "RF010" for finding in result.findings)


def test_incomplete_de_minimis_does_not_trigger_without_us_content():
    context = _base_context()
    context.update({"jurisdiction_path": "FOREIGN_US_PRODUCTION_INPUTS", "de_minimis_computed": False})
    result = evaluate_red_flag_rules(context)
    assert not any(finding.rule_id == "RF010" for finding in result.findings)


def test_encryption_without_classification_triggers_rf011():
    context = _base_context()
    context.update({"encryption_without_classification": True})
    result = evaluate_red_flag_rules(context)
    finding = next((item for item in result.findings if item.rule_id == "RF011"), None)
    assert finding is not None
    assert finding.action == "COMPLETE_CLASSIFICATION"


def test_encryption_with_a_recorded_eccn_does_not_trigger_rf011():
    context = _base_context()
    context.update({"encryption_without_classification": False})
    result = evaluate_red_flag_rules(context)
    assert not any(finding.rule_id == "RF011" for finding in result.findings)


def test_encryption_flag_stays_off_when_the_context_fact_is_false():
    context = _base_context()
    context.update({"encryption_without_classification": False})
    result = evaluate_red_flag_rules(context)
    assert not any(finding.rule_id == "RF011" for finding in result.findings)


def test_buyer_in_embargoed_country_triggers_rf012():
    context = _base_context()
    context.update({"buyer_country_embargoed": True, "ultimate_destination": "DE"})
    result = evaluate_red_flag_rules(context)
    finding = next((item for item in result.findings if item.rule_id == "RF012"), None)
    assert finding is not None
    assert finding.action == "LEGAL_REVIEW_REQUIRED"


def test_rule_errors_do_not_crash_the_engine():
    result = evaluate_red_flag_rules({})
    assert result.total_points == 0
    assert all(finding.risk_points == 0 for finding in result.findings)
