"""Tests for the Risk Engine and review queue (Steps 9-10)."""

from __future__ import annotations

from examples.sample_transaction import build_sample_review
from app.models.review import (
    JURISDICTION_INSUFFICIENT,
    JURISDICTION_POSSIBLE,
    JURISDICTION_REVIEW_REQUIRED,
    DeMinimisResult,
    EndUseReviewInput,
    EndUseReviewResult,
    FDPReviewResult,
    JurisdictionQuestionSet,
    JurisdictionReviewResult,
)
from app.models.transaction import TransactionIntake
from app.services.risk_service import assemble_review_context, run_review_queue, run_risk_engine


def _low_risk_context() -> dict:
    transaction = TransactionIntake(
        transaction_name="Low-risk sample",
        exporter_name="Test Exporter Pte Ltd",
        exporter_country="SG",
        buyer_name="Known Buyer GmbH",
        buyer_country="DE",
        consignee=None,
        ultimate_end_user="End Customer AG",
        ultimate_destination="DE",
        transaction_value="1200.00",
        shipment_date=None,
    )
    context = assemble_review_context(
        transaction=transaction,
        product=None,
        jurisdiction_questions=JurisdictionQuestionSet(
            is_us_origin=False,
            has_us_origin_content=False,
            us_software_used_in_production=False,
            us_technology_used_in_production=False,
            production_chain_known=True,
        ),
        jurisdiction=JurisdictionReviewResult(
            status=JURISDICTION_POSSIBLE,
            status_label="POSSIBLE EAR JURISDICTION",
            path="FOREIGN_NO_US_NEXUS",
            summary="test",
        ),
        deminimis=DeMinimisResult(),
        fdp=FDPReviewResult(),
        end_use=EndUseReviewResult(
            input=EndUseReviewInput(
                declared_end_use="Commercial use in industrial automation",
                installation_location="Frankfurt facility",
                industry="Industrial automation",
                civil_use=True,
            )
        ),
    )
    return context


def test_risk_engine_returns_structured_categories():
    context = _low_risk_context()
    assessment, _ = run_risk_engine(context)
    assert set(assessment.categories.keys()) == {
        "jurisdiction",
        "product",
        "destination",
        "end_user",
        "end_use",
        "red_flags",
    }
    assert assessment.total <= assessment.max_total
    assert assessment.level in {"LOW", "MODERATE", "ELEVATED", "HIGH", "CRITICAL"}


def test_risk_engine_points_are_explained():
    sample = build_sample_review()
    context = assemble_review_context(
        transaction=sample.transaction,
        product=sample.product,
        jurisdiction_questions=sample.jurisdiction_questions,
        jurisdiction=sample.jurisdiction,
        deminimis=sample.deminimis,
        fdp=sample.fdp,
        parties=sample.parties,
        screening_output=sample.screening,
        end_use=sample.end_use,
    )
    assessment, enriched = run_risk_engine(context)
    total_awarded = sum(
        float(finding.points)
        for category in assessment.categories.values()
        for finding in category.findings
    )
    assert total_awarded > 0  # The sample should exercise the risk rules.
    assert assessment.total > 0
    # Every non-zero category has at least one explanation line.
    for category in assessment.categories.values():
        if category.points > 0:
            assert category.explanation_lines
            assert any("point" in line for line in category.explanation_lines)


def test_review_queue_routing_for_high_risk():
    context = _low_risk_context()
    context.update(
        {
            "risk_level": "CRITICAL",
            "risk_total": 90,
            "screening_has_manual_verification": True,
            "destination_embargoed": True,
        }
    )
    decision = run_review_queue(context)
    assert decision.decision == "EXTERNAL_COUNSEL_REVIEW_RECOMMENDED"
    assert decision.decision_label == "EXTERNAL COUNSEL REVIEW RECOMMENDED"
    assert decision.explanation


def test_review_queue_defaults_to_auto_complete():
    context = _low_risk_context()
    context.update({"risk_level": "LOW", "risk_total": 5})
    decision = run_review_queue(context)
    assert decision.decision == "AUTO_REVIEW_COMPLETE"
    assert decision.decision_label == "AUTO REVIEW COMPLETE"


