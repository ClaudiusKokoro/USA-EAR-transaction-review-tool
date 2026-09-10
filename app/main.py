"""EAR Transaction Review Tool - Streamlit application entry point.

Run from the project root:

    streamlit run app/main.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.db import delete_review, list_reviews, load_review, save_review  # noqa: E402
from app.models.party import PartyScreeningResult, PartyToScreen  # noqa: E402
from app.models.product import EAR_STATUS_OPTIONS, PRODUCT_CATEGORIES, ProductInformation  # noqa: E402
from app.models.review import (  # noqa: E402
    DE_MINIMIS_COMPUTED,
    EndUseReviewInput,
    FDPReviewInput,
    JurisdictionQuestionSet,
    ReviewBundle,
)
from app.models.transaction import TransactionIntake, normalize_transaction_dict  # noqa: E402
from app.services import deminimis_service, enduse_service, fdp_service  # noqa: E402
from app.services import ear_list_sync_service  # noqa: E402
from app.services import jurisdiction_service, redflag_service, report_service  # noqa: E402
from app.services import risk_service, screening_service  # noqa: E402

st.set_page_config(
    page_title="EAR Transaction Review Tool",
    page_icon=":shield:",
    layout="wide",
)

STAGES = {
    1: "Step 1 - Transaction Intake",
    2: "Step 2 - Product Information",
    3: "Step 3 - EAR Jurisdiction Review",
    4: "Step 4 - De Minimis Calculator",
    5: "Step 5 - FDP Review",
    6: "Step 6 - Party Screening",
    7: "Step 7 - End Use Review",
    8: "Step 8 - Red Flag Engine",
    9: "Step 9 - Risk Engine",
    10: "Step 10 - Legal Review Queue",
    11: "Step 11 - Report Generator",
}


MAIN_VIEW_REVIEW = "Review workspace"
MAIN_VIEW_LISTS = "List & Data Center"

EAR_SOURCE_LABELS = {
    "EL": "Entity List (EL)",
    "DPL": "Denied Persons List (DPL)",
    "UVL": "Unverified List (UVL)",
    "MEU": "Military End User List (MEU)",
    "": "Other U.S. lists",
}


def effective_screening_csv_paths() -> list[Path]:
    """Bundled example plus the applied federal snapshot (when present)."""

    paths = [screening_service.DEFAULT_RESTRICTED_PARTIES_FILE]
    synced = ear_list_sync_service.synced_list_path()
    if synced:
        paths.append(synced)
    return paths


STATUS_LABELS = {
    "POSSIBLE_EAR_JURISDICTION": "POSSIBLE EAR JURISDICTION",
    "POSSIBLE EAR JURISDICTION": "POSSIBLE EAR JURISDICTION",
    "JURISDICTION_REVIEW_REQUIRED": "JURISDICTION REVIEW REQUIRED",
    "JURISDICTION REVIEW REQUIRED": "JURISDICTION REVIEW REQUIRED",
    "INSUFFICIENT_INFORMATION": "INSUFFICIENT INFORMATION",
    "INSUFFICIENT INFORMATION": "INSUFFICIENT INFORMATION",
    "NO_FDP_FACTS_IDENTIFIED": "NO FDP FACTS IDENTIFIED",
    "NO FDP FACTS IDENTIFIED": "NO FDP FACTS IDENTIFIED",
    "POTENTIAL_FDP_ISSUE": "POTENTIAL FDP ISSUE",
    "POTENTIAL FDP ISSUE": "POTENTIAL FDP ISSUE",
    "NO_APPARENT_MATCH": "NO APPARENT MATCH",
    "NO APPARENT MATCH": "NO APPARENT MATCH",
    "POSSIBLE_MATCH": "POSSIBLE MATCH",
    "POSSIBLE MATCH": "POSSIBLE MATCH",
    "MANUAL_VERIFICATION_REQUIRED": "MANUAL VERIFICATION REQUIRED",
    "MANUAL VERIFICATION REQUIRED": "MANUAL VERIFICATION REQUIRED",
    "LOW": "LOW",
    "MODERATE": "MODERATE",
    "ELEVATED": "ELEVATED",
    "HIGH": "HIGH",
    "CRITICAL": "CRITICAL",
    "AUTO_REVIEW_COMPLETE": "AUTO REVIEW COMPLETE",
    "AUTO REVIEW COMPLETE": "AUTO REVIEW COMPLETE",
    "COMPLIANCE_REVIEW_REQUIRED": "COMPLIANCE REVIEW REQUIRED",
    "COMPLIANCE REVIEW REQUIRED": "COMPLIANCE REVIEW REQUIRED",
    "LEGAL_REVIEW_REQUIRED": "LEGAL REVIEW REQUIRED",
    "LEGAL REVIEW REQUIRED": "LEGAL REVIEW REQUIRED",
    "EXTERNAL_COUNSEL_REVIEW_RECOMMENDED": "EXTERNAL COUNSEL REVIEW RECOMMENDED",
    "EXTERNAL COUNSEL REVIEW RECOMMENDED": "EXTERNAL COUNSEL REVIEW RECOMMENDED",
    "COMPUTED": "COMPUTED",
    "NO_CONTROLLED_US_CONTENT": "NO CONTROLLED U.S. CONTENT",
    "MISSING_VALUE": "MISSING VALUE",
    "MISSING_TOTAL": "MISSING TOTAL",
    "MISSING_INPUT": "MISSING INPUT",
}


def status_text(value: str | None) -> str:
    """Map service statuses/labels to Chinese-first bilingual text."""

    if not value:
        return ""
    key = value.strip().replace("_", " ").upper() if " " in value or "_" in value else value.strip().upper()
    for candidate in (value.strip(), value.strip().replace("_", " "), key):
        if candidate in STATUS_LABELS:
            return STATUS_LABELS[candidate]
    return value


def reset_state() -> None:
    st.session_state.pop("step_data", None)
    st.session_state.pop("screening_csv_bytes", None)
    st.session_state.pop("current_step", None)
    st.session_state.step_data = {}
    st.session_state.current_step = 1
    st.session_state.pending_step = 1


def go_to_step(step: int) -> None:
    """Queue a wizard transition; the sidebar radio is updated before it renders."""

    st.session_state.current_step = step
    st.session_state.pending_step = step


def process_pending_step() -> None:
    """Apply a pending wizard transition before any widget is instantiated."""

    if st.session_state.get("pending_step") is None:
        return
    step = int(st.session_state.pending_step)
    st.session_state.current_step = step
    st.session_state["stage_radio"] = f"{step}. {STAGES[step]}"
    st.session_state.pending_step = None


if "step_data" not in st.session_state:
    st.session_state.step_data = {}
if "current_step" not in st.session_state:
    st.session_state.current_step = 1
if "screening_csv_bytes" not in st.session_state:
    st.session_state.screening_csv_bytes = None
if "screening_csv_name" not in st.session_state:
    st.session_state.screening_csv_name = ""
if "pending_step" not in st.session_state:
    st.session_state.pending_step = None


def store(step: int, data: dict) -> None:
    st.session_state.step_data[str(step)] = data


def current_data(step: int) -> dict:
    return st.session_state.step_data.get(str(step), {})


def nullable_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def money_to_str(value) -> str:
    if value is None:
        return ""
    return str(value)


def build_transaction(data: dict | None) -> TransactionIntake:
    return TransactionIntake.model_validate(normalize_transaction_dict(data or {}))


def build_product(data: dict | None) -> ProductInformation:
    return ProductInformation.model_validate(data or {})


def build_jurisdiction_questions(data: dict | None) -> JurisdictionQuestionSet:
    raw = dict(data or {})
    clean = {key: value for key, value in raw.items() if value is not None}
    return JurisdictionQuestionSet.model_validate(clean)


def collect_parties() -> list[PartyToScreen]:
    """Assemble the parties to screen from Steps 1 and 6."""

    parties: list[PartyToScreen] = []
    step1 = current_data(1)
    if step1.get("exporter_name"):
        parties.append(
            PartyToScreen(
                name=str(step1["exporter_name"]),
                role="Exporter",
                country=nullable_text(step1.get("exporter_country")),
            )
        )
    if step1.get("buyer_name"):
        parties.append(
            PartyToScreen(
                name=str(step1["buyer_name"]),
                role="Buyer",
                country=nullable_text(step1.get("buyer_country")),
            )
        )
    if step1.get("consignee"):
        parties.append(
            PartyToScreen(name=str(step1["consignee"]), role="Consignee", country=None)
        )
    if step1.get("ultimate_end_user"):
        parties.append(
            PartyToScreen(
                name=str(step1["ultimate_end_user"]),
                role="Ultimate end user",
                country=nullable_text(step1.get("ultimate_destination")),
            )
        )
    step6 = current_data(6)
    role_blocks = {
        "Parent company": step6.get("parent_companies", ""),
        "Subsidiary": step6.get("subsidiaries", ""),
        "Director": step6.get("directors", ""),
        "Beneficial owner": step6.get("beneficial_owners", ""),
    }
    for role, block in role_blocks.items():
        for line in str(block).splitlines():
            name = line.strip()
            if name:
                parties.append(PartyToScreen(name=name, role=role, country=None))
    return parties


ROLE_LABELS = {
    "exporter": "Exporter",
    "buyer": "Buyer",
    "consignee": "Consignee",
    "ultimate end user": "Ultimate end user",
    "parent company": "Parent company",
    "subsidiary": "Subsidiary",
    "director": "Director",
    "beneficial owner": "Beneficial owner",
}


def party_role_label(role: str) -> str:
    lowered = role.casefold()
    for key, label in ROLE_LABELS.items():
        if key in lowered:
            return label
    return role


END_USE_LABELS = {
    "insufficient end-use information": "Insufficient end-use information",
    "inconsistent business activity": "Inconsistent business activity",
    "military-related indicators": "Military-related indicators",
    "unclear installation location": "Unclear installation location",
}


def flag_label(label: str) -> str:
    for english, display in END_USE_LABELS.items():
        if label.casefold() == english or english in label.casefold():
            return display
    return label


RISK_CATEGORY_LABELS = {
    "EAR Jurisdiction Risk": "EAR Jurisdiction Risk",
    "Product Risk": "Product Risk",
    "Destination Risk": "Destination Risk",
    "End User Risk": "End User Risk",
    "End Use Risk": "End Use Risk",
    "Red Flags": "Red Flags",
}


def risk_category_label(label: str) -> str:
    for english, display in RISK_CATEGORY_LABELS.items():
        if label == english or english in label:
            return display
    return label


def build_de_minimis_components(raw_rows: list[dict] | None) -> list[dict]:
    cleaned: list[dict] = []
    for row in raw_rows or []:
        component_name = str(row.get("component_name") or "").strip()
        if not component_name:
            continue
        value = row.get("component_value")
        try:
            decimal_value = None if value in (None, "", "nan") else Decimal(str(value))
        except Exception:
            decimal_value = None
        cleaned.append(
            {
                "component_name": component_name,
                "origin": nullable_text(row.get("origin")),
                "eccn": nullable_text(row.get("eccn")),
                "controlled_status": str(row.get("controlled_status") or "Unknown"),
                "component_value": decimal_value,
            }
        )
    return cleaned


def run_all_reviews(legal_notes: str = "") -> ReviewBundle:
    """Run the complete review pipeline from the current form data."""

    step1 = current_data(1)
    step2 = current_data(2)
    transaction = build_transaction(step1)
    product = build_product(step2)

    jurisdiction_questions = build_jurisdiction_questions(current_data(3))
    jurisdiction = jurisdiction_service.run_jurisdiction_review(jurisdiction_questions)

    de_minimis_raw = current_data(4)
    deminimis_total = de_minimis_raw.get("total_foreign_product_value")
    if deminimis_total in (None, ""):
        deminimis_total = transaction.transaction_value
    components = build_de_minimis_components(de_minimis_raw.get("components") or [])
    deminimis = deminimis_service.run_de_minimis(components, total_foreign_product_value=deminimis_total)

    fdp = fdp_service.run_fdp_review(FDPReviewInput.model_validate(current_data(5) or {}))

    parties = collect_parties()
    uploaded_bytes = st.session_state.screening_csv_bytes
    temp_csv_path: Path | None = None
    csv_paths = effective_screening_csv_paths()
    if uploaded_bytes:
        handle = tempfile.NamedTemporaryFile(
            mode="w+b",
            suffix=".csv",
            prefix="ear_screening_",
            delete=False,
            encoding=None,
        )
        handle.write(uploaded_bytes)
        handle.close()
        temp_csv_path = Path(handle.name)
        csv_paths.append(temp_csv_path)
    screening_output = screening_service.screen_parties(parties, csv_paths=csv_paths)
    if temp_csv_path:
        try:
            temp_csv_path.unlink(missing_ok=True)
        except Exception:
            pass

    end_use = enduse_service.run_end_use_review(
        EndUseReviewInput.model_validate(current_data(7) or {})
    )

    context = risk_service.assemble_review_context(
        transaction=transaction,
        product=product,
        jurisdiction_questions=jurisdiction_questions,
        jurisdiction=jurisdiction,
        deminimis=deminimis,
        fdp=fdp,
        parties=parties,
        screening_output=screening_output,
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
        screening=screening_output.results,
        end_use=end_use,
        red_flags=red_flags,
        risk=risk,
        queue=queue,
        legal_review_notes=legal_notes,
    )


def persist_review(bundle: ReviewBundle) -> int:
    transaction = bundle.transaction
    payload = {
        "step_data": st.session_state.step_data,
        "summary": {
            "transaction_name": transaction.transaction_name if transaction else "",
            "exporter_name": transaction.exporter_name if transaction else "",
            "buyer_name": transaction.buyer_name if transaction else "",
            "buyer_country": transaction.buyer_country if transaction else "",
            "risk_level": bundle.risk.level if bundle.risk else "NOT_RUN",
            "total_risk": str(bundle.risk.total) if bundle.risk else None,
            "queue_decision": bundle.queue.decision_label if bundle.queue else "",
            "generated_at": bundle.generated_at.isoformat(),
        },
        "transaction": transaction.model_dump(mode="json") if transaction else {},
        "legal_review_notes": bundle.legal_review_notes,
    }
    return save_review(payload)


def sidebar() -> None:
    st.sidebar.title("EAR Transaction Review Tool")
    st.sidebar.caption(
        "Preliminary compliance risk assessment for EAR transaction review. Not legal advice."
    )
    view_kwargs: dict = {"key": "main_view_radio"}
    if "main_view_radio" not in st.session_state:
        view_kwargs["index"] = 0
    selected_view = st.sidebar.radio(
        "Main view",
        [MAIN_VIEW_REVIEW, MAIN_VIEW_LISTS],
        **view_kwargs,
    )
    st.session_state.main_view = selected_view

    if selected_view == MAIN_VIEW_LISTS:
        st.sidebar.caption(
            "Sync official U.S. screening lists (CSL) and manage the local snapshot here."
        )
        return

    if st.sidebar.button("Start a new review", width="stretch"):
        reset_state()
        st.rerun()

    stage_options = [f"{key}. {label}" for key, label in STAGES.items()]
    current_index = st.session_state.current_step - 1
    radio_kwargs: dict = {"key": "stage_radio"}
    if "stage_radio" not in st.session_state:
        radio_kwargs["index"] = min(max(current_index, 0), len(stage_options) - 1)
    selected = st.sidebar.radio("Workflow stage", stage_options, **radio_kwargs)
    st.session_state.current_step = int(selected.split(".")[0])

    st.sidebar.markdown("---")
    st.sidebar.subheader("Saved reviews (local SQLite)")
    try:
        reviews = list_reviews()
        if not reviews:
            st.sidebar.caption("No saved reviews yet. Complete Step 11 to save one.")
        for review in reviews:
            label = f"#{review['id']} - {review['transaction_name']} ({review['risk_level']})"
            with st.sidebar.expander(label):
                st.caption(
                    f"{review['exporter_name']} -> {review['buyer_name']}\n"
                    f"{'Created'}: {review['created_at']}"
                )
                if st.button("Load", key=f"load_{review['id']}"):
                    payload = load_review(int(review["id"]))
                    st.session_state.step_data = dict(payload.get("step_data") or {})
                    st.session_state.screening_csv_bytes = None
                    st.session_state.main_view_radio = MAIN_VIEW_REVIEW
                    st.session_state.main_view = MAIN_VIEW_REVIEW
                    go_to_step(11)
                    st.rerun()
                if st.button("Delete", key=f"delete_{review['id']}"):
                    delete_review(int(review["id"]))
                    st.rerun()
    except Exception as exc:  # pragma: no cover - SQLite failures should not block the UI.
        st.sidebar.error(f"{'Review history unavailable'}: {exc}")


def status_box(label: str, text: str) -> None:
    st.markdown(f"**{label}:** {text}")


def render_step1() -> None:
    st.header("Step 1 - Transaction Intake")
    defaults = current_data(1)
    with st.form("step1_form", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            transaction_name = st.text_input(
                "Transaction name", value=str(defaults.get("transaction_name", ""))
            )
            exporter_name = st.text_input("Exporter name", value=str(defaults.get("exporter_name", "")))
            exporter_country = st.text_input(
                "Exporter country (ISO code)", value=str(defaults.get("exporter_country", "")),
                max_chars=2,
            ).upper()
            buyer_name = st.text_input("Buyer name", value=str(defaults.get("buyer_name", "")))
            buyer_country = st.text_input(
                "Buyer country (ISO code)", value=str(defaults.get("buyer_country", "")),
                max_chars=2,
            ).upper()
        with col2:
            consignee = st.text_input("Consignee", value=str(defaults.get("consignee", "") or ""))
            ultimate_end_user = st.text_input(
                "Ultimate end user", value=str(defaults.get("ultimate_end_user", "") or "")
            )
            ultimate_destination = st.text_input(
                "Ultimate destination (ISO code)",
                value=str(defaults.get("ultimate_destination", "") or ""),
                max_chars=2,
            ).upper()
            transaction_value = st.number_input(
                "Transaction value",
                min_value=0.0,
                step=1000.0,
                value=float(defaults.get("transaction_value") or 0.0),
                format="%.2f",
            )
            currency = st.text_input(
                "Currency", value=str(defaults.get("currency", "USD")), max_chars=3
            ).upper()
        shipment_date = st.date_input(
            "Shipment date",
            value=date.fromisoformat(defaults["shipment_date"]) if defaults.get("shipment_date") else date.today(),
        )
        notes = st.text_area("Notes", value=str(defaults.get("notes", "") or ""))
        submitted = st.form_submit_button("Save and continue to Step 2", type="primary")

    if submitted:
        data = {
            "transaction_name": transaction_name.strip(),
            "exporter_name": exporter_name.strip(),
            "exporter_country": exporter_country,
            "buyer_name": buyer_name.strip(),
            "buyer_country": buyer_country,
            "consignee": nullable_text(consignee),
            "ultimate_end_user": nullable_text(ultimate_end_user),
            "ultimate_destination": nullable_text(ultimate_destination),
            "transaction_value": float(transaction_value) if transaction_value else None,
            "currency": currency or "USD",
            "shipment_date": shipment_date.isoformat(),
            "notes": notes,
        }
        try:
            build_transaction(data)
        except ValidationError as exc:
            st.error(
                "Please complete the required transaction fields: "
                + "; ".join(error["loc"][0] for error in exc.errors())
            )
            return
        store(1, data)
        go_to_step(2)
        st.success("Transaction intake saved.")
        st.rerun()


def render_step2() -> None:
    st.header("Step 2 - Product Information")
    defaults = current_data(2)
    with st.form("step2_form"):
        col1, col2 = st.columns(2)
        with col1:
            product_name = st.text_input("Product name", value=str(defaults.get("product_name", "")))
            model = st.text_input("Model", value=str(defaults.get("model", "") or ""))
            category = st.selectbox(
                "Category",
                PRODUCT_CATEGORIES,
                index=PRODUCT_CATEGORIES.index(defaults["category"])
                if defaults.get("category") in PRODUCT_CATEGORIES
                else 0,
            )
            manufacturer = st.text_input("Manufacturer", value=str(defaults.get("manufacturer", "") or ""))
            country_of_manufacture = st.text_input(
                "Country of manufacture",
                value=str(defaults.get("country_of_manufacture", "") or ""),
            )
        with col2:
            existing_eccn = st.text_input(
                "Existing ECCN (if any)", value=str(defaults.get("existing_eccn", "") or "")
            ).upper()
            ear_status = st.selectbox(
                "Existing EAR status",
                EAR_STATUS_OPTIONS,
                index=EAR_STATUS_OPTIONS.index(defaults["existing_ear_status"])
                if defaults.get("existing_ear_status") in EAR_STATUS_OPTIONS
                else 0,
            )
            product_value = st.number_input(
                "Product value",
                min_value=0.0,
                step=1000.0,
                value=float(defaults.get("product_value") or 0.0),
                format="%.2f",
            )
        product_description = st.text_area(
            "Product description",
            value=str(defaults.get("product_description", "") or ""),
            height=120,
        )
        submitted = st.form_submit_button("Save and continue to Step 3", type="primary")

    if submitted:
        data = {
            "product_name": product_name.strip(),
            "model": nullable_text(model),
            "product_description": product_description.strip(),
            "category": category,
            "manufacturer": nullable_text(manufacturer),
            "country_of_manufacture": nullable_text(country_of_manufacture),
            "existing_eccn": nullable_text(existing_eccn),
            "existing_ear_status": ear_status,
            "product_value": float(product_value) if product_value else None,
        }
        try:
            build_product(data)
        except ValidationError as exc:
            st.error(
                "Please complete the required product fields: "
                + "; ".join(error["loc"][0] for error in exc.errors())
            )
            return
        store(2, data)
        go_to_step(3)
        st.success("Product information saved.")
        st.rerun()


QUESTION_HELP = {
    "is_us_origin": "Is the item U.S.-origin?",
    "has_us_origin_content": "Does the item contain U.S.-origin content?",
    "us_content_value_known": "Is the value of U.S.-origin controlled content known?",
    "total_foreign_value_known": "Is the total value of the foreign-produced item known?",
    "us_software_used_in_production": "Was U.S.-origin software used in production?",
    "us_technology_used_in_production": "Was U.S.-origin technology used in production?",
    "production_chain_known": "Is the production chain known?",
}

CHOICE_LABELS = [
    "Yes",
    "No",
    "Unanswered",
]


def tri_state_widget(key: str, defaults: dict) -> bool | None:
    current = defaults.get(key)
    index = 0 if current is True else 1 if current is False else 2
    answer = st.radio(
        QUESTION_HELP[key],
        CHOICE_LABELS,
        index=index,
        horizontal=True,
        key=f"q_{key}",
    )
    if answer == CHOICE_LABELS[0]:
        return True
    if answer == CHOICE_LABELS[1]:
        return False
    return None


def render_step3() -> None:
    st.header("Step 3 - EAR Jurisdiction Review")
    st.caption(
        "Answers feed a conservative preliminary decision tree. The tool only reports "
        "POSSIBLE EAR JURISDICTION, JURISDICTION REVIEW REQUIRED, or INSUFFICIENT INFORMATION - "
        "never a definitive legal conclusion."
    )
    defaults = current_data(3)
    answers = {
        key: tri_state_widget(key, defaults)
        for key in QUESTION_HELP
    }
    additional_notes = st.text_area(
        "Additional jurisdiction notes",
        value=str(defaults.get("additional_notes", "") or ""),
    )
    run_button = st.button("Run jurisdiction review and save", type="primary")
    if run_button:
        data = {**answers, "additional_notes": additional_notes}
        store(3, data)
        questions = build_jurisdiction_questions(data)
        result = jurisdiction_service.run_jurisdiction_review(questions)
        go_to_step(4)
        st.session_state.step3_result = result
        st.rerun()

    if "step3_result" in st.session_state:
        result = st.session_state.step3_result
        st.markdown("### Preliminary jurisdiction state")
        status_box("Result", status_text(result.status_label))
        st.write(result.summary)
        st.write("Reasons:")
        for reason in result.reasons:
            st.markdown(f"- {reason}")
        if result.missing_information:
            st.warning("Missing information: " + "; ".join(result.missing_information) + ".")
        st.caption(
            "This is a preliminary review state, not a legal determination that the EAR applies or does not apply."
        )


def render_step4() -> None:
    st.header("Step 4 - De Minimis Calculator")
    st.caption(
        "Add each U.S.-origin controlled component in the foreign-produced item. "
        "The tool calculates controlled U.S. content value / total foreign product value and warns "
        "that the applicable legal threshold requires review."
    )
    defaults = current_data(4)
    components = defaults.get("components") or []
    if components:
        component_rows = pd.DataFrame(components)
    else:
        component_rows = pd.DataFrame(
            [
                {
                    "component_name": "",
                    "origin": "",
                    "eccn": "",
                    "controlled_status": "Unknown",
                    "component_value": 0.0,
                }
            ]
        )
    edited = st.data_editor(
        component_rows,
        num_rows="dynamic",
        width="stretch",
        column_config={
            "component_name": st.column_config.TextColumn("Component name", required=True),
            "origin": st.column_config.TextColumn("Origin", help="e.g." + " US / China"),
            "eccn": st.column_config.TextColumn("ECCN"),
            "controlled_status": st.column_config.SelectboxColumn(
                "Controlled status",
                options=[
                    "Yes - controlled",
                    "No - EAR99",
                    "Unknown",
                ],
            ),
            "component_value": st.column_config.NumberColumn("Value", min_value=0.0, format="%.2f"),
        },
        key="deminimis_editor",
    )
    total_value = st.number_input(
        "Total value of the foreign-produced item",
        min_value=0.0,
        step=1000.0,
        value=float(defaults.get("total_foreign_product_value") or 0.0),
        format="%.2f",
    )
    if st.button("Run de minimis calculation", type="primary"):
        rows = edited.to_dict(orient="records") if edited is not None else []
        cleaned_rows = build_de_minimis_components(rows)
        store(4, {"components": cleaned_rows, "total_foreign_product_value": float(total_value) or None})
        result = deminimis_service.run_de_minimis(cleaned_rows, total_foreign_product_value=total_value or None)
        st.session_state.step4_result = result

    if "step4_result" in st.session_state:
        result = st.session_state.step4_result
        st.markdown("### Calculation result")
        status_box("Status", status_text(result.status.replace("_", " ")))
        st.write(
            f"{'Controlled U.S.-origin content value'}: "
            f"{result.controlled_us_content_value if result.controlled_us_content_value is not None else 'n/a'}"
        )
        st.write(
            f"{'Total foreign-product value'}: "
            f"{result.total_foreign_product_value if result.total_foreign_product_value is not None else 'n/a'}"
        )
        if result.ratio is not None:
            st.write(f"{'Ratio'}: **{float(result.ratio) * 100:.2f}%**")
        for warning in result.warnings:
            st.warning(warning)
        for note in result.notes:
            st.caption(note)


def render_step5() -> None:
    st.header("Step 5 - FDP Review")
    st.caption(
        "Describe U.S.-origin software/technology used in the foreign production chain and map the "
        "production chain. Outputs: NO FDP FACTS IDENTIFIED, POTENTIAL FDP ISSUE, or INSUFFICIENT INFORMATION."
    )
    defaults = current_data(5)
    with st.form("step5_form"):
        us_software = st.text_area(
            "U.S.-origin software used in production (name/version and role)",
            value=str(defaults.get("us_software_used", "") or ""),
        )
        us_technology = st.text_area(
            "U.S.-origin technology used in production (describe)",
            value=str(defaults.get("us_technology_used", "") or ""),
        )
        facilities = st.text_area(
            "Foreign production facilities (one per line: name, country)",
            value=str(defaults.get("foreign_production_facilities", "") or ""),
        )
        equipment = st.text_area(
            "Production equipment (one per line)",
            value=str(defaults.get("production_equipment", "") or ""),
        )
        process = st.text_area(
            "Production process description",
            value=str(defaults.get("production_process_description", "") or ""),
            height=100,
        )
        run_button = st.form_submit_button("Run FDP review and save", type="primary")
    if run_button:
        data = {
            "us_software_used": us_software,
            "us_technology_used": us_technology,
            "foreign_production_facilities": facilities,
            "production_equipment": equipment,
            "production_process_description": process,
        }
        store(5, data)
        result = fdp_service.run_fdp_review(FDPReviewInput.model_validate(data))
        st.session_state.step5_result = result
        go_to_step(6)
        st.rerun()

    if "step5_result" in st.session_state:
        result = st.session_state.step5_result
        st.markdown("### FDP review result")
        status_box("FDP flag", status_text(result.flag_label))
        st.write(result.summary)
        if result.dependency_map:
            st.markdown("#### Production Dependency Map")
            st.table(
                pd.DataFrame(
                    [
                        {
                            "Layer": item.layer,
                            "Details": item.details,
                        }
                        for item in result.dependency_map
                    ]
                )
            )
        for note in result.notes:
            st.caption(note)


def render_step6() -> None:
    st.header("Step 6 - Party Screening")
    st.caption(
        "Parties from Steps 1 and 6 are compared with local CSV reference lists using exact match, "
        "fuzzy name match, and similarity scoring. Output is never 'restricted party'; the strongest "
        "result is MANUAL VERIFICATION REQUIRED."
    )
    defaults = current_data(6)
    with st.form("step6_form"):
        parent = st.text_area(
            "Parent companies (one per line)",
            value=str(defaults.get("parent_companies", "") or ""),
        )
        subsidiaries = st.text_area(
            "Subsidiaries (one per line)",
            value=str(defaults.get("subsidiaries", "") or ""),
        )
        directors = st.text_area(
            "Directors (one per line)",
            value=str(defaults.get("directors", "") or ""),
        )
        beneficial = st.text_area(
            "Beneficial owners (one per line)",
            value=str(defaults.get("beneficial_owners", "") or ""),
        )
        submitted = st.form_submit_button("Save additional parties")
    if submitted:
        store(6, {
            "parent_companies": parent,
            "subsidiaries": subsidiaries,
            "directors": directors,
            "beneficial_owners": beneficial,
        })
        st.success("Additional parties saved.")

    uploaded = st.file_uploader(
        "Optional: additional local CSV reference list",
        type=["csv"],
        help="Expected columns: name, aliases, country, reference, source, notes. Lines starting with # are ignored.",
    )
    if uploaded is not None:
        st.session_state.screening_csv_bytes = uploaded.getvalue()
        st.session_state.screening_csv_name = uploaded.name
        st.caption("Loaded extra reference list: " + uploaded.name)

    parties = collect_parties()
    if not parties:
        st.warning(
            "No parties to screen yet. Complete Step 1 or add parent/subsidiary/director/owner names above."
        )
        return

    st.markdown("#### Parties to screen")
    party_table = pd.DataFrame(
        [
            {
                "Role": party_role_label(party.role),
                "Name": party.name,
                "Country": party.country or "",
            }
            for party in parties
        ]
    )
    st.dataframe(party_table, width="stretch")
    if st.button("Run party screening", type="primary"):
        csv_paths = effective_screening_csv_paths()
        temp_path = None
        if st.session_state.screening_csv_bytes:
            handle = tempfile.NamedTemporaryFile(
                mode="w+b", suffix=".csv", prefix="ear_screening_", delete=False
            )
            handle.write(st.session_state.screening_csv_bytes)
            handle.close()
            temp_path = Path(handle.name)
            csv_paths.append(temp_path)
        try:
            output = screening_service.screen_parties(parties, csv_paths=csv_paths)
            st.session_state.step6_result = output
            go_to_step(7)
            st.rerun()
        finally:
            if temp_path:
                temp_path.unlink(missing_ok=True)

    if "step6_result" in st.session_state:
        output = st.session_state.step6_result
        st.markdown("#### Screening results")
        result_rows = []
        for result in output.results:
            result_rows.append(
                {
                    "Role": party_role_label(result.party.role),
                    "Party": result.party.name,
                    "Result": status_text(result.status.replace("_", " ")),
                    "Score": float(result.best_score) if result.best_score is not None else None,
                    "Best match": result.best_match.matched_name if result.best_match else "",
                    "Method": result.best_match.match_method if result.best_match else "",
                }
            )
        st.dataframe(pd.DataFrame(result_rows), width="stretch")
        for result in output.results:
            st.caption(f"{result.party.role} ({result.party.name}): {result.explanation}")


def render_step7() -> None:
    st.header("Step 7 - End Use Review")
    st.caption(
        "Enter the declared end use, installation/delivery location, industry, and use categories."
    )
    defaults = current_data(7)
    with st.form("step7_form"):
        declared = st.text_area(
            "Declared end use",
            value=str(defaults.get("declared_end_use", "") or ""),
            height=100,
        )
        location = st.text_input(
            "Installation location",
            value=str(defaults.get("installation_location", "") or ""),
        )
        industry = st.text_input("Industry", value=str(defaults.get("industry", "") or ""))
        col1, col2, col3 = st.columns(3)
        with col1:
            civil = st.checkbox("Civil use", value=bool(defaults.get("civil_use", False)))
            military = st.checkbox("Military use", value=bool(defaults.get("military_use", False)))
        with col2:
            aerospace = st.checkbox("Aerospace use", value=bool(defaults.get("aerospace_use", False)))
            semiconductor = st.checkbox(
                "Semiconductor use", value=bool(defaults.get("semiconductor_use", False))
            )
        with col3:
            research = st.checkbox("Research use", value=bool(defaults.get("research_use", False)))
            unknown = st.checkbox("Unknown use", value=bool(defaults.get("unknown_use", False)))
        notes = st.text_area(
            "Additional end-use notes",
            value=str(defaults.get("additional_notes", "") or ""),
        )
        run_button = st.form_submit_button("Run end-use review and save", type="primary")
    if run_button:
        data = {
            "declared_end_use": declared,
            "installation_location": location,
            "industry": industry,
            "civil_use": civil,
            "military_use": military,
            "aerospace_use": aerospace,
            "semiconductor_use": semiconductor,
            "research_use": research,
            "unknown_use": unknown,
            "additional_notes": notes,
        }
        store(7, data)
        result = enduse_service.run_end_use_review(EndUseReviewInput.model_validate(data))
        st.session_state.step7_result = result
        go_to_step(8)
        st.rerun()

    if "step7_result" in st.session_state:
        result = st.session_state.step7_result
        st.markdown("### End-use flags")
        st.write(result.summary)
        for flag in result.flags:
            st.warning(f"**{flag_label(flag.label)}** - {flag.detail}")


def preview_required_steps() -> list[int]:
    missing = []
    if not current_data(1):
        missing.append(1)
    if not current_data(2):
        missing.append(2)
    return missing


def render_engine_preview() -> ReviewBundle | None:
    missing = preview_required_steps()
    if missing:
        st.warning(
            "Complete the earlier required steps first: "
            + ", ".join(str(item) for item in missing)
            + "."
        )
        return None
    try:
        bundle = run_all_reviews()
    except ValidationError as exc:
        st.error(
            "Some saved form data is incomplete: "
            + "; ".join(str(error) for error in exc.errors())
        )
        return None
    except Exception as exc:  # surface any user-configuration or data issue
        st.exception(exc)
        return None
    return bundle


def render_step8() -> None:
    st.header("Step 8 - Red Flag Engine")
    st.caption(
        "Rules load from app/rules/red_flag_rules.json and are evaluated against the recorded facts. "
        "Rule points are only indicators, not legal conclusions."
    )
    bundle = render_engine_preview()
    if bundle is None:
        return
    st.markdown("### Triggered red flags")
    if not bundle.red_flags.findings:
        st.success("No red flags matched the recorded facts and configured rules.")
        return
    rows = [
        {
            "Rule": finding.rule_id,
            "Name": finding.name,
            "Points": float(finding.risk_points),
            "Action": finding.action,
            "Explanation": finding.explanation,
        }
        for finding in bundle.red_flags.findings
    ]
    st.dataframe(pd.DataFrame(rows), width="stretch")
    st.markdown(f"**{'Combined red-flag point value'}: {float(bundle.red_flags.total_points):.0f}**")
    st.caption(
        "Red-flag point values feed the configurable risk engine. They do not make a legal "
        "determination about the transaction."
    )
    if st.button("Continue to Step 9 - Risk Engine", type="primary"):
        go_to_step(9)
        st.rerun()


def render_step9() -> None:
    st.header("Step 9 - Risk Engine")
    st.caption(
        "Category scores and total risk level are fully driven by app/rules/risk_rules.json. "
        "Every awarded point is itemized below."
    )
    bundle = render_engine_preview()
    if bundle is None:
        return
    risk = bundle.risk
    st.markdown(
        f"### Overall preliminary risk: **{status_text(risk.level)}** "
        f"({risk.total} / {risk.max_total})"
    )
    category_rows = [
        {
            "Category": risk_category_label(category.label),
            "Score": f"{category.points} / {category.max_points}",
            "Details": category.explanation_lines[0]
            if len(category.explanation_lines) == 1 and category.findings
            else "",
        }
        for category in risk.categories.values()
    ]
    st.dataframe(pd.DataFrame(category_rows), width="stretch")
    for category in risk.categories.values():
        with st.expander(f"{risk_category_label(category.label)} - {category.points} / {category.max_points}"):
            for line in category.explanation_lines:
                st.markdown(f"- {line}")
    st.caption(risk.methodology)
    if st.button("Continue to Step 10 - Legal Review Queue", type="primary"):
        go_to_step(10)
        st.rerun()


def render_step10() -> None:
    st.header("Step 10 - Legal Review Queue")
    st.caption(
        "Routing decisions are configurable in app/rules/review_queue_rules.json. The first matching "
        "rule determines the queue. Routing never authorizes or prohibits a transaction."
    )
    bundle = render_engine_preview()
    if bundle is None:
        return
    queue = bundle.queue
    st.markdown("### Queue decision")
    st.success(f"**{status_text(queue.decision_label)}**")
    st.write(queue.explanation)
    st.write(
        f"{'Matched rule'}: {queue.matched_rule_name or 'default routing'} "
        f"({queue.matched_rule_id or 'n/a'})"
    )
    if st.button("Continue to Step 11 - Report Generator", type="primary"):
        go_to_step(11)
        st.rerun()


def render_step11() -> None:
    st.header("Step 11 - Report Generator")
    st.caption(
        "Generate an HTML report and a downloadable PDF. Reports are stored locally in SQLite "
        "ear_reviews.db for the review history."
    )
    legal_notes = st.text_area(
        "Legal review notes (included in report section 11)",
        value=str(st.session_state.step_data.get("legal_review_notes", "") or ""),
        height=120,
    )
    st.session_state.step_data["legal_review_notes"] = legal_notes
    if st.button("Generate full review report", type="primary"):
        bundle = run_all_reviews(legal_notes=legal_notes)
        st.session_state.generated_bundle = bundle
        st.session_state.generated_html = report_service.build_html_report(bundle)
        st.session_state.generated_pdf = report_service.build_pdf_report(bundle)
        review_id = persist_review(bundle)
        st.session_state.last_saved_id = review_id
        st.rerun()

    if "generated_bundle" not in st.session_state:
        return
    bundle = st.session_state.generated_bundle
    transaction = bundle.transaction
    st.markdown("### Report preview")
    if transaction:
        st.markdown(
            f"**{transaction.transaction_name}**  \n"
            f"{transaction.exporter_name} ({transaction.exporter_country}) → "
            f"{transaction.buyer_name} ({transaction.buyer_country})"
        )
    if bundle.risk:
        st.markdown(
            f"{'Risk level'}: **{status_text(bundle.risk.level)}** "
            f"({bundle.risk.total} / {bundle.risk.max_total})"
        )
    if bundle.queue:
        st.markdown(f"{'Queue decision'}: **{status_text(bundle.queue.decision_label)}**")
    if st.session_state.get("last_saved_id"):
        st.success(
            f"Review saved to local SQLite history as #{st.session_state.last_saved_id}."
        )

    if "generated_html" in st.session_state:
        st.download_button(
            "Download HTML report",
            data=st.session_state.generated_html,
            file_name="ear_transaction_review.html",
            mime="text/html",
            width="stretch",
        )
    if "generated_pdf" in st.session_state:
        st.download_button(
            "Download PDF report",
            data=st.session_state.generated_pdf,
            file_name="ear_transaction_review.pdf",
            mime="application/pdf",
            width="stretch",
        )
    with st.expander("HTML report (inline preview)"):
        st.iframe(st.session_state.generated_html, width="stretch", height=700)


def _ear_record_rows(records: list, limit: int = 200) -> pd.DataFrame:
    rows = []
    for record in records[:limit]:
        rows.append(
            {
                "List": EAR_SOURCE_LABELS.get(record.source_code, record.source_code or record.source),
                "Name": record.name,
                "Aliases": record.aliases or "",
                "Country": record.country or "",
                "Reference": record.reference or "",
            }
        )
    return pd.DataFrame(rows)


def render_list_center() -> None:
    st.header("List & Data Center - Sync latest EAR content")
    st.caption(
        "Official source: the U.S. International Trade Administration's Consolidated Screening List (CSL), "
        "refreshed daily. It includes the BIS Entity List, Denied Persons List, Unverified List, and Military "
        "End User List (State/Treasury lists are available as an option)."
    )

    if st.session_state.pop("ear_sync_applied", False):
        st.success(
            "The latest snapshot has been applied to the local screening file and will be used by party screening."
        )

    summary = ear_list_sync_service.snapshot_summary()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "Local screening records",
        f"{summary['count']:,}" if summary["exists"] else "0",
        help="app/data/ear_synced_lists.csv",
    )
    col2.metric(
        "Last sync",
        str(summary["last_synced_at"] or "—")[:19],
        help="Value reflects the last applied sync.",
    )
    col3.metric("Last added", f"{summary['last_added']:,}")
    col4.metric("Last removed", f"{summary['last_removed']:,}")

    if not summary["exists"]:
        st.info(
            "No synchronized snapshot has been applied yet. Click the button below to download the latest "
            "official lists, review the differences, then apply them to the local screening list."
        )
    else:
        counts = summary["source_counts"] or {}
        label_parts = " · ".join(
            f"{EAR_SOURCE_LABELS.get(code, code)}: {counts.get(code, 0)}"
            for code in ear_list_sync_service.BIS_ONLY_CODES
            if counts.get(code)
        )
        counted = sum(counts.get(code, 0) for code in ear_list_sync_service.BIS_ONLY_CODES)
        if summary["count"] > counted:
            label_parts = (label_parts + " · " if label_parts else "") + (
                f"{EAR_SOURCE_LABELS['']}: {summary['count'] - counted}"
            )
        if label_parts:
            st.caption(f"Current snapshot: {label_parts}.")

    with st.expander("Sync scope", expanded=True):
        scope = st.radio(
            "Which official U.S. lists should be synchronized?",
            [
                "BIS / EAR lists only (recommended)",
                "All CSL lists (State and Treasury included)",
            ],
            horizontal=True,
            key="ear_sync_scope",
            index=0,
        )
        st.caption(
            "EAR review usually needs the four BIS lists. Choosing 'All lists' also adds OFAC SDN and "
            "other State/Treasury lists to the local screening CSV."
        )

    st.warning(
        "The lists come from official U.S. websites and are reference data for initial screening. Any match "
        "still requires manual verification against the Federal Register and the official agency lists; "
        "this tool never declares a party 'restricted' from list data alone."
    )

    if st.button(
        "Sync latest EAR content",
        type="primary",
        width="stretch",
    ):
        include_codes = ear_list_sync_service.BIS_ONLY_CODES if scope.startswith("BIS") else ()
        try:
            with st.spinner(
                "Downloading the official CSL from data.trade.gov and comparing with the local snapshot..."
            ):
                result = ear_list_sync_service.fetch_and_compare(include_codes=include_codes)
            st.session_state.ear_sync_result = result
            st.session_state.ear_sync_error = None
        except Exception as exc:
            st.session_state.ear_sync_error = str(exc)
            st.session_state.ear_sync_result = None

    error = st.session_state.get("ear_sync_error")
    if error:
        st.error(
            "Synchronization failed. Check your internet connection and retry."
            + f"\n\n{error}"
        )
        with st.expander("Troubleshooting"):
            st.markdown(
                "- Network access to data.trade.gov is required; corporate proxies or firewalls may "
                "block .gov traffic.\n"
                "- To use a custom mirror, set the environment variable EAR_CSL_URL or edit the url in "
                "app/rules/ear_sync_sources.json.\n"
                "- Official download page: https://www.trade.gov/consolidated-screening-list"
            )

    result = st.session_state.get("ear_sync_result")
    if result is None:
        return

    st.markdown("### Latest sync result")
    metric_cols = st.columns(5)
    metric_cols[0].metric("Official file rows", f"{result.fetched_total:,}")
    metric_cols[1].metric(
        "Records in scope",
        f"{result.record_count:,}",
        help="Rows kept after applying the selected scope.",
    )
    metric_cols[2].metric("Added", f"{result.added_count:,}")
    metric_cols[3].metric("Removed", f"{result.removed_count:,}")
    metric_cols[4].metric("Modified", f"{result.modified_count:,}")

    if result.initial_load:
        st.info(
            "This is the first sync with no previous local snapshot, so 'added' equals the number of "
            "records loaded for the first time."
        )

    if result.added:
        st.markdown("#### New entries (preview)")
        st.dataframe(_ear_record_rows(result.added), width="stretch", height=280)
        if result.added_count > 200:
            st.caption("Showing the first 200 only; download for the full list.")

    if result.removed:
        st.markdown("#### Removed entries (preview)")
        st.dataframe(_ear_record_rows(result.removed), width="stretch", height=280)
        if result.removed_count > 200:
            st.caption("Showing the first 200 only; download for the full list.")

    if result.modified:
        st.markdown("#### Entries whose details changed (preview)")
        modified_rows = [
            {
                "List": EAR_SOURCE_LABELS.get(new.source_code, new.source_code or new.source),
                "Name": new.name,
                "Change": "Address, aliases, reference, or license details changed",
            }
            for old, new in result.modified[:200]
        ]
        st.dataframe(pd.DataFrame(modified_rows), width="stretch", height=260)

    if not (result.added or result.removed or result.modified):
        st.success(
            "No additions, removals, or modifications were found compared with the previous sync."
        )

    st.markdown("---")
    download_cols = st.columns(2)
    with download_cols[0]:
        st.download_button(
            "Download update log CSV",
            data=ear_list_sync_service.update_log_csv_bytes(result),
            file_name=f"ear_sync_updates_{result.fetched_at[:10]}.csv",
            mime="text/csv",
            width="stretch",
        )
    with download_cols[1]:
        st.download_button(
            "Download full new list CSV",
            data=ear_list_sync_service.snapshot_csv_bytes(result.records),
            file_name=f"ear_synced_lists_{result.fetched_at[:10]}.csv",
            mime="text/csv",
            width="stretch",
        )

    with st.container(border=True):
        st.markdown(
            "#### Apply to the local screening list?"
        )
        st.markdown(
            "Applying overwrites the local snapshot app/data/ear_synced_lists.csv with the downloaded "
            "lists; later party screening automatically uses it. The bundled example list is not deleted."
        )
        confirmed = st.checkbox(
            "I confirm that I reviewed the differences above and understand that official texts still "
            "require manual verification.",
            key="ear_sync_apply_confirm",
        )
        if st.button(
            "Confirm and apply to local screening",
            type="primary",
            width="stretch",
            disabled=not confirmed,
        ):
            ear_list_sync_service.apply_sync_result(result)
            st.session_state.ear_sync_result = None
            st.session_state.ear_sync_applied = True
            st.session_state.ear_sync_apply_confirm = False
            st.rerun()


def main() -> None:
    process_pending_step()
    sidebar()
    disclaimer = st.container(border=True)
    disclaimer.caption(
        ":warning: "
        + "**Important**: This tool provides a preliminary compliance risk assessment based on "
        "user-provided information and configurable rules. It does not constitute legal advice and does "
        "not determine whether an export, reexport, or transfer is authorized under the EAR."
    )
    current = st.session_state.current_step
    renderer = {
        1: render_step1,
        2: render_step2,
        3: render_step3,
        4: render_step4,
        5: render_step5,
        6: render_step6,
        7: render_step7,
        8: render_step8,
        9: render_step9,
        10: render_step10,
        11: render_step11,
    }
    if st.session_state.get("main_view") == MAIN_VIEW_LISTS:
        render_list_center()
    else:
        renderer.get(current, render_step1)()
    st.caption(
        "EAR Transaction Review Tool - local-first Streamlit application. "
        "Facts and results remain on this machine unless you export them."
    )


if __name__ == "__main__":
    main()
