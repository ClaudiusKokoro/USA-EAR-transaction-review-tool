"""Run the EAR review benchmark against the real service pipeline.

Each case in ``benchmark/cases.json`` is pushed through exactly the same
services the Streamlit workbench uses (jurisdiction -> de minimis -> FDP ->
screening -> end use -> red flags -> risk -> queue) and the recorded output is
compared with the expectations written in the dataset.

Two classes of checks are performed:

* expectation checks - does the tool produce the outcome the case predicts?
* guardrail checks   - does the tool stay inside its legal design limits?

Usage:

    python benchmark/run_benchmark.py [--verbose] [--family screening]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BENCHMARK_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BENCHMARK_DIR / "results"

from app.models.party import (  # noqa: E402
    SCREENING_MANUAL_VERIFICATION,
    SCREENING_NO_APPARENT_MATCH,
    SCREENING_POSSIBLE_MATCH,
    PartyToScreen,
)
from app.models.product import ProductInformation  # noqa: E402
from app.models.review import (  # noqa: E402
    EndUseReviewInput,
    FDPReviewInput,
    JurisdictionQuestionSet,
)
from app.models.transaction import TransactionIntake, normalize_transaction_dict  # noqa: E402
from app.services import deminimis_service, enduse_service, fdp_service  # noqa: E402
from app.services import jurisdiction_service, redflag_service, risk_service  # noqa: E402
from app.services import screening_service  # noqa: E402

RISK_ORDER = ["LOW", "MODERATE", "ELEVATED", "HIGH", "CRITICAL"]
QUEUE_ORDER = [
    "AUTO_REVIEW_COMPLETE",
    "COMPLIANCE_REVIEW_REQUIRED",
    "LEGAL_REVIEW_REQUIRED",
    "EXTERNAL_COUNSEL_REVIEW_RECOMMENDED",
]
ALLOWED_SCREENING = {
    SCREENING_NO_APPARENT_MATCH,
    SCREENING_POSSIBLE_MATCH,
    SCREENING_MANUAL_VERIFICATION,
}
FORBIDDEN_PHRASES = [
    "no license is required",
    "does not require a license",
    "not require a license",
    "is legal",
    "are legal",
    "violates the ear",
    "you may export",
    "is authorized to export",
    "transaction is approved",
]


def collect_parties(case: dict) -> list[PartyToScreen]:
    """Mirror the party collection used by the Streamlit workbench."""

    step1 = case["step1_transaction"]
    step6 = case.get("step6_parties") or {}
    parties: list[PartyToScreen] = [
        PartyToScreen(name=step1["exporter_name"], role="Exporter", country=step1.get("exporter_country")),
        PartyToScreen(name=step1["buyer_name"], role="Buyer", country=step1.get("buyer_country")),
    ]
    if step1.get("consignee"):
        parties.append(PartyToScreen(name=step1["consignee"], role="Consignee", country=None))
    if step1.get("ultimate_end_user"):
        parties.append(
            PartyToScreen(
                name=step1["ultimate_end_user"],
                role="Ultimate end user",
                country=step1.get("ultimate_destination"),
            )
        )
    role_blocks = {
        "Parent company": step6.get("parent_companies") or [],
        "Subsidiary": step6.get("subsidiaries") or [],
        "Director": step6.get("directors") or [],
        "Beneficial owner": step6.get("beneficial_owners") or [],
    }
    for role, names in role_blocks.items():
        for name in names:
            if str(name).strip():
                parties.append(PartyToScreen(name=str(name).strip(), role=role, country=None))
    return parties


def run_case(case: dict, screening_csv: Path) -> dict:
    """Run one benchmark case through the real review pipeline."""

    transaction = TransactionIntake.model_validate(normalize_transaction_dict(case["step1_transaction"]))
    product = ProductInformation.model_validate(case["step2_product"])
    questions = JurisdictionQuestionSet.model_validate(case["step3_jurisdiction"])

    jurisdiction = jurisdiction_service.run_jurisdiction_review(questions)

    deminimis_input = case["step4_deminimis"]
    deminimis = deminimis_service.run_de_minimis(
        deminimis_input.get("components") or [],
        total_foreign_product_value=deminimis_input.get("total_foreign_product_value"),
    )

    fdp = fdp_service.run_fdp_review(FDPReviewInput.model_validate(case["step5_fdp"]))

    parties = collect_parties(case)
    screening_output = screening_service.screen_parties(parties, csv_paths=[screening_csv])

    end_use = enduse_service.run_end_use_review(EndUseReviewInput.model_validate(case["step7_end_use"]))

    context = risk_service.assemble_review_context(
        transaction=transaction,
        product=product,
        jurisdiction_questions=questions,
        jurisdiction=jurisdiction,
        deminimis=deminimis,
        fdp=fdp,
        parties=parties,
        screening_output=screening_output,
        end_use=end_use,
    )
    red_flags = redflag_service.evaluate_red_flag_rules(context)
    risk, enriched = risk_service.run_risk_engine(context, red_flags=red_flags)
    queue = risk_service.run_review_queue(enriched, risk=risk)

    texts: list[str] = [
        jurisdiction.summary,
        *jurisdiction.reasons,
        *jurisdiction.next_steps,
        risk.methodology,
        queue.explanation,
        *queue.rationale,
        *[finding.explanation for finding in red_flags.findings],
        *[flag.detail for flag in end_use.flags],
        *[str(note) for note in deminimis.warnings],
        *[str(note) for note in deminimis.notes],
        *[result.explanation for result in screening_output.results],
    ]

    return {
        "jurisdiction_status": jurisdiction.status,
        "jurisdiction_path": jurisdiction.path,
        "deminimis_status": deminimis.status,
        "deminimis_ratio": float(deminimis.ratio) if deminimis.ratio is not None else None,
        "deminimis_included_value": float(deminimis.controlled_us_content_value or 0),
        "fdp_flag": fdp.flag,
        "screening": {result.party.name: result.status for result in screening_output.results},
        "screening_scores": {
            result.party.name: float(result.best_score or 0) for result in screening_output.results
        },
        "end_use_flags": sorted(flag.key for flag in end_use.flags),
        "red_flag_ids": sorted(finding.rule_id for finding in red_flags.findings),
        "red_flag_points": float(red_flags.total_points),
        "risk_level": risk.level,
        "risk_total": float(risk.total),
        "risk_categories": {key: float(value.points) for key, value in risk.categories.items()},
        "queue_decision": queue.decision,
        "queue_rule": queue.matched_rule_id,
        "texts": [text for text in texts if text],
    }


def evaluate(case: dict, actual: dict) -> list[dict]:
    """Compare one case's actual output with its expectations."""

    expected = case.get("expected") or {}
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    if "jurisdiction_status" in expected:
        check(
            "jurisdiction_status",
            actual["jurisdiction_status"] == expected["jurisdiction_status"],
            f"expected {expected['jurisdiction_status']}, got {actual['jurisdiction_status']}",
        )

    if "deminimis_status" in expected:
        check(
            "deminimis_status",
            actual["deminimis_status"] == expected["deminimis_status"],
            f"expected {expected['deminimis_status']}, got {actual['deminimis_status']}",
        )

    if "deminimis_ratio" in expected:
        ratio = actual["deminimis_ratio"]
        ok = ratio is not None and abs(ratio - float(expected["deminimis_ratio"])) <= 0.0011
        check("deminimis_ratio", ok, f"expected {expected['deminimis_ratio']}, got {ratio}")

    if "fdp_flag" in expected:
        check(
            "fdp_flag",
            actual["fdp_flag"] == expected["fdp_flag"],
            f"expected {expected['fdp_flag']}, got {actual['fdp_flag']}",
        )

    for party_name, status in (expected.get("screening") or {}).items():
        actual_status = actual["screening"].get(party_name)
        score = actual["screening_scores"].get(party_name)
        check(
            f"screening:{party_name}",
            actual_status == status,
            f"expected {status}, got {actual_status} (best score {score:.3f})"
            if isinstance(score, float)
            else f"expected {status}, got {actual_status}",
        )

    if "end_use_flags_exact" in expected:
        expected_flags = sorted(expected["end_use_flags_exact"])
        check(
            "end_use_flags",
            actual["end_use_flags"] == expected_flags,
            f"expected {expected_flags}, got {actual['end_use_flags']}",
        )

    for rule_id in expected.get("red_flags_should_include", []):
        check(
            f"red_flag_present:{rule_id}",
            rule_id in actual["red_flag_ids"],
            f"{rule_id} missing (actual: {actual['red_flag_ids']})",
        )

    for rule_id in expected.get("red_flags_should_not_include", []):
        check(
            f"red_flag_absent:{rule_id}",
            rule_id not in actual["red_flag_ids"],
            f"{rule_id} should not fire (actual: {actual['red_flag_ids']})",
        )

    if "risk_level_exact" in expected:
        check(
            "risk_level_exact",
            actual["risk_level"] == expected["risk_level_exact"],
            f"expected {expected['risk_level_exact']}, got {actual['risk_level']} ({actual['risk_total']})",
        )

    if "risk_level_min" in expected:
        ok = RISK_ORDER.index(actual["risk_level"]) >= RISK_ORDER.index(expected["risk_level_min"])
        check(
            "risk_level_min",
            ok,
            f"expected at least {expected['risk_level_min']}, got {actual['risk_level']} ({actual['risk_total']})",
        )

    if "queue_decision" in expected:
        check(
            "queue_decision",
            actual["queue_decision"] == expected["queue_decision"],
            f"expected {expected['queue_decision']}, got {actual['queue_decision']} ({actual['queue_rule']})",
        )

    if "queue_decision_min" in expected:
        ok = QUEUE_ORDER.index(actual["queue_decision"]) >= QUEUE_ORDER.index(expected["queue_decision_min"])
        check(
            "queue_decision_min",
            ok,
            f"expected at least {expected['queue_decision_min']}, got {actual['queue_decision']}",
        )

    return checks


