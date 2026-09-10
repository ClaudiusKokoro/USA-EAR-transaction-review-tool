"""Headless Streamlit smoke tests: both pages must render in English.

These tests execute the real Streamlit scripts through ``AppTest`` (no browser
and no network) and assert that no Chinese characters leak into the rendered
interface.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.ai_frontend import config_store

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CJK = re.compile(r"[\u4e00-\u9fff]")

STEP_DATA = {
    "1": {
        "transaction_name": "UI smoke test",
        "exporter_name": "Example Exporter",
        "exporter_country": "CN",
        "buyer_name": "Example Buyer",
        "buyer_country": "SG",
        "transaction_value": 1000.0,
        "currency": "USD",
        "shipment_date": "2026-09-10",
    },
    "2": {
        "product_name": "Ethernet switch",
        "product_description": "Commercial 48-port switch",
        "category": "Electronics",
    },
}


def rendered_text(at) -> str:
    chunks: list[str] = []
    for attribute in (
        "markdown",
        "header",
        "title",
        "caption",
        "info",
        "warning",
        "error",
        "success",
        "text_input",
        "text_area",
        "selectbox",
    ):
        for element in getattr(at, attribute, []) or []:
            value = getattr(element, "value", "")
            if value:
                chunks.append(str(value))
    for element in at.sidebar.markdown or []:
        chunks.append(str(getattr(element, "value", "")))
    return "\n".join(chunks)


def assert_english(at, label: str) -> str:
    assert not at.exception, f"{label} raised: {at.exception}"
    text = rendered_text(at)
    assert not CJK.findall(text), f"{label} rendered Chinese characters"
    return text


def run_review_page(current_step: int = 1, main_view: str | None = None):
    AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
    at = AppTest.from_file(str(PROJECT_ROOT / "app" / "main.py"), default_timeout=30)
    at.session_state["step_data"] = STEP_DATA
    at.session_state["current_step"] = current_step
    if main_view:
        at.session_state["main_view_radio"] = main_view
    at.run()
    return at


def test_review_workbench_renders_in_english():
    text = assert_english(run_review_page(), "review page")
    assert "Step 1 - Transaction Intake" in text


def test_review_steps_and_list_center_render_in_english():
    assert "Party Screening" in assert_english(run_review_page(current_step=6), "step 6")
    assert "Report Generator" in assert_english(run_review_page(current_step=11), "step 11")
    assert "List & Data Center" in assert_english(
        run_review_page(main_view="List & Data Center"), "list center"
    )


def _ai_config(provider: str = "openai") -> dict:
    config = config_store.load_config(path=Path("missing-config.json"))
    config["provider"] = provider
    return config_store.update_provider(config, provider, {"api_key": "sk-test"})


def run_ai_page(page: str, provider: str = "openai"):
    AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
    at = AppTest.from_file(str(PROJECT_ROOT / "app" / "ai_main.py"), default_timeout=30)
    at.session_state["ai_config"] = _ai_config(provider)
    at.session_state["ai_page"] = page
    at.run()
    return at


def test_ai_frontend_pages_render_in_english():
    overview = assert_english(run_ai_page("Overview"), "AI overview")
    assert "OpenAI (GPT)" in overview
    assert "Question Interfaces" in assert_english(
        run_ai_page("3 - EAR Question Interfaces"), "question page"
    )
    assert "Active provider: OpenAI (GPT)" in assert_english(
        run_ai_page("2 - File Analysis"), "file analysis page"
    )


def test_ai_provider_page_supports_claude():
    text = assert_english(run_ai_page("1 - Provider & API", provider="anthropic"), "anthropic config")
    assert "Anthropic (Claude)" in text
    assert "api.anthropic.com" in text
