"""Report generator (Step 11): HTML report and downloadable PDF."""

from __future__ import annotations

import html
import io
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from string import Template
from typing import Any

from app.models.review import ReviewBundle
from app.paths import template_path
from app.services.jurisdiction_service import describe_status

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

DISCLAIMER = (
    "This tool provides a preliminary compliance risk assessment based on user-provided information "
    "and configurable rules. It does not constitute legal advice and does not determine whether an "
    "export, reexport, or transfer is authorized under the EAR."
)

ACTION_GUIDANCE = {
    "ENHANCED_DUE_DILIGENCE": "Perform enhanced due diligence on the parties and transaction before routing for decision.",
    "MANUAL_VERIFICATION_REQUIRED": "Manually verify the identity, geography, and ownership of the matching party against authoritative reference data.",
    "COMPLIANCE_VERIFICATION": "Compliance staff should verify the spelling and legal identity of the parties involved.",
    "OBTAIN_DESTINATION_FACTS": "Collect the ultimate destination country and confirm the final delivery route.",
    "LEGAL_REVIEW_REQUIRED": "Route this transaction to an export-control attorney or specialist for legal review.",
    "FDP_REVIEW": "Complete a Foreign Direct Product review of the production chain before proceeding.",
    "COMPLETE_JURISDICTION_REVIEW": "Complete an EAR jurisdiction review and record the supporting analysis.",
    "REVIEW": "Review the flagged item and document the resolution.",
}


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _money(value: Any, currency: str = "") -> str:
    if value is None or value == "":
        return ""
    try:
        amount = Decimal(str(value))
        formatted = f"{amount:,.2f}"
    except Exception:
        formatted = str(value)
    return f"{formatted} {currency}".strip() if currency else formatted


def _yes_no(value: Any) -> str:
    if value is None:
        return "Not provided"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if str(value).strip().casefold() in {"true", "yes", "y", "1"}:
        return "Yes"
    if str(value).strip().casefold() in {"false", "no", "n", "0"}:
        return "No"
    return str(value)


def _status_span(value: str) -> str:
    lowered = (value or "").lower()
    if "critical" in lowered:
        css = "critical"
    elif "high" in lowered:
        css = "high"
    elif "elevated" in lowered:
        css = "elevated"
    elif "moderate" in lowered:
        css = "moderate"
    elif "possible" in lowered or "potential" in lowered or "manual" in lowered:
        css = "elevated"
    elif "insufficient" in lowered or "required" in lowered or "flagged" in lowered:
        css = "moderate"
    else:
        css = "low"
    return f'<span class="status {css}">{_esc(value)}</span>'


def _screening_sections(bundle: ReviewBundle) -> list[dict[str, Any]]:
    rows = []
    for result in bundle.screening:
        best = result.best_match
        rows.append(
            {
                "role": result.party.role,
                "name": result.party.name,
                "country": result.party.country or "",
                "status": result.status.replace("_", " "),
                "score": f"{result.best_score:.4f}" if result.best_score is not None else "",
                "best_match": best.matched_name if best else "",
                "method": best.match_method if best else "",
                "reference": best.listed_reference if best else "",
                "explanation": result.explanation,
            }
        )
    return rows


