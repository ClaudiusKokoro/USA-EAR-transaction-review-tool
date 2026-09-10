"""Risk Engine and legal review queue service (Steps 9-10).

The risk engine loads every point allocation from ``app/rules/risk_rules.json``.
No scoring threshold is hardcoded in Python. Every point awarded is recorded as
a RiskFinding with an explanation so the report can account for the total.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from app.models.party import (
    SCREENING_MANUAL_VERIFICATION,
    SCREENING_POSSIBLE_MATCH,
    PartyScreeningResult,
    ScreeningOutput,
)
from app.models.review import (
    JURISDICTION_INSUFFICIENT,
    JURISDICTION_POSSIBLE,
    JURISDICTION_REVIEW_REQUIRED,
    DeMinimisResult,
    EndUseReviewResult,
    FDPReviewResult,
    JurisdictionQuestionSet,
    JurisdictionReviewResult,
    ReviewQueueDecision,
    RiskAssessment,
    RiskCategoryScore,
    RiskFinding,
)
from app.models.transaction import TransactionIntake
from app.paths import rule_path
from app.rule_evaluator import evaluate_condition
from app.services.enduse_service import MILITARY_TERMS
from app.services.json_files import load_json_file
from app.services.redflag_service import evaluate_red_flag_rules

CATEGORY_LABELS = {
    "jurisdiction": "EAR Jurisdiction Risk",
    "product": "Product Risk",
    "destination": "Destination Risk",
    "end_user": "End User Risk",
    "end_use": "End Use Risk",
    "red_flags": "Red Flags",
}

CATEGORY_ORDER = ["jurisdiction", "product", "destination", "end_user", "end_use", "red_flags"]


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _truthy_military(text: str) -> bool:
    lowered = text.casefold()
    return any(term in lowered for term in MILITARY_TERMS)


def _ear_status_code(existing_status: str | None, eccn: str | None) -> str:
    status = _clean_text(existing_status).upper()
    if not status and eccn:
        return "CONTROLLED"
    if any(token in status for token in ("EAR99",)):
        return "EAR99"
    if any(token in status for token in ("CONTROLLED", "ECCN", "CCL")):
        return "CONTROLLED"
    if any(token in status for token in ("NOT U.S.", "NOT US", "NOT BELIEVED")):
        return "NOT_US_ORIGIN"
    if any(token in status for token in ("NOT DETERMINED", "UNKNOWN", "UNDETERMINED")):
        return "NOT_DETERMINED"
    return "UNKNOWN"


def _has_eccn(eccn: str | None) -> bool:
    value = _clean_text(eccn).upper()
    if not value or value in {"UNKNOWN", "TBD", "N/A", "NA", "NONE", "NO"}:
        return False
    return True


def _load_country_data() -> dict[str, Any]:
    from app.paths import data_path

    return load_json_file(data_path("country_data.json"))


def _destination_groups(country_data: dict[str, Any]) -> dict[str, set[str]]:
    groups: dict[str, set[str]] = {}
    for key, group in (country_data.get("destination_groups") or {}).items():
        groups[key] = {str(code).upper() for code in (group.get("codes") or [])}
    return groups


def _screening_status_for_role(
    screening_output: ScreeningOutput | None,
    role_tokens: tuple[str, ...],
) -> str | None:
    if not screening_output:
        return None
    for result in screening_output.results:
        role = (result.party.role or "").casefold()
        if any(token in role for token in role_tokens):
            return result.status
    return None


def assemble_review_context(
    transaction: TransactionIntake | dict | None = None,
    product: Any | None = None,
    jurisdiction_questions: JurisdictionQuestionSet | dict | None = None,
    jurisdiction: JurisdictionReviewResult | None = None,
    deminimis: DeMinimisResult | None = None,
    fdp: FDPReviewResult | None = None,
    parties: list[Any] | None = None,
    screening_output: ScreeningOutput | list[PartyScreeningResult] | None = None,
    end_use: EndUseReviewResult | None = None,
) -> dict[str, Any]:
    """Flatten review models into the single fact namespace used by JSON rules."""

    transaction_obj = (
        transaction
        if isinstance(transaction, TransactionIntake)
        else TransactionIntake.model_validate(transaction or {}) if transaction else None
    )
    product_obj = product
    questions_obj = (
        jurisdiction_questions
        if isinstance(jurisdiction_questions, JurisdictionQuestionSet)
        else JurisdictionQuestionSet.model_validate(jurisdiction_questions or {}) if jurisdiction_questions else None
    )

    def field(model: Any, name: str, default: Any = None) -> Any:
        return getattr(model, name, default) if model is not None else default

    # Screening output normalisation.
    screening_obj: ScreeningOutput | None = None
    if isinstance(screening_output, ScreeningOutput):
        screening_obj = screening_output
    elif isinstance(screening_output, list):
        screening_obj = ScreeningOutput(results=screening_output)
    elif screening_output is not None and not isinstance(screening_output, (ScreeningOutput, list)):
        screening_obj = ScreeningOutput.model_validate(screening_output)

    product_text = " ".join(
        filter(
            None,
            [
                field(product_obj, "product_name", ""),
                field(product_obj, "product_description", ""),
                field(product_obj, "category", ""),
            ],
        )
    )

    destination_code = field(transaction_obj, "ultimate_destination", None)
    buyer_country = field(transaction_obj, "buyer_country", None)

    country_data = _load_country_data()
    groups = _destination_groups(country_data)
    destination_embargoed = bool(destination_code and destination_code.upper() in groups.get("US_EMBARGO", set()))
    destination_special = bool(destination_code and destination_code.upper() in groups.get("SPECIAL_ATTENTION", set()))
    if not destination_code and buyer_country:
        destination_special = bool(buyer_country.upper() in groups.get("SPECIAL_ATTENTION", set()))

    context: dict[str, Any] = {
        # Transaction facts
        "transaction_name": field(transaction_obj, "transaction_name"),
        "exporter_name": field(transaction_obj, "exporter_name"),
        "exporter_country": field(transaction_obj, "exporter_country"),
        "buyer_name": field(transaction_obj, "buyer_name"),
        "buyer_country": buyer_country,
        "consignee": field(transaction_obj, "consignee"),
        "ultimate_end_user": field(transaction_obj, "ultimate_end_user"),
        "ultimate_destination": destination_code,
        "transaction_value": _to_float(field(transaction_obj, "transaction_value")),
        "currency": field(transaction_obj, "currency", "USD"),
        "shipment_date": (
            field(transaction_obj, "shipment_date").isoformat()
            if isinstance(field(transaction_obj, "shipment_date"), date)
            else field(transaction_obj, "shipment_date")
        ),
        # Product facts
        "product_name": field(product_obj, "product_name"),
        "product_category": field(product_obj, "category"),
        "product_description": field(product_obj, "product_description"),
        "product_country_of_manufacture": field(product_obj, "country_of_manufacture"),
        "existing_eccn": field(product_obj, "existing_eccn"),
        "has_eccn": _has_eccn(field(product_obj, "existing_eccn")) if product_obj is not None else False,
        "existing_ear_status": (
            _ear_status_code(field(product_obj, "existing_ear_status"), field(product_obj, "existing_eccn"))
            if product_obj is not None
            else None
        ),
        "product_value": _to_float(field(product_obj, "product_value")),
        "product_value_known": field(product_obj, "product_value") is not None,
        "product_military_terms": _truthy_military(product_text),
        # Jurisdiction question facts
        "is_us_origin": field(questions_obj, "is_us_origin"),
        "has_us_content": field(questions_obj, "has_us_origin_content"),
        "us_content_value_known": field(questions_obj, "us_content_value_known"),
        "total_foreign_value_known": field(questions_obj, "total_foreign_value_known"),
        "us_software_used_in_production": field(questions_obj, "us_software_used_in_production"),
        "us_technology_used_in_production": field(questions_obj, "us_technology_used_in_production"),
        "production_chain_known": field(questions_obj, "production_chain_known"),
        "jurisdiction_status": field(jurisdiction, "status"),
        "jurisdiction_path": field(jurisdiction, "path"),
        # De minimis facts
        "de_minimis_computed": field(deminimis, "ratio") is not None if deminimis is not None else False,
        "de_minimis_ratio": _to_float(field(deminimis, "ratio")),
        "controlled_us_content_value": _to_float(field(deminimis, "controlled_us_content_value")),
        "total_foreign_product_value": _to_float(field(deminimis, "total_foreign_product_value")),
        "has_controlled_us_content": (
            _to_decimal(field(deminimis, "controlled_us_content_value", 0)) > 0 if deminimis is not None else False
        ),
        # FDP facts
        "fdp_flag": field(fdp, "flag"),
        "fdp_potential": bool(fdp is not None and fdp.flag == "POTENTIAL_FDP_ISSUE"),
        "fdp_insufficient": bool(fdp is not None and fdp.flag == "INSUFFICIENT_INFORMATION"),
        "fdp_no_facts": bool(fdp is not None and fdp.flag == "NO_FDP_FACTS_IDENTIFIED"),
        "fdp_dependency_count": len(field(fdp, "dependency_map", []) or []),
        # Destination facts
        "destination_country": destination_code,
        "destination_embargoed": destination_embargoed,
        "destination_special_attention": destination_special,
        # End-use facts
        "declared_end_use": field(end_use, "input", None).declared_end_use if end_use is not None else None,
        "installation_location": field(end_use, "input", None).installation_location if end_use is not None else None,
        "industry": field(end_use, "input", None).industry if end_use is not None else None,
        "end_use_civil": field(end_use, "input", None).civil_use if end_use is not None else False,
        "end_use_military": field(end_use, "input", None).military_use if end_use is not None else False,
        "end_use_aerospace": field(end_use, "input", None).aerospace_use if end_use is not None else False,
        "end_use_semiconductor": field(end_use, "input", None).semiconductor_use if end_use is not None else False,
        "end_use_research": field(end_use, "input", None).research_use if end_use is not None else False,
        "end_use_unknown": field(end_use, "input", None).unknown_use if end_use is not None else False,
        "end_use_insufficient": False,
        "end_use_military_indicators": False,
        "end_use_inconsistent_business": False,
        "end_use_location_unclear": False,
        # Screening facts
        "screening_buyer_status": None,
        "screening_consignee_status": None,
        "screening_end_user_status": None,
        "screening_has_manual_verification": False,
        "screening_has_possible_match": False,
        "screening_worst_status": None,
        # Red flag facts (populated by risk/red flag services)
        "red_flag_count": 0,
        "red_flag_total_points": 0,
        "any_red_flags": False,
        "red_flag_ids": "",
        # Overall risk facts (populated by the risk engine)
        "risk_level": None,
        "risk_total": None,
    }

    if end_use is not None:
        flag_keys = {flag.key for flag in end_use.flags}
        context["end_use_insufficient"] = "insufficient_end_use_information" in flag_keys
        context["end_use_military_indicators"] = "military_related_indicators" in flag_keys
        context["end_use_inconsistent_business"] = "inconsistent_business_activity" in flag_keys
        context["end_use_location_unclear"] = "unclear_installation_location" in flag_keys

    if screening_obj is not None:
        statuses = [result.status for result in screening_obj.results if result.status]
        role_status = {
            "buyer": _screening_status_for_role(screening_obj, ("buyer",)),
            "consignee": _screening_status_for_role(screening_obj, ("consignee",)),
            "end_user": _screening_status_for_role(
                screening_obj, ("end user", "ultimate", "end-user", "user")
            ),
        }
        context.update(
            {
                "screening_buyer_status": role_status["buyer"],
                "screening_consignee_status": role_status["consignee"],
                "screening_end_user_status": role_status["end_user"],
                "screening_has_manual_verification": SCREENING_MANUAL_VERIFICATION in statuses,
                "screening_has_possible_match": SCREENING_POSSIBLE_MATCH in statuses,
                "screening_worst_status": (
                    SCREENING_MANUAL_VERIFICATION
                    if SCREENING_MANUAL_VERIFICATION in statuses
                    else SCREENING_POSSIBLE_MATCH
                    if SCREENING_POSSIBLE_MATCH in statuses
                    else "NO_APPARENT_MATCH"
                    if statuses
                    else None
                ),
            }
        )

    return context


def load_risk_config() -> dict[str, Any]:
    return load_json_file(rule_path("risk_rules.json"))


def run_risk_engine(
    context: dict[str, Any],
    red_flags: Any = None,
) -> tuple[RiskAssessment, dict[str, Any]]:
    """Score each configured risk category and return (assessment, enriched context)."""

    working_context = dict(context)
    if red_flags is None:
        red_flags = evaluate_red_flag_rules(working_context)
    working_context.update(
        {
            "red_flag_count": red_flags.rule_count,
            "red_flag_total_points": float(red_flags.total_points),
            "any_red_flags": bool(red_flags.findings),
            "red_flag_ids": ",".join(finding.rule_id for finding in red_flags.findings),
        }
    )

    config = load_risk_config()
    category_config = config["category_scores"]
    risk_level_config = config["risk_levels"]
    rule_map = config["rules"]

    categories: dict[str, RiskCategoryScore] = {}
    total = Decimal("0")
    for category_key in CATEGORY_ORDER:
        max_points = Decimal(str(category_config[category_key]["max"]))
        category_points = Decimal("0")
        findings: list[RiskFinding] = []
        for rule in rule_map.get(category_key, []):
            try:
                matched = evaluate_condition(str(rule.get("condition", "")), working_context)
            except Exception as exc:  # Surface broken user-edited rules without crashing scoring.
                matched = False
                findings.append(
                    RiskFinding(
                        rule_id=str(rule.get("rule_id", "ERROR")),
                        name="Rule configuration error",
                        points=Decimal("0"),
                        explanation=f"Rule could not be evaluated: {exc}",
                    )
                )
            if matched:
                points = Decimal(str(rule.get("points", 0)))
                findings.append(
                    RiskFinding(
                        rule_id=str(rule.get("rule_id", "")),
                        name=str(rule.get("name", "")),
                        points=points,
                        explanation=str(rule.get("explanation", "")),
                    )
                )
                category_points += points

        if category_points > max_points:
            category_points = max_points
        total += category_points
        explanation_lines = [f"{finding.name}: {finding.points} point(s) awarded. {finding.explanation}" for finding in findings]
        if not findings:
            explanation_lines = ["No contributing factors were identified from the recorded facts and rules."]
        categories[category_key] = RiskCategoryScore(
            key=category_key,
            label=CATEGORY_LABELS[category_key],
            max_points=max_points,
            points=category_points,
            findings=findings,
            explanation_lines=explanation_lines,
        )

    level = "NOT_RUN"
    level_label = "Not run"
    for band in risk_level_config:
        if int(band["min"]) <= total <= int(band["max"]):
            level = band["label"]
            level_label = band["label"]
            break

    total_cap = sum(Decimal(str(item["max"])) for item in category_config.values())
    assessment = RiskAssessment(
        categories=categories,
        total=total,
        max_total=total_cap,
        level=level,
        level_label=level_label,
        methodology=(
            "Points are assigned by the configurable JSON rules in app/rules/risk_rules.json, "
            "capped per category, and summed. Every awarded point is explained in the report. "
            "The score is a preliminary compliance risk indicator, not a legal conclusion."
        ),
    )
    working_context["risk_level"] = level
    working_context["risk_total"] = float(total)
    return assessment, working_context


def run_review_queue(
    working_context: dict[str, Any],
    risk: RiskAssessment | None = None,
) -> ReviewQueueDecision:
    """Route the review to a queue using ordered configurable JSON rules."""

    context = dict(working_context)
    if risk is not None:
        context["risk_level"] = risk.level
        context["risk_total"] = float(risk.total)
    payload = load_json_file(rule_path("review_queue_rules.json"))
    decisions = payload.get("decisions", {})
    for rule in payload.get("rules", []):
        try:
            matched = evaluate_condition(str(rule.get("condition", "true")), context)
        except Exception:
            matched = False
        if matched:
            decision_code = str(rule.get("decision", "AUTO_REVIEW_COMPLETE"))
            decision_meta = decisions.get(decision_code, {"label": decision_code, "detail": ""})
            return ReviewQueueDecision(
                decision=decision_code,
                decision_label=decision_meta.get("label", decision_code),
                matched_rule_id=str(rule.get("rule_id", "")),
                matched_rule_name=str(rule.get("name", "")),
                explanation=str(rule.get("explanation", "")) + " " + str(decision_meta.get("detail", "")),
                rationale=[str(rule.get("explanation", "")), str(decision_meta.get("detail", ""))],
            )
    return ReviewQueueDecision(
        decision="AUTO_REVIEW_COMPLETE",
        decision_label=decisions.get("AUTO_REVIEW_COMPLETE", {}).get("label", "AUTO REVIEW COMPLETE"),
        explanation=decisions.get("AUTO_REVIEW_COMPLETE", {}).get("detail", ""),
        rationale=[decisions.get("AUTO_REVIEW_COMPLETE", {}).get("detail", "")],
    )


def jurisdiction_requires_attention(status: str | None) -> bool:
    return status in {JURISDICTION_REVIEW_REQUIRED, JURISDICTION_INSUFFICIENT}


def jurisdiction_is_possible(status: str | None) -> bool:
    return status == JURISDICTION_POSSIBLE

