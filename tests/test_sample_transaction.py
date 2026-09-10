"""End-to-end test of the complete sample transaction workflow."""

from __future__ import annotations

from examples.sample_transaction import build_sample_review
from app.services.report_service import (
    DISCLAIMER,
    build_html_report,
    build_pdf_report,
)


def test_sample_review_uses_expected_scenario():
    bundle = build_sample_review()
    assert bundle.transaction.exporter_country == "CN"
    assert bundle.transaction.buyer_country == "SG"
    assert bundle.transaction.ultimate_end_user is None
    assert bundle.product.country_of_manufacture == "CN"


def test_sample_jurisdiction_and_fdp_results():
    bundle = build_sample_review()
    assert bundle.jurisdiction.status == "POSSIBLE_EAR_JURISDICTION"
    assert bundle.fdp.flag == "POTENTIAL_FDP_ISSUE"


def test_sample_end_user_missing_creates_red_flag_and_risk():
    bundle = build_sample_review()
    assert any(finding.rule_id == "RF001" for finding in bundle.red_flags.findings)
    end_user_score = bundle.risk.categories["end_user"].points
    assert end_user_score > 0
    assert bundle.risk.total > 0


def test_sample_never_outputs_definitive_conclusions():
    bundle = build_sample_review()
    html = build_html_report(bundle)
    lowered = html.casefold()
    for forbidden in (
        "this transaction is legal",
        "no license is required",
        "this transaction violates the ear",
        "no license required",
    ):
        assert forbidden not in lowered
    assert DISCLAIMER in html


def test_html_report_contains_required_sections():
    bundle = build_sample_review()
    html = build_html_report(bundle)
    for heading in (
        "1. Transaction Summary",
        "2. Product Information",
        "3. EAR Jurisdiction Review",
        "4. De Minimis Calculation",
        "5. FDP Review",
        "6. Party Screening",
        "7. End Use Review",
        "8. Red Flags",
        "9. Risk Assessment",
        "10. Required Actions",
        "11. Legal Review Notes",
    ):
        assert heading in html


def test_pdf_report_generates_bytes():
    bundle = build_sample_review()
    pdf = build_pdf_report(bundle)
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF")


def test_queue_decision_reflects_fdp_issue():
    bundle = build_sample_review()
    # FDP review was flagged, so the sample cannot route to AUTO REVIEW COMPLETE.
    assert bundle.queue.decision in {"LEGAL_REVIEW_REQUIRED", "EXTERNAL_COUNSEL_REVIEW_RECOMMENDED"}