def guardrail_checks(actual: dict) -> list[dict]:
    checks: list[dict] = []
    bad_statuses = {name: status for name, status in actual["screening"].items() if status not in ALLOWED_SCREENING}
    checks.append(
        {
            "check": "guardrail:screening_status_enum",
            "ok": not bad_statuses,
            "detail": f"unexpected screening statuses: {bad_statuses}" if bad_statuses else "",
        }
    )
    restricted_labels = {
        name: status for name, status in actual["screening"].items() if "RESTRICT" in str(status).upper()
    }
    checks.append(
        {
            "check": "guardrail:no_restricted_party_label",
            "ok": not restricted_labels,
            "detail": f"restricted-party style labels found: {restricted_labels}" if restricted_labels else "",
        }
    )
    hits: list[str] = []
    for text in actual["texts"]:
        lowered = str(text).lower()
        for phrase in FORBIDDEN_PHRASES:
            if phrase in lowered:
                hits.append(f"'{phrase}' in: {str(text)[:120]}")
    checks.append(
        {
            "check": "guardrail:no_legal_conclusion",
            "ok": not hits,
            "detail": "; ".join(hits[:3]),
        }
    )
    return checks


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the EAR review benchmark.")
    parser.add_argument("--family", help="Only run cases from this family")
    parser.add_argument("--case", help="Only run a single case_id")
    parser.add_argument("--verbose", action="store_true", help="Print every check")
    parser.add_argument(
        "--allow-failures",
        action="store_true",
        help="Exit with code 0 even when checks fail (useful for exploratory runs)",
    )
    args = parser.parse_args()

    dataset = json.loads((BENCHMARK_DIR / "cases.json").read_text(encoding="utf-8"))
    screening_csv = BENCHMARK_DIR / "screening_list.csv"
    cases = dataset["cases"]
    if args.family:
        cases = [case for case in cases if case["family"] == args.family]
    if args.case:
        cases = [case for case in cases if case["case_id"] == args.case]
    if not cases:
        raise SystemExit("No cases matched the filter.")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "raw").mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    failures: list[dict] = []
    family_stats: dict[str, Counter] = {}
    observations: list[str] = []
    case_known_issues: list[str] = []
    near_misses: list[tuple[float, str, str]] = []
    started = time.perf_counter()

    for case in cases:
        case_started = time.perf_counter()
        actual = run_case(case, screening_csv)
        elapsed_ms = (time.perf_counter() - case_started) * 1000
        checks = evaluate(case, actual) + guardrail_checks(actual)
        failed = [item for item in checks if not item["ok"]]
        passed = [item for item in checks if item["ok"]]

        stats = family_stats.setdefault(case["family"], Counter())
        stats["cases"] += 1
        stats["checks_passed"] += len(passed)
        stats["checks_total"] += len(checks)
        if not failed:
            stats["cases_passed"] += 1

        rows.append(
            {
                "case_id": case["case_id"],
                "family": case["family"],
                "title": case["title"],
                "checks_passed": len(passed),
                "checks_total": len(checks),
                "status": "PASS" if not failed else "FAIL",
                "jurisdiction": actual["jurisdiction_status"],
                "deminimis": actual["deminimis_status"],
                "fdp": actual["fdp_flag"],
                "risk_level": actual["risk_level"],
                "risk_total": actual["risk_total"],
                "queue": actual["queue_decision"],
                "red_flags": ",".join(actual["red_flag_ids"]),
                "failing_checks": " | ".join(item["check"] for item in failed),
                "elapsed_ms": round(elapsed_ms, 1),
            }
        )

        for item in failed:
            failures.append(
                {
                    "case_id": case["case_id"],
                    "family": case["family"],
                    "check": item["check"],
                    "detail": item["detail"],
                }
            )

        if args.verbose or failed:
            print(f"\n[{case['case_id']}] {case['title']}  ({case['family']})")
            print(
                f"  jurisdiction={actual['jurisdiction_status']} | deminimis={actual['deminimis_status']}"
                f" | fdp={actual['fdp_flag']} | risk={actual['risk_level']}({actual['risk_total']})"
                f" | queue={actual['queue_decision']}"
            )
            print(f"  red flags: {actual['red_flag_ids'] or 'none'}")
            for item in checks:
                if args.verbose or not item["ok"]:
                    print(f"    {'PASS' if item['ok'] else 'FAIL'}  {item['check']}  {item['detail']}")

        if actual["screening_scores"]:
            fuzzy = {
                name: round(score, 3)
                for name, score in actual["screening_scores"].items()
                if 0.65 <= score < 0.96
            }
            if fuzzy:
                observations.append(f"{case['case_id']}: fuzzy similarity band -> {fuzzy}")
            strong = {name: round(score, 3) for name, score in actual["screening_scores"].items() if score >= 0.96}
            if strong:
                observations.append(f"{case['case_id']}: manual-verification band -> {strong}")
            for name, score in actual["screening_scores"].items():
                if score < 0.65:
                    near_misses.append((score, case["case_id"], name))

        (RESULTS_DIR / "raw" / f"{case['case_id']}.json").write_text(
            json.dumps({"case": case, "actual": actual}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        for note in case.get("known_issues") or []:
            case_known_issues.append(f"{case['case_id']}: {note}")

    total_checks = sum(row["checks_total"] for row in rows)
    passed_checks = sum(row["checks_passed"] for row in rows)
    fully_passed = sum(1 for row in rows if row["status"] == "PASS")
    elapsed = time.perf_counter() - started

    with (RESULTS_DIR / "case_results.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    risk_distribution = Counter(row["risk_level"] for row in rows)
    queue_distribution = Counter(row["queue"] for row in rows)

    lines: list[str] = []
    lines.append(f"# EAR benchmark results - {dataset['metadata']['dataset_name']}")
    lines.append("")
    lines.append(f"- Run at: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    lines.append(f"- Cases run: {len(rows)}")
    lines.append(f"- Cases fully passing: {fully_passed} / {len(rows)}")
    lines.append(f"- Individual checks: {passed_checks} / {total_checks} passed")
    lines.append(f"- Wall clock: {elapsed:.2f}s ({elapsed / len(rows) * 1000:.0f} ms per case)")
    lines.append("")
    lines.append("## Per family")
    lines.append("")
    lines.append("| Family | Cases | Cases passing | Checks passed | Checks total |")
    lines.append("| --- | --- | --- | --- | --- |")
    for family in sorted(family_stats):
        stats = family_stats[family]
        lines.append(
            f"| {family} | {stats['cases']} | {stats['cases_passed']} | "
            f"{stats['checks_passed']} | {stats['checks_total']} |"
        )
    lines.append("")
    lines.append("## Outcome distribution")
    lines.append("")
    lines.append("| Risk level | Cases |")
    lines.append("| --- | --- |")
    for level in RISK_ORDER:
        if risk_distribution.get(level):
            lines.append(f"| {level} | {risk_distribution[level]} |")
    lines.append("")
    lines.append("| Queue decision | Cases |")
    lines.append("| --- | --- |")
    for decision in QUEUE_ORDER:
        if queue_distribution.get(decision):
            lines.append(f"| {decision} | {queue_distribution[decision]} |")
    lines.append("")
    lines.append("## Failures")
    lines.append("")
    if failures:
        lines.append("| Case | Family | Check | Detail |")
        lines.append("| --- | --- | --- | --- |")
        for item in failures:
            lines.append(
                f"| {item['case_id']} | {item['family']} | {item['check']} | {item['detail']} |"
            )
    else:
        lines.append("No failures.")
    lines.append("")
    lines.append("## Screening calibration observations")
    lines.append("")
    if observations:
        for item in observations:
            lines.append(f"- {item}")
    else:
        lines.append("- No fuzzy or manual-verification screening scores were produced.")
    lines.append("")
    lines.append("## Closest non-matches (false-positive headroom)")
    lines.append("")
    if near_misses:
        lines.append("| Score | Case | Party name |")
        lines.append("| --- | --- | --- |")
        for score, case_id, name in sorted(near_misses, reverse=True)[:8]:
            lines.append(f"| {score:.3f} | {case_id} | {name} |")
        lines.append("")
        lines.append("Scores below 0.65 produce NO_APPARENT_MATCH; these are the highest such scores.")
    else:
        lines.append("- No non-matching party scored above zero.")
    lines.append("")
    lines.append("## Guardrail checks")
    lines.append("")
    guardrail_failures = [item for item in failures if item["check"].startswith("guardrail:")]
    lines.append(f"- Guardrail failures across the whole run: {len(guardrail_failures)}")
    lines.append(
        "- Every case is checked for: screening status enum, no restricted-party label, "
        "and no legal-conclusion wording in any generated text."
    )
    lines.append("")
    lines.append("## Known issues and calibration notes")
    lines.append("")
    dataset_issues = dataset["metadata"].get("known_issues") or []
    if dataset_issues:
        lines.append("Dataset-level findings:")
        lines.append("")
        for item in dataset_issues:
            lines.append(f"- {item}")
        lines.append("")
    if case_known_issues:
        lines.append("Case-level findings:")
        lines.append("")
        for item in case_known_issues:
            lines.append(f"- {item}")
    else:
        lines.append("- None recorded.")
    lines.append("")
    (RESULTS_DIR / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("")
    print(f"cases: {len(rows)} | fully passing: {fully_passed} | checks: {passed_checks}/{total_checks}")
    print(f"results written to {RESULTS_DIR}")
    if failures:
        print(f"failures: {len(failures)} (see results/summary.md)")
    if failures and not args.allow_failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
