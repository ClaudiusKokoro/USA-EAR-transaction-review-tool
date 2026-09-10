"""EAR Transaction Review Tool - AI assistant frontend (multi-provider).

Run from the project root:

    streamlit run app/ai_main.py

Features:
1. Provider & API configuration - GPT, Claude, DeepSeek, GLM, Qwen, Moonshot,
   Ollama, or any custom OpenAI-compatible gateway. Saved locally.
2. File analysis - upload supporting documents, optionally POST them to a
   provider Files API, always extract local text and let the model summarize
   EAR-relevant facts.
3. EAR question interfaces - every review question is a standalone interface
   that can prompt the model one at a time; answers are collected into an
   exportable draft.

This page never produces legal conclusions, and provider calls only happen when
you click a button.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st  # noqa: E402

from app.ai_frontend import config_store, file_utils, llm_client, providers  # noqa: E402
from app.ai_frontend import question_registry  # noqa: E402

st.set_page_config(
    page_title="EAR AI Assistant",
    page_icon=":robot_face:",
    layout="wide",
)


def init_session() -> None:
    if "ai_config" not in st.session_state:
        st.session_state.ai_config = config_store.load_config()
    if "ear_answers" not in st.session_state:
        st.session_state.ear_answers = {}
    if "ask_results" not in st.session_state:
        st.session_state.ask_results = {}
    if "analysis_results" not in st.session_state:
        st.session_state.analysis_results = {}
    if "review_summary" not in st.session_state:
        st.session_state.review_summary = ""


def active_settings() -> dict:
    return config_store.provider_settings(st.session_state.ai_config)


def has_api_key(settings: dict) -> bool:
    if settings.get("auth_style") == "none":
        return True
    return bool(str(settings.get("api_key") or "").strip())


def require_provider() -> dict | None:
    settings = active_settings()
    if not has_api_key(settings):
        st.error(
            f"No API key is configured for {settings['provider_label']}. "
            "Open '1 - Provider & API' to add one."
        )
        return None
    return settings


def render_config() -> None:
    st.header("1 - Provider & API")
    config = st.session_state.ai_config
    provider_ids = providers.provider_ids()
    labels = providers.provider_labels()
    current_id = str(config.get("provider") or providers.DEFAULT_PROVIDER_ID)
    index = provider_ids.index(current_id) if current_id in provider_ids else 0

    st.caption(
        "Settings are stored locally in app/data/ai_config.json (git-ignored). "
        "Requests are sent to a provider only when you click a button."
    )

    selected_id = st.selectbox(
        "Provider",
        provider_ids,
        index=index,
        format_func=lambda value: labels.get(value, value),
        key="ai_provider_select",
    )
    spec = providers.get_provider(selected_id)
    settings = config_store.provider_settings(config, selected_id)
    st.info(
        f"Active key for {spec.label}: {config_store.mask_api_key(settings['api_key'])} | "
        f"Model: {settings['model'] or '(not set)'}"
    )
    if spec.notes:
        st.caption(spec.notes)
    if spec.docs_url:
        st.caption(f"API documentation: {spec.docs_url}")

    with st.form(f"provider_config_form_{selected_id}", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            api_key = st.text_input(
                f"{spec.label} API key",
                value="",
                type="password",
                help="Leave blank to keep the saved key.",
                key=f"api_key_{selected_id}",
            )
            model = st.text_input(
                "Model",
                value=settings["model"],
                help="Type any model identifier supported by this provider.",
                key=f"model_{selected_id}",
            )
            if settings["models"]:
                st.caption("Suggested models: " + ", ".join(settings["models"]))
            base_url = st.text_input(
                "Base URL",
                value=settings["base_url"],
                help="Provider API root, without the chat path.",
                key=f"base_url_{selected_id}",
            )
        with col2:
            chat_path = st.text_input(
                "Chat endpoint path",
                value=settings["chat_path"],
                help="For example /chat/completions (OpenAI-style) or /messages (Anthropic).",
                key=f"chat_path_{selected_id}",
            )
            temperature = st.number_input(
                "Temperature",
                min_value=0.0,
                max_value=1.5,
                step=0.05,
                value=float(config.get("temperature", 0.2)),
                key=f"temperature_{selected_id}",
            )
            timeout = st.number_input(
                "Request timeout (seconds)",
                min_value=10,
                max_value=600,
                step=10,
                value=int(config.get("timeout_seconds", 120)),
                key=f"timeout_{selected_id}",
            )
        with st.expander("Advanced options"):
            upload_endpoint = st.text_input(
                "File upload endpoint (optional)",
                value=settings["upload_endpoint"],
                help=(
                    "Absolute URL of an OpenAI-style /files endpoint. Leave blank to use the "
                    "provider default, or when the provider has no file API."
                ),
                key=f"upload_endpoint_{selected_id}",
            )
            upload_purpose = st.text_input(
                "Upload purpose field",
                value=str(config.get("upload_purpose", "assistants")),
                key=f"upload_purpose_{selected_id}",
            )
            max_context_chars = st.number_input(
                "Maximum extracted characters per file",
                min_value=1000,
                max_value=400000,
                step=1000,
                value=int(config.get("max_context_chars", 60000)),
                key=f"max_context_chars_{selected_id}",
            )
        submitted = st.form_submit_button("Save configuration", type="primary")

    if submitted:
        values = {
            "api_key": api_key.strip() or settings["api_key"],
            "model": model.strip() or spec.default_model,
            "base_url": base_url.strip() or spec.base_url,
            "chat_path": chat_path.strip() or spec.chat_path,
            "upload_endpoint": upload_endpoint.strip(),
        }
        updated = config_store.update_provider(config, selected_id, values)
        updated.update(
            {
                "provider": selected_id,
                "temperature": float(temperature),
                "timeout_seconds": int(timeout),
                "max_context_chars": int(max_context_chars),
                "upload_purpose": upload_purpose.strip() or "assistants",
            }
        )
        config_store.save_config(updated)
        st.session_state.ai_config = config_store.load_config()
        st.success(f"Configuration for {spec.label} saved locally.")

    st.markdown("#### Connection test")
    st.caption("The test uses the saved configuration, so save your changes first.")
    if st.button("Test chat endpoint", type="secondary"):
        try:
            result = llm_client.test_connection(config_store.load_config())
            st.success(f"Connection OK. Model replied: {result['content'][:200]}")
        except llm_client.LLMClientError as exc:
            st.error(str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            st.exception(exc)

    st.markdown("#### File handling")
    if spec.supports_upload:
        st.caption(
            f"{spec.label} exposes an OpenAI-style Files API. The upload button POSTs the "
            "original file and the frontend also extracts text locally so the chat request "
            "works even when the upload endpoint rejects a document type."
        )
    else:
        st.caption(
            f"{spec.label} has no documented file endpoint in this tool. Files are parsed "
            "locally (TXT, Markdown, CSV, JSON, PDF, DOCX, XLSX, HTML, XML) and the extracted "
            "text is sent with the chat request."
        )


def _handle_file(config: dict, uploaded) -> None:
    settings = config_store.provider_settings(config)
    filename = uploaded.name
    file_bytes = uploaded.getvalue()
    st.markdown(f"### {filename}")

    upload_note = ""
    if llm_client.supports_upload(settings):
        try:
            upload_result = llm_client.upload_file(
                config, filename, file_bytes, purpose=str(config.get("upload_purpose") or "assistants")
            )
            st.success(f"Uploaded to the provider file endpoint (HTTP {upload_result['status_code']}).")
            with st.expander("Upload response"):
                st.json(upload_result["response"])
            upload_note = f"Uploaded to provider (HTTP {upload_result['status_code']})."
        except llm_client.LLMClientError as exc:
            upload_note = str(exc)
            st.warning(f"Direct upload did not succeed: {exc}\n\nFalling back to local text extraction.")
    else:
        upload_note = f"{settings['provider_label']} has no file endpoint; using local text extraction."
        st.info(upload_note)

    file_text, extract_note = file_utils.extract_text(
        filename,
        file_bytes,
        max_chars=int(config.get("max_context_chars", 60000)),
    )
    st.caption(extract_note)
    if file_text:
        with st.expander("Extracted text preview (first 3000 characters)"):
            st.text(file_text[:3000])
    else:
        st.warning("No readable text was extracted, so no chat analysis was requested for this file.")
        return

    messages = question_registry.build_analysis_messages(filename, file_text)
    prompt = str(st.session_state.get("analysis_prompt") or "").strip()
    if prompt:
        messages[-1]["content"] = messages[-1]["content"] + "\n\nAdditional instructions:\n" + prompt
    with st.spinner(f"{settings['provider_label']} is analyzing the document..."):
        try:
            result = llm_client.send_chat(config, messages)
            st.markdown(result["content"])
            st.session_state.analysis_results[filename] = {
                "filename": filename,
                "provider": settings["provider_label"],
                "upload_note": upload_note,
                "extract_note": extract_note,
                "analysis": result["content"],
            }
        except llm_client.LLMClientError as exc:
            st.error(str(exc))


def render_files() -> None:
    st.header("2 - File Analysis")
    config = st.session_state.ai_config
    settings = require_provider()
    if settings is None:
        return
    st.caption(
        f"Active provider: {settings['provider_label']} ({settings['model']}). "
        "Files never leave this machine unless you click the analyze button."
    )

    uploaded_files = st.file_uploader(
        "Upload supporting files (multiple selections allowed)",
        type=["txt", "md", "csv", "json", "pdf", "docx", "doc", "xlsx", "xls", "xml", "html", "log"],
        accept_multiple_files=True,
        help="Text is extracted locally first; providers with a Files API also receive the original file.",
    )
    st.session_state.analysis_prompt = st.text_area(
        "Analysis instructions (optional)",
        value=str(
            st.session_state.get("analysis_prompt")
            or "Summarize the EAR-relevant facts in this file, the missing information, and the "
            "follow-up questions I should confirm."
        ),
        height=80,
    )
    if st.button("Extract and analyze files", type="primary"):
        if not uploaded_files:
            st.warning("Select at least one file first.")
        else:
            for uploaded in uploaded_files:
                _handle_file(config, uploaded)

    if st.session_state.analysis_results:
        st.markdown("#### Recent analysis results")
        for filename, payload in st.session_state.analysis_results.items():
            with st.expander(filename):
                st.caption(payload.get("extract_note", ""))
                st.markdown(payload.get("analysis", ""))


def render_questions() -> None:
    st.header("3 - EAR Question Interfaces")
    st.caption(
        "Each entry below is a standalone interface (interface_id). Ask the model to pose one "
        "answerable factual question for that review topic, record your answer, and export the "
        "draft. No interface produces a legal conclusion."
    )
    config = st.session_state.ai_config
    settings = require_provider()
    if settings is None:
        return

    interfaces = question_registry.load_question_interfaces()
    categories = question_registry.list_categories(interfaces)
    selected_category = st.selectbox("Browse by review topic", categories)

    review_summary = st.text_area(
        "Review summary (optional, helps the model spot missing facts)",
        value=st.session_state.review_summary,
        height=120,
        help="Paste the parties, product, destination, and end-use facts you already know.",
    )
    st.session_state.review_summary = review_summary

    for interface in interfaces:
        if interface.get("category") != selected_category:
            continue
        interface_id = interface["interface_id"]
        title = interface.get("name_en") or interface_id
        with st.expander(f"{title}  ·  {interface_id}", expanded=False):
            st.markdown(f"**Question:** {interface.get('question_en')}")
            st.caption(
                f"Maps to: {', '.join(interface.get('maps_to', []))} | "
                f"Answer type: {interface.get('expected_answer_type')} | "
                f"Related step: {interface.get('related_stage')}"
            )
            options = interface.get("options") or []
            if options:
                st.caption("Suggested options: " + " / ".join(options))

            if st.button(f"Ask {settings['provider_label']} this question", key=f"ask_{interface_id}"):
                file_text = ""
                if interface_id == "ear.evidence.documents" and st.session_state.analysis_results:
                    file_text = "\n\n".join(
                        payload.get("analysis", "")
                        for payload in st.session_state.analysis_results.values()
                    )
                messages = question_registry.build_interview_messages(
                    interface,
                    review_summary=review_summary,
                    file_text=file_text,
                )
                with st.spinner("Preparing the question..."):
                    try:
                        result = llm_client.send_chat(config, messages)
                        st.session_state.ask_results[interface_id] = result["content"]
                    except llm_client.LLMClientError as exc:
                        st.session_state.ask_results[interface_id] = f"Request failed: {exc}"
                st.rerun()

            if interface_id in st.session_state.ask_results:
                st.info(st.session_state.ask_results[interface_id])

            saved_answer = st.session_state.ear_answers.get(interface_id, {}).get("answer", "")
            answer = st.text_area(
                "Your answer (kept in the review draft)",
                value=saved_answer,
                height=100,
                key=f"answer_{interface_id}",
            )
            if st.button("Save this answer", key=f"save_{interface_id}"):
                st.session_state.ear_answers[interface_id] = {
                    "interface_id": interface_id,
                    "name_en": interface.get("name_en", ""),
                    "category": interface.get("category", ""),
                    "question": interface.get("question_en", ""),
                    "answer": answer,
                    "maps_to": interface.get("maps_to", []),
                }
                st.success("Answer saved to the review draft for this session.")
                st.rerun()

    st.markdown("---")
    st.markdown("#### Export review draft")
    st.caption(f"Saved answers: {len(st.session_state.ear_answers)} of {len(interfaces)} interfaces.")
    draft_json = json.dumps(
        {
            "provider": settings["provider_label"],
            "model": settings["model"],
            "review_summary": st.session_state.review_summary,
            "answers": list(st.session_state.ear_answers.values()),
        },
        ensure_ascii=False,
        indent=2,
    )
    st.download_button(
        "Download questionnaire draft (JSON)",
        data=draft_json,
        file_name="ear_ai_questionnaire_draft.json",
        mime="application/json",
        width="stretch",
    )


def render_overview() -> None:
    st.header("Overview")
    config = st.session_state.ai_config
    settings = config_store.provider_settings(config)
    interfaces = question_registry.load_question_interfaces()
    st.markdown(
        f"""