def _collect_sections(bundle: ReviewBundle) -> list[dict[str, Any]]:
    transaction = bundle.transaction
    product = bundle.product
    jurisdiction = bundle.jurisdiction
    deminimis = bundle.deminimis
    fdp = bundle.fdp
    end_use = bundle.end_use
    red_flags = bundle.red_flags
    risk = bundle.risk
    queue = bundle.queue

    def attr(model: Any, name: str, default: Any = "") -> Any:
        return getattr(model, name, default) if model is not None else default

    currency = attr(transaction, "currency", "USD")
    sections: list[dict[str, Any]] = []

    # 1. Transaction Summary
    kv1 = [
        ("Transaction name", attr(transaction, "transaction_name")),
        ("Exporter", attr(transaction, "exporter_name")),
        ("Exporter country", attr(transaction, "exporter_country")),
        ("Buyer", attr(transaction, "buyer_name")),
        ("Buyer country", attr(transaction, "buyer_country")),
        ("Consignee", attr(transaction, "consignee")),
        ("Ultimate end user", attr(transaction, "ultimate_end_user")),
        ("Ultimate destination", attr(transaction, "ultimate_destination")),
        ("Transaction value", _money(attr(transaction, "transaction_value"), currency)),
        ("Shipment date", attr(transaction, "shipment_date")),
        ("Notes", attr(transaction, "notes")),
    ]
    sections.append({"title": "1. Transaction Summary", "items": [{"type": "kv", "pairs": kv1}]})

    # 2. Product Information
    kv2 = [
        ("Product name", attr(product, "product_name")),
        ("Model", attr(product, "model")),
        ("Description", attr(product, "product_description")),
        ("Category", attr(product, "category")),
        ("Manufacturer", attr(product, "manufacturer")),
        ("Country of manufacture", attr(product, "country_of_manufacture")),
        ("Existing ECCN", attr(product, "existing_eccn")),
        ("Existing EAR status", attr(product, "existing_ear_status")),
        ("Product value", _money(attr(product, "product_value"), currency)),
    ]
    sections.append({"title": "2. Product Information", "items": [{"type": "kv", "pairs": kv2}]})

    # 3. EAR Jurisdiction Review
    if jurisdiction is None:
        section3_paras = ["Jurisdiction review has not been run."]
    else:
        section3_paras = [
            f"Status: {describe_status(jurisdiction.status)}",
            jurisdiction.summary,
            "Reasons:",
            *[f"* {reason}" for reason in jurisdiction.reasons],
        ]
        if jurisdiction.missing_information:
            section3_paras.append("Missing information: " + "; ".join(jurisdiction.missing_information) + ".")
        section3_paras.append(
            "Legal note: This status is a preliminary review state, not a legal conclusion about jurisdiction."
        )
    sections.append({"title": "3. EAR Jurisdiction Review", "items": [{"type": "paragraphs", "paragraphs": section3_paras}]})

    # 4. De Minimis Calculation
    deminimis_items: list[dict[str, Any]] = []
    if deminimis is None:
        deminimis_items.append({"type": "paragraphs", "paragraphs": ["De minimis calculation has not been run."]})
    else:
        ratio_text = f"{float(deminimis.ratio) * 100:.2f}%" if deminimis.ratio is not None else "Not calculable"
        deminimis_items.append(
            {
                "type": "paragraphs",
                "paragraphs": [
                    f"Status: {deminimis.status.replace('_', ' ')}",
                    f"Controlled U.S.-origin content value: {_money(deminimis.controlled_us_content_value, currency)}",
                    f"Total foreign-product value: {_money(deminimis.total_foreign_product_value, currency)}",
                    f"Ratio (controlled U.S. content / total foreign product): {ratio_text}",
                    *[f"Warning: {warning}" for warning in deminimis.warnings],
                ],
            }
        )
        rows = [
            [
                component.component_name,
                component.origin or "",
                component.eccn or "",
                component.controlled_status,
                _money(component.component_value, currency),
            ]
            for component in deminimis.components
        ]
        deminimis_items.append(
            {
                "type": "table",
                "headers": ["Component", "Origin", "ECCN", "Controlled status", "Value"],
                "rows": rows,
            }
        )
        if deminimis.excluded_components:
            deminimis_items.append(
                {
                    "type": "paragraphs",
                    "paragraphs": ["Excluded components:", *[f"* {item}" for item in deminimis.excluded_components]],
                }
            )
    sections.append({"title": "4. De Minimis Calculation", "items": deminimis_items})

    # 5. FDP Review
    fdp_items: list[dict[str, Any]] = []
    if fdp is None:
        fdp_items.append({"type": "paragraphs", "paragraphs": ["FDP review has not been run."]})
    else:
        paragraphs = [f"FDP flag: {fdp.flag_label}", fdp.summary, *[f"Note: {note}" for note in fdp.notes]]
        if fdp.missing_information:
            paragraphs.append("Missing information: " + "; ".join(fdp.missing_information) + ".")
        fdp_items.append({"type": "paragraphs", "paragraphs": paragraphs})
        map_rows = [[entry.layer, entry.details] for entry in fdp.dependency_map]
        if map_rows:
            fdp_items.append({"type": "table", "headers": ["Layer", "Details"], "rows": map_rows})
        else:
            fdp_items.append({"type": "paragraphs", "paragraphs": ["No dependency-map entries were recorded."]})
    sections.append({"title": "5. FDP Review", "items": fdp_items})

    # 6. Party Screening
    screening_rows = _screening_sections(bundle)
    if not screening_rows:
        screening_items = [{"type": "paragraphs", "paragraphs": ["No parties were screened."]}]
    else:
        table_rows = [
            [
                row["role"],
                row["name"],
                row["country"],
                row["status"],
                row["score"],
                row["best_match"],
                row["method"],
            ]
            for row in screening_rows
        ]
        screening_items = [
            {
                "type": "table",
                "headers": ["Role", "Party", "Country", "Result", "Score", "Best match", "Match method"],
                "rows": table_rows,
            },
            {
                "type": "paragraphs",
                "paragraphs": [
                    "Screening note: A name match is an indicator requiring verification. It never establishes "
                    "that a party is a restricted party.",
                    *[f"* {row['role']}: {row['explanation']}" for row in screening_rows if row["explanation"]],
                ],
            },
        ]
    sections.append({"title": "6. Party Screening", "items": screening_items})

    # 7. End Use Review
    if end_use is None:
        use_items = [{"type": "paragraphs", "paragraphs": ["End-use review has not been run."]}]
    else:
        end_input = end_use.input
        kv = [
            ("Declared end use", end_input.declared_end_use),
            ("Installation location", end_input.installation_location),
            ("Industry", end_input.industry),
            ("Civil use", _yes_no(end_input.civil_use)),
            ("Military use", _yes_no(end_input.military_use)),
            ("Aerospace use", _yes_no(end_input.aerospace_use)),
            ("Semiconductor use", _yes_no(end_input.semiconductor_use)),
            ("Research use", _yes_no(end_input.research_use)),
            ("Unknown use", _yes_no(end_input.unknown_use)),
        ]
        use_items = [
            {"type": "kv", "pairs": kv},
            {"type": "paragraphs", "paragraphs": [end_use.summary]},
        ]
        flag_paragraphs = [f"* {flag.label}: {flag.detail}" for flag in end_use.flags]
        if flag_paragraphs:
            use_items.append({"type": "paragraphs", "paragraphs": ["Flags:", *flag_paragraphs]})
    sections.append({"title": "7. End Use Review", "items": use_items})

    # 8. Red Flags
    if red_flags is None or not red_flags.findings:
        rf_items = [
            {
                "type": "paragraphs",
                "paragraphs": ["No red flags matched the recorded facts and configured rules."],
            }
        ]
    else:
        rf_items = [
            {
                "type": "table",
                "headers": ["Rule", "Name", "Points", "Action", "Explanation"],
                "rows": [
                    [
                        finding.rule_id,
                        finding.name,
                        str(finding.risk_points),
                        finding.action,
                        finding.explanation,
                    ]
                    for finding in red_flags.findings
                ],
            }
        ]
    sections.append({"title": "8. Red Flags", "items": rf_items})

    # 9. Risk Assessment
    if risk is None:
        risk_items = [{"type": "paragraphs", "paragraphs": ["Risk assessment has not been run."]}]
    else:
        risk_rows = [
            [
                category.label,
                f"{category.points} / {category.max_points}",
            ]
            for category in risk.categories.values()
        ]
        risk_rows.append(["TOTAL", f"{risk.total} / {risk.max_total}"])
        risk_items = [
            {"type": "paragraphs", "paragraphs": [f"Overall risk level: {risk.level} ({risk.total} / {risk.max_total})"]},
            {"type": "table", "headers": ["Risk category", "Score"], "rows": risk_rows},
        ]
        for category in risk.categories.values():
            if category.findings:
                detail_lines = [f"* {line}" for line in category.explanation_lines]
                risk_items.append(
                    {
                        "type": "paragraphs",
                        "paragraphs": [f"{category.label} ({category.points} points) - point explanations:", *detail_lines],
                    }
                )
        risk_items.append({"type": "paragraphs", "paragraphs": [risk.methodology]})
    sections.append({"title": "9. Risk Assessment", "items": risk_items})

    # 10. Required Actions
    if queue is None:
        action_items = [{"type": "paragraphs", "paragraphs": ["Review queue decision has not been generated."]}]
    else:
        actions_paragraphs = [
            f"Queue decision: {queue.decision_label}",
            f"Matched rule: {queue.matched_rule_name or 'Default routing'}",
            queue.explanation,
        ]
        if red_flags is not None:
            action_codes = [finding.action for finding in red_flags.findings if finding.action]
            for code in dict.fromkeys(action_codes):
                guidance = ACTION_GUIDANCE.get(code, code)
                actions_paragraphs.append(f"* {code}: {guidance}")
        action_items = [{"type": "paragraphs", "paragraphs": actions_paragraphs}]
    sections.append({"title": "10. Required Actions", "items": action_items})

    # 11. Legal Review Notes
    notes = bundle.legal_review_notes.strip() or "No legal review notes were entered."
    sections.append(
        {"title": "11. Legal Review Notes", "items": [{"type": "paragraphs", "paragraphs": [notes]}]}
    )
    return sections