def test_jurisdiction_insufficient_cannot_be_auto_complete():
    context = _low_risk_context()
    context.update(
        {
            "jurisdiction_status": JURISDICTION_INSUFFICIENT,
            "risk_level": "LOW",
            "risk_total": 5,
        }
    )
    decision = run_review_queue(context)
    assert decision.decision in {"LEGAL_REVIEW_REQUIRED", "EXTERNAL_COUNSEL_REVIEW_RECOMMENDED"}


def _de_minimis_context(ratio: float):
    context = _low_risk_context()
    context.update(
        {
            "jurisdiction_path": "FOREIGN_US_CONTENT",
            "de_minimis_computed": True,
            "de_minimis_ratio": ratio,
            "has_us_content": True,
        }
    )
    return context


def test_de_minimis_ratio_is_scored_by_magnitude():
    small, _ = run_risk_engine(_de_minimis_context(0.06))
    large, _ = run_risk_engine(_de_minimis_context(0.60))
    small_points = small.categories["jurisdiction"].points
    large_points = large.categories["jurisdiction"].points
    assert large_points > small_points
    small_rules = {finding.rule_id for finding in small.categories["jurisdiction"].findings}
    large_rules = {finding.rule_id for finding in large.categories["jurisdiction"].findings}
    assert "JUR-05" in small_rules
    assert "JUR-07" in large_rules
    assert large.total > small.total


def test_incomplete_de_minimis_scores_and_routes():
    context = _low_risk_context()
    context.update(
        {
            "jurisdiction_path": "FOREIGN_US_CONTENT",
            "has_us_content": True,
            "de_minimis_computed": False,
            "de_minimis_ratio": None,
        }
    )
    assessment, enriched = run_risk_engine(context)
    rules = {finding.rule_id for finding in assessment.categories["jurisdiction"].findings}
    assert "JUR-08" in rules
    assert enriched["red_flag_requires_legal"] is False
    decision = run_review_queue(enriched, risk=assessment)
    assert decision.decision == "COMPLIANCE_REVIEW_REQUIRED"


def test_red_flag_action_requires_legal_review():
    context = _low_risk_context()
    context.update({"risk_level": "LOW", "risk_total": 10, "red_flag_requires_legal": True})
    decision = run_review_queue(context)
    assert decision.decision == "LEGAL_REVIEW_REQUIRED"
    assert decision.matched_rule_id == "RQ-07"


def test_buyer_in_embargoed_country_scores_destination_risk():
    context = _low_risk_context()
    context.update({"buyer_country_embargoed": True, "destination_embargoed": False})
    assessment, _ = run_risk_engine(context)
    rules = {finding.rule_id for finding in assessment.categories["destination"].findings}
    assert "DST-04" in rules


def _product(description: str, eccn: str | None = None):
    from app.models.product import ProductInformation

    return ProductInformation(
        product_name="Test product",
        product_description=description,
        existing_eccn=eccn,
        existing_ear_status="Not determined" if eccn is None else "Controlled (ECCN)",
    )


def test_encryption_context_fact_detects_capability_without_classification():
    context = assemble_review_context(
        transaction=_low_risk_context_transaction(),
        product=_product("Commercial encryption toolkit for enterprise data pipelines"),
    )
    assert context["encryption_without_classification"] is True


def test_encryption_context_fact_ignores_negated_wording():
    context = assemble_review_context(
        transaction=_low_risk_context_transaction(),
        product=_product("Bench multimeter shipped with no encryption features"),
    )
    assert context["encryption_without_classification"] is False


def test_encryption_context_fact_ignores_items_with_an_eccn():
    context = assemble_review_context(
        transaction=_low_risk_context_transaction(),
        product=_product("Commercial encryption toolkit", eccn="5D002"),
    )
    assert context["encryption_without_classification"] is False


def _low_risk_context_transaction():
    return TransactionIntake(
        transaction_name="Encryption context sample",
        exporter_name="Test Exporter",
        exporter_country="US",
        buyer_name="Known Buyer GmbH",
        buyer_country="DE",
        ultimate_end_user="End Customer AG",
        ultimate_destination="DE",
        transaction_value="1000.00",
    )
