"""Tests for the multi-provider AI frontend modules."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ai_frontend import config_store, file_utils, llm_client, providers, question_registry


def _config(provider: str = "openai", **values) -> dict:
    """Build a saved config for a provider with the given key/model overrides."""

    base = config_store.load_config(path=Path("does-not-exist.json"))
    base["provider"] = provider
    base = config_store.update_provider(base, provider, {"api_key": "sk-test", **values})
    return base


# --- config store ---------------------------------------------------------


def test_config_round_trip(tmp_path: Path):
    path = tmp_path / "ai_config.json"
    config = config_store.load_config(path=path)
    config["provider"] = "anthropic"
    config = config_store.update_provider(
        config,
        "anthropic",
        {"api_key": "sk-ant-1234", "model": "claude-sonnet-4-5"},
    )
    config_store.save_config(config, path=path)

    loaded = config_store.load_config(path=path)
    assert loaded["provider"] == "anthropic"
    assert loaded["providers"]["anthropic"]["api_key"] == "sk-ant-1234"
    assert loaded["providers"]["anthropic"]["model"] == "claude-sonnet-4-5"
    assert loaded["temperature"] == config_store.SHARED_DEFAULTS["temperature"]


def test_config_missing_file_returns_defaults(tmp_path: Path):
    loaded = config_store.load_config(path=tmp_path / "missing.json")
    assert loaded == config_store.DEFAULT_CONFIG


def test_legacy_deepseek_config_is_migrated(tmp_path: Path):
    path = tmp_path / "ai_config.json"
    path.write_text(
        """
        {
          "api_key": "sk-legacy",
          "base_url": "https://api.deepseek.com",
          "chat_endpoint_path": "/chat/completions",
          "model": "deepseek-reasoner",
          "temperature": 0.3,
          "upload_endpoint": "https://api.deepseek.com/v1/files",
          "upload_purpose": "assistants",
          "max_context_chars": 50000
        }
        """,
        encoding="utf-8",
    )
    loaded = config_store.load_config(path=path)
    assert loaded["provider"] == "deepseek"
    assert loaded["providers"]["deepseek"]["api_key"] == "sk-legacy"
    assert loaded["providers"]["deepseek"]["model"] == "deepseek-reasoner"
    assert loaded["temperature"] == 0.3
    assert loaded["max_context_chars"] == 50000


def test_update_provider_does_not_touch_other_providers():
    config = config_store.load_config(path=Path("does-not-exist.json"))
    config = config_store.update_provider(config, "openai", {"api_key": "sk-openai"})
    config = config_store.update_provider(config, "glm", {"api_key": "sk-glm"})
    assert config["providers"]["openai"]["api_key"] == "sk-openai"
    assert config["providers"]["glm"]["api_key"] == "sk-glm"


def test_mask_api_key():
    assert config_store.mask_api_key("") == "(not set)"
    masked = config_store.mask_api_key("sk-abcdefghijklmnop")
    assert masked.startswith("sk-a")
    assert masked.endswith("mnop")
    assert len(masked) == len("sk-abcdefghijklmnop")


# --- provider registry ----------------------------------------------------


def test_provider_registry_covers_common_vendors():
    ids = providers.provider_ids()
    for expected in ("openai", "anthropic", "deepseek", "glm", "qwen", "custom"):
        assert expected in ids
    for spec in providers.PROVIDERS.values():
        assert spec.chat_path.startswith("/")
        if spec.id != "custom":
            assert spec.base_url.startswith("http")
            assert spec.default_model


def test_provider_settings_use_spec_defaults():
    config = config_store.load_config(path=Path("does-not-exist.json"))
    settings = config_store.provider_settings(config, "anthropic")
    assert settings["provider_label"] == "Anthropic (Claude)"
    assert settings["api_style"] == "anthropic"
    assert settings["base_url"] == "https://api.anthropic.com/v1"
    assert settings["model"] == providers.PROVIDERS["anthropic"].default_model


def test_guess_provider_from_url():
    assert providers.guess_provider_from_url("https://api.deepseek.com") == "deepseek"
    assert providers.guess_provider_from_url("https://api.anthropic.com/v1") == "anthropic"
    assert providers.guess_provider_from_url("https://open.bigmodel.cn/api/paas/v4") == "glm"
    assert providers.guess_provider_from_url("https://dashscope.aliyuncs.com/compatible-mode/v1") == "qwen"
    assert providers.guess_provider_from_url("") == providers.DEFAULT_PROVIDER_ID


# --- question registry ----------------------------------------------------


def test_question_registry_has_independent_interfaces():
    interfaces = question_registry.load_question_interfaces()
    ids = [item["interface_id"] for item in interfaces]
    assert len(ids) >= 10
    assert len(set(ids)) == len(ids)
    required = {
        "ear.jurisdiction.us_origin",
        "ear.transaction.ultimate_end_user",
        "ear.end_use.purpose",
    }
    assert required.issubset(set(ids))
    for interface in interfaces:
        assert interface["name_en"]
        assert interface["question_en"]
        assert " / " not in interface["category"] or interface["category"].startswith("EAR")


def test_question_categories_are_english():
    categories = question_registry.list_categories()
    assert categories
    assert all(not any("\u4e00" <= char <= "\u9fff" for char in name) for name in categories)
    assert "Transaction & Parties" in categories


def test_build_interview_messages_include_guardrails():
    interface = question_registry.get_interface("ear.jurisdiction.us_origin")
    messages = question_registry.build_interview_messages(interface)
    combined = messages[0]["content"] + messages[1]["content"]
    assert "never state that a transaction is legal" in messages[0]["content"].lower()
    assert "U.S.-origin" in combined
    assert "never" in messages[0]["content"].lower()


def test_build_interview_messages_supports_chinese_optional_language():
    interface = question_registry.get_interface("ear.jurisdiction.us_origin")
    messages = question_registry.build_interview_messages(interface, language="zh")
    assert "不得输出" in messages[0]["content"]


# --- client ---------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def test_missing_api_key_raises():
    config = config_store.load_config(path=Path("does-not-exist.json"))
    with pytest.raises(llm_client.LLMClientError):
        llm_client.send_chat(config, [{"role": "user", "content": "hello"}])


def test_upload_unsupported_provider_raises():
    config = _config("deepseek")
    assert not llm_client.supports_upload(llm_client.resolve_settings(config))
    with pytest.raises(llm_client.LLMClientError):
        llm_client.upload_file(config, "a.txt", b"data")


def test_openai_upload_is_supported_by_default():
    config = _config("openai")
    settings = llm_client.resolve_settings(config)
    assert llm_client.supports_upload(settings)
    assert llm_client.upload_url(settings) == "https://api.openai.com/v1/files"


def test_chat_url_for_providers_and_legacy_config():
    assert (
        llm_client.chat_url(config_store.provider_settings(_config("openai"), "openai"))
        == "https://api.openai.com/v1/chat/completions"
    )
    assert (
        llm_client.chat_url(config_store.provider_settings(_config("anthropic"), "anthropic"))
        == "https://api.anthropic.com/v1/messages"
    )
    legacy = {
        "api_key": "sk",
        "base_url": "https://api.deepseek.com",
        "chat_endpoint_path": "/chat/completions",
        "model": "deepseek-chat",
    }
    assert llm_client.chat_url(llm_client.resolve_settings(legacy)) == "https://api.deepseek.com/chat/completions"


def test_build_request_openai_style():
    settings = config_store.provider_settings(_config("deepseek"), "deepseek")
    url, headers, payload = llm_client.build_request(
        settings, [{"role": "user", "content": "ping"}]
    )
    assert url == "https://api.deepseek.com/v1/chat/completions"
    assert headers["Authorization"] == "Bearer sk-test"
    assert payload["model"] == "deepseek-chat"
    assert payload["stream"] is False
    assert "response_format" not in payload


def test_build_request_anthropic_style_splits_system():
    config = _config("anthropic", model="claude-sonnet-4-5")
    settings = config_store.provider_settings(config, "anthropic")
    url, headers, payload = llm_client.build_request(
        settings,
        [
            {"role": "system", "content": "guardrails"},
            {"role": "user", "content": "ping"},
        ],
    )
    assert url == "https://api.anthropic.com/v1/messages"
    assert headers["x-api-key"] == "sk-test"
    assert headers["anthropic-version"] == llm_client.ANTHROPIC_VERSION
    assert payload["system"] == "guardrails"
    assert payload["messages"] == [{"role": "user", "content": "ping"}]
    assert payload["max_tokens"] >= 1


def test_parse_response_anthropic():
    settings = config_store.provider_settings(_config("anthropic"), "anthropic")
    parsed = llm_client.parse_response(
        settings,
        {
            "content": [{"type": "text", "text": "hello"}],
            "usage": {"input_tokens": 1},
            "model": "claude-sonnet-4-5",
        },
    )
    assert parsed["content"] == "hello"
    assert parsed["usage"]["input_tokens"] == 1


def test_send_chat_normalized_response(monkeypatch):
    config = _config("openai")

    captured: dict = {}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _FakeResponse(
            200,
            {
                "choices": [{"message": {"content": "OK"}}],
                "usage": {"total_tokens": 3},
                "model": "gpt-4.1-mini",
            },
        )

    monkeypatch.setattr(llm_client.requests, "post", fake_post)
    result = llm_client.send_chat(config, [{"role": "user", "content": "ping"}])
    assert result["content"] == "OK"
    assert result["usage"]["total_tokens"] == 3
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["json"]["model"] == "gpt-4.1-mini"


def test_send_chat_http_error(monkeypatch):
    config = _config("qwen")
    monkeypatch.setattr(
        llm_client.requests,
        "post",
        lambda url, headers, json, timeout: _FakeResponse(401, {"error": "bad key"}),
    )
    with pytest.raises(llm_client.LLMClientError) as excinfo:
        llm_client.send_chat(config, [{"role": "user", "content": "ping"}])
    assert "401" in str(excinfo.value)
    assert "Qwen" in str(excinfo.value)


# --- file utilities -------------------------------------------------------


def test_extract_text_plain_file():
    text, note = file_utils.extract_text("sample.txt", "hello EAR".encode("utf-8"), max_chars=100)
    assert "hello EAR" in text
    assert "plain text" in note


def test_extract_text_unsupported_binary_note():
    text, note = file_utils.extract_text("archive.zip", b"PK\x03\x04", max_chars=100)
    assert text == ""
    assert "zip" in note