- Provider: **{settings['provider_label']}**
- Model: **{settings['model'] or '(not set)'}**
- Base URL: `{settings['base_url'] or '(not set)'}`
- API key: {config_store.mask_api_key(settings['api_key'])}
- File endpoint: {'yes' if llm_client.supports_upload(settings) else 'local text extraction only'}
- Standalone EAR question interfaces: **{len(interfaces)}**
        """
    )
    st.info(
        "This frontend only configures a provider, analyzes uploaded documents, and collects "
        "EAR review facts through one question interface at a time. Every output is preliminary "
        "working material, not legal advice."
    )


def main() -> None:
    init_session()
    st.sidebar.title("EAR AI Assistant")
    st.sidebar.caption("EAR Transaction Review Tool - multi-provider frontend")
    page = st.sidebar.radio(
        "Pages",
        ["Overview", "1 - Provider & API", "2 - File Analysis", "3 - EAR Question Interfaces"],
        key="ai_page",
    )
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "**Important**\n\n"
        "This tool supports preliminary fact collection and risk indicators. "
        "It does not provide legal conclusions and does not determine whether an "
        "export is authorized."
    )
    disclaimer = st.container(border=True)
    disclaimer.caption(
        ":warning: When you click a request button, the provider, model, API key, document text, "
        "and review summary you entered are sent to the third-party service you configured. Only "
        "upload material you are authorized to share. Output is preliminary working material "
        "and is not legal advice."
    )

    if page == "Overview":
        render_overview()
    elif page == "1 - Provider & API":
        render_config()
    elif page == "2 - File Analysis":
        render_files()
    else:
        render_questions()


if __name__ == "__main__":
    main()
