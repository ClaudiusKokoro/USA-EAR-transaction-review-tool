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