def _item_to_html(item: dict[str, Any]) -> str:
    kind = item.get("type")
    if kind == "kv":
        rows = "".join(
            f"<tr><th>{_esc(label)}</th><td>{_esc(value) if value is not None else ''}</td></tr>"
            for label, value in item["pairs"]
        )
        return f'<table class="kv">{rows}</table>'
    if kind == "table":
        header = "".join(f"<th>{_esc(column)}</th>" for column in item["headers"])
        body = "".join(
            "<tr>" + "".join(f"<td>{_esc(cell)}</td>" for cell in row) + "</tr>" for row in item["rows"]
        )
        return f'<table class="data"><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>'
    if kind == "paragraphs":
        chunks: list[str] = []
        for paragraph in item.get("paragraphs", []):
            if paragraph.startswith("* "):
                chunks.append(f"<li>{_esc(paragraph[2:])}</li>")
            else:
                chunks.append(f"<p>{_esc(paragraph)}</p>")
        text = "".join(chunks)
        if "<li>" in text:
            return f"<ul>{text}</ul>"
        return text
    return ""


def _build_executive_summary(bundle: ReviewBundle) -> str:
    transaction = bundle.transaction
    risk = bundle.risk
    queue = bundle.queue
    name = _esc(getattr(transaction, "transaction_name", "") if transaction else "")
    exporter = _esc(getattr(transaction, "exporter_name", "") if transaction else "")
    buyer = _esc(getattr(transaction, "buyer_name", "") if transaction else "")
    risk_text = f"{risk.level} ({risk.total} / {risk.max_total})" if risk else "Not run"
    queue_text = queue.decision_label if queue else "Not run"
    return (
        f"<p><strong>Transaction:</strong> {name or 'Untitled'} &mdash; {exporter} &rarr; {buyer}</p>"
        f"<p><strong>Preliminary risk level:</strong> {_status_span(str(risk_text))}</p>"
        f"<p><strong>Review queue:</strong> {_esc(queue_text)}</p>"
        f"<p>This summary is generated from user-entered facts and configurable rules. It is not a legal "
        f"conclusion that the transaction is or is not authorized under the EAR.</p>"
    )


