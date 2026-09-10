"""Configurable Red Flag Engine (Step 8)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.models.review import RedFlagFinding, RedFlagResult
from app.paths import rule_path
from app.rule_evaluator import evaluate_condition
from app.services.json_files import load_json_file


def load_red_flag_rules() -> list[dict[str, Any]]:
    payload = load_json_file(rule_path("red_flag_rules.json"))
    return list(payload.get("rules", []))


def evaluate_red_flag_rules(context: dict[str, Any]) -> RedFlagResult:
    """Evaluate all JSON red flag rules against a normalized fact context."""

    findings: list[RedFlagFinding] = []
    total = Decimal("0")
    for rule in load_red_flag_rules():
        rule_id = str(rule.get("rule_id", "UNKNOWN"))
        condition = str(rule.get("condition", ""))
        if evaluate_condition(condition, context):
            points = Decimal(str(rule.get("risk_points", 0)))
            total += points
            findings.append(
                RedFlagFinding(
                    rule_id=rule_id,
                    name=str(rule.get("name", rule_id)),
                    risk_points=points,
                    action=str(rule.get("action", "REVIEW")),
                    explanation=str(rule.get("explanation", "")),
                    condition=condition,
                )
            )
    findings.sort(key=lambda finding: finding.rule_id)
    return RedFlagResult(findings=findings, total_points=total, rule_count=len(findings))

