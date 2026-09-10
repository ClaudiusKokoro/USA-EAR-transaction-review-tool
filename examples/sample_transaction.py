"""Sample EAR transaction review for a Chinese exporter / Singapore buyer.

Run directly to generate HTML and PDF reports:

    python examples/sample_transaction.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.models.party import PartyToScreen  # noqa: E402
from app.models.product import ProductInformation  # noqa: E402
from app.models.review import (  # noqa: E402
    EndUseReviewInput,
    FDPReviewInput,
    JurisdictionQuestionSet,
    ReviewBundle,
)
from app.models.transaction import TransactionIntake  # noqa: E402
from app.services import deminimis_service, enduse_service, fdp_service  # noqa: E402
from app.services import jurisdiction_service, redflag_service, report_service  # noqa: E402
from app.services import risk_service, screening_service  # noqa: E402


def build_sample_review(legal_notes: str = "") -> ReviewBundle:
    transaction = TransactionIntake(
        transaction_name="SN-2026-0715 Singapore Distribution",
        exporter_name="Shenzhen Horizon Electronics Co., Ltd.",
        exporter_country="CN",
        buyer_name="Meridian Pacific Electronics Pte. Ltd.",
        buyer_country="SG",
        consignee="Meridian Pacific Logistics Hub",
        ultimate_end_user=None,  # Intentionally incomplete: drives RF001 and end-user risk.
        ultimate_destination="SG",
        transaction_value="850000.00",
        currency="USD",
        shipment_date=date(2026, 7, 15),
        notes="Foreign-produced networking hardware distributed through a Singapore trading hub.",
    )
    product = ProductInformation(
        product_name="VX-990 Smart Network Switch",
        model="VX-990-48T",
        product_description=(
            "Commercial 48-port Ethernet network switch for enterprise and data-center use. "
            "Assembled in China from foreign-origin parts."
        ),
        category="Electronics",
        manufacturer="Shenzhen Horizon Electronics Co., Ltd.",
        country_of_manufacture="CN",
        existing_eccn=None,
        existing_ear_status="Not determined",
        product_value="850000.00",
    )
    jurisdiction_questions = JurisdictionQuestionSet(
        is_us_origin=False,
        has_us_origin_content=False,
        us_content_value_known=None,
        total_foreign_value_known=True,
        us_software_used_in_production=True,
        us_technology_used_in_production=False,
        production_chain_known=True,
        additional_notes="U.S.-origin embedded test software is used during production-line firmware validation.",
    )
    jurisdiction = jurisdiction_service.run_jurisdiction_review(jurisdiction_questions)

    deminimis = deminimis_service.run_de_minimis(
        components=[],
        total_foreign_product_value=product.product_value,
    )

    fdp = fdp_service.run_fdp_review(
        FDPReviewInput(
            us_software_used="US-Origin TestSuite firmware loader v2.4 (production test station)",
            us_technology_used="",
            foreign_production_facilities="Shenzhen Horizon Electronics - Fab B, Shenzhen, China",
            production_equipment="Automated test station with U.S.-origin firmware loader",
            production_process_description=(
                "Surface-mount assembly followed by automated firmware validation on a U.S.-origin "
                "software-driven test station."
            ),
        )
    )

    parties = [
        PartyToScreen(
            name=transaction.exporter_name,
            role="Exporter",
            country=transaction.exporter_country,
        ),
        PartyToScreen(name=transaction.buyer_name, role="Buyer", country=transaction.buyer_country),
        PartyToScreen(
            name=transaction.consignee or "",
            role="Consignee",
            country=transaction.ultimate_destination,
        ),
    ]
    screening = screening_service.screen_parties(parties)

    end_use = enduse_service.run_end_use_review(
        EndUseReviewInput(
            declared_end_use="Wholesale distribution of commercial networking switches to enterprise customers",
            installation_location="Singapore regional distribution center",
            industry="Telecommunications / Networking",
            civil_use=True,
            military_use=False,
            aerospace_use=False,
            semiconductor_use=False,
            research_use=False,
            unknown_use=False,
            additional_notes="No specific downstream end user identified at intake.",
        )
    )

    context = risk_service.assemble_review_context(
        transaction=transaction,
        product=product,
        jurisdiction_questions=jurisdiction_questions,
        jurisdiction=jurisdiction,
        deminimis=deminimis,
        fdp=fdp,
        parties=parties,
        screening_output=screening,
        end_use=end_use,
    )
    red_flags = redflag_service.evaluate_red_flag_rules(context)
    risk, enriched_context = risk_service.run_risk_engine(context, red_flags=red_flags)
    queue = risk_service.run_review_queue(enriched_context, risk=risk)

    return ReviewBundle(
        transaction=transaction,
        product=product,
        jurisdiction_questions=jurisdiction_questions,
        jurisdiction=jurisdiction,
        deminimis=deminimis,
        fdp=fdp,
        parties=parties,
        screening=screening.results,
        end_use=end_use,
        red_flags=red_flags,
        risk=risk,
        queue=queue,
        legal_review_notes=legal_notes,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the sample EAR transaction review report.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "reports",
        help="Directory for generated sample_report.html / .pdf",
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    bundle = build_sample_review(
        legal_notes=(
            "Preliminary intake review. Ultimate end user not yet identified; enhanced due diligence "
            "and FDP legal review remain open."
        )
    )
    html_path = args.output_dir / "sample_report.html"
    pdf_path = args.output_dir / "sample_report.pdf"
    html_path.write_text(report_service.build_html_report(bundle), encoding="utf-8")
    pdf_path.write_bytes(report_service.build_pdf_report(bundle))

    print(f"Sample review generated: {html_path}")
    print(f"Sample review generated: {pdf_path}")
    if bundle.risk:
        print(f"Preliminary risk: {bundle.risk.level} ({bundle.risk.total}/{bundle.risk.max_total})")
    if bundle.queue:
        print(f"Review queue: {bundle.queue.decision_label}")
    for finding in bundle.red_flags.findings:
        print(f"Red flag: {finding.rule_id} {finding.name} ({finding.risk_points} pts)")


if __name__ == "__main__":
    main()