def build_html_report(bundle: ReviewBundle) -> str:
    """Render the full HTML report from the template."""

    template_source = template_path("report.html").read_text(encoding="utf-8")
    sections_html = "".join(
        f"<h2>{_esc(section['title'])}</h2>" + "".join(_item_to_html(item) for item in section["items"])
        for section in _collect_sections(bundle)
    )
    generated = bundle.generated_at.strftime("%Y-%m-%d %H:%M UTC")
    return Template(template_source).safe_substitute(
        generated_at=generated,
        executive_summary=_build_executive_summary(bundle),
        sections_html=sections_html,
    )


# ---------------------------------------------------------------------------
# PDF rendering
# ---------------------------------------------------------------------------

pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))


def _pdf_styles() -> dict[str, ParagraphStyle]:
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "EARBody",
        parent=styles["BodyText"],
        fontName="STSong-Light",
        fontSize=9.5,
        leading=13,
        spaceAfter=5,
    )
    heading = ParagraphStyle(
        "EARHeading",
        parent=styles["Heading2"],
        fontName="STSong-Light",
        fontSize=13,
        leading=17,
        spaceBefore=12,
        textColor=colors.HexColor("#0b5394"),
    )
    title_style = ParagraphStyle(
        "EARTitle",
        parent=styles["Title"],
        fontName="STSong-Light",
        fontSize=19,
        alignment=TA_CENTER,
    )
    subtitle = ParagraphStyle(
        "EARSubtitle",
        parent=body,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#59636e"),
    )
    return {"body": body, "heading": heading, "title": title_style, "subtitle": subtitle}


def _paragraph_safe(value: str) -> str:
    return html.escape("" if value is None else str(value)).replace("\n", "<br/>")


def _build_pdf_story(bundle: ReviewBundle) -> list[Any]:
    styles = _pdf_styles()
    story: list[Any] = [
        Paragraph("EAR Transaction Review Report", styles["title"]),
        Paragraph(
            "Preliminary, rule-based compliance risk assessment - not legal advice",
            styles["subtitle"],
        ),
        Spacer(1, 8),
    ]
    transaction = bundle.transaction
    if transaction:
        story.append(
            Paragraph(
                _paragraph_safe(
                    f"Transaction: {transaction.transaction_name}  |  Exporter: {transaction.exporter_name}  |  "
                    f"Buyer: {transaction.buyer_name}"
                ),
                styles["body"],
            )
        )
    risk = bundle.risk
    queue = bundle.queue
    if risk:
        story.append(Paragraph(_paragraph_safe(f"Preliminary risk level: {risk.level} ({risk.total} / {risk.max_total})"), styles["body"]))
    if queue:
        story.append(Paragraph(_paragraph_safe(f"Review queue decision: {queue.decision_label}"), styles["body"]))
    disclaimer = ParagraphStyle(
        "EARDisclaimer",
        parent=styles["body"],
        backColor=colors.HexColor("#fff8c5"),
        borderColor=colors.HexColor("#d4a72c"),
        borderWidth=0.8,
        borderPadding=6,
        spaceBefore=8,
        spaceAfter=8,
    )
    story.append(Paragraph(_paragraph_safe(DISCLAIMER), disclaimer))

    sections = _collect_sections(bundle)
    for section in sections:
        story.append(Paragraph(_paragraph_safe(section["title"]), styles["heading"]))
        for item in section["items"]:
            kind = item.get("type")
            if kind == "paragraphs":
                for paragraph in item.get("paragraphs", []):
                    if paragraph.startswith("* "):
                        paragraph = "&bull; " + paragraph[2:]
                    story.append(Paragraph(_paragraph_safe(paragraph), styles["body"]))
            elif kind == "kv":
                data = [[_paragraph_safe(label), _paragraph_safe(value)] for label, value in item["pairs"]]
                table = Table(data, colWidths=[52 * mm, 118 * mm])
                table.setStyle(
                    TableStyle(
                        [
                            ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
                            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f6f8fa")),
                            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d9e0")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 5),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                            ("TOPPADDING", (0, 0), (-1, -1), 4),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ]
                    )
                )
                story.append(table)
            elif kind == "table":
                if item.get("rows"):
                    data = [[_paragraph_safe(cell) for cell in item["headers"]], *[[_paragraph_safe(cell) for cell in row] for row in item["rows"]]]
                    table = Table(data, repeatRows=1)
                    table.setStyle(
                        TableStyle(
                            [
                                ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
                                ("FONTSIZE", (0, 0), (-1, -1), 8),
                                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f6f8fa")),
                                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d9e0")),
                                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                                ("TOPPADDING", (0, 0), (-1, -1), 3),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                            ]
                        )
                    )
                    story.append(table)
    story.append(Spacer(1, 12))
    story.append(Paragraph(_paragraph_safe(DISCLAIMER), disclaimer))
    story.append(
        Paragraph(
            _paragraph_safe(f"Generated: {bundle.generated_at.strftime('%Y-%m-%d %H:%M UTC')} by the EAR Transaction Review Tool."),
            styles["body"],
        )
    )
    return story


def build_pdf_report(bundle: ReviewBundle) -> bytes:
    """Return PDF bytes for the review bundle."""

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="EAR Transaction Review Report",
        author="EAR Transaction Review Tool",
    )
    document.build(_build_pdf_story(bundle))
    return buffer.getvalue()


def report_disclaimer() -> str:
    return DISCLAIMER
