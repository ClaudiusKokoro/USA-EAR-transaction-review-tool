"""Multi-provider LLM client used by the AI frontend.

Supported API styles:

* OpenAI-compatible ``POST {base_url}{chat_path}`` with a ``Bearer`` token -
  OpenAI (GPT), DeepSeek, Zhipu GLM, Qwen/DashScope, Moonshot, Ollama, and any
  custom gateway.
* Anthropic Messages API (``POST {base_url}/messages`` with ``x-api-key`` and
  ``anthropic-version`` headers).

File handling is vendor aware: providers that expose an OpenAI-style Files API
can receive a real multipart upload; every provider can still analyze locally
extracted document text (see ``file_utils``), which keeps the workflow
identical across vendors.
"""

from __future__ import annotations

import mimetypes
from typing import Any

import requests

from app.ai_frontend import config_store, providers

ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MAX_TOKENS = 4096


class LLMClientError(RuntimeError):
    """Raised when the configured provider cannot be reached or returns an error."""


def resolve_settings(config: dict[str, Any]) -> dict[str, Any]:
    """Return normalized provider settings for either the new or legacy schema."""

    if isinstance(config, dict) and isinstance(config.get("providers"), dict) and "providers" in config:
        return config_store.provider_settings(config)

    provider_id = providers.guess_provider_from_url(str(config.get("base_url") or ""))
    spec = providers.get_provider(provider_id)
    settings = {
        "provider": spec.id,
        "provider_label": spec.label,
        "api_style": spec.api_style,
        "auth_style": spec.auth_style,
        "api_key": "",
        "model": spec.default_model,
        "base_url": spec.base_url.rstrip("/"),
        "chat_path": spec.chat_path,
        "upload_endpoint": "",
        "upload_path": spec.upload_path,
        "upload_purpose": str(config.get("upload_purpose") or "assistants"),
        "temperature": float(config.get("temperature", 0.2)),
        "timeout_seconds": int(config.get("timeout_seconds", 120)),
        "max_context_chars": int(config.get("max_context_chars", 60000)),
        "docs_url": spec.docs_url,
        "notes": spec.notes,
        "models": list(spec.models),
    }
    legacy_map = {
        "api_key": "api_key",
        "model": "model",
        "base_url": "base_url",
        "chat_endpoint_path": "chat_path",
        "upload_endpoint": "upload_endpoint",
    }
    for source_key, target_key in legacy_map.items():
        value = config.get(source_key)
        if value:
            settings[target_key] = str(value).strip()
    if "temperature" in config and config["temperature"] is not None:
        settings["temperature"] = float(config["temperature"])
    if "timeout_seconds" in config and config["timeout_seconds"] is not None:
        settings["timeout_seconds"] = int(config["timeout_seconds"])
    settings["base_url"] = str(settings["base_url"]).rstrip("/")
    return settings


def chat_url(settings: dict[str, Any]) -> str:
    path = str(settings.get("chat_path") or "/chat/completions")
    if path.startswith("http://") or path.startswith("https://"):
        return path
    base = str(settings.get("base_url") or "").rstrip("/")
    return f"{base}/{path.lstrip('/')}"


def upload_url(settings: dict[str, Any]) -> str:
    endpoint = str(settings.get("upload_endpoint") or "").strip()
    if endpoint:
        return endpoint
    upload_path = settings.get("upload_path")
    if not upload_path:
        return ""
    base = str(settings.get("base_url") or "").rstrip("/")
    return f"{base}/{str(upload_path).lstrip('/')}"


def supports_upload(settings: dict[str, Any]) -> bool:
    return bool(upload_url(settings))


def provider_label(settings: dict[str, Any]) -> str:
    return str(settings.get("provider_label") or settings.get("provider") or "provider")


def _headers(settings: dict[str, Any]) -> dict[str, str]:
    auth_style = str(settings.get("auth_style") or "bearer")
    api_key = str(settings.get("api_key") or "").strip()
    if auth_style != "none" and not api_key:
        raise LLMClientError(
            f"No API key configured for {provider_label(settings)}. "
            "Open '1 - Provider & API' and save your key first."
        )
    headers = {"Content-Type": "application/json"}
    if auth_style == "x-api-key":
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = ANTHROPIC_VERSION
    elif auth_style == "bearer":
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _split_system(messages: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
    system_parts: list[str] = []
    conversation: list[dict[str, str]] = []
    for message in messages:
        role = str(message.get("role") or "user")
        content = str(message.get("content") or "")
        if role == "system":
            system_parts.append(content)
        else:
            conversation.append({"role": role, "content": content})
    return "\n\n".join(part for part in system_parts if part), conversation


def build_request(
    settings: dict[str, Any],
    messages: list[dict[str, str]],
    json_mode: bool = False,
    temperature: float | None = None,
) -> tuple[str, dict[str, str], dict[str, Any]]:
    """Build (url, headers, payload) for the configured provider."""

    model = str(settings.get("model") or "").strip()
    if not model:
        raise LLMClientError(
            f"No model configured for {provider_label(settings)}. "
            "Open '1 - Provider & API' and choose or type a model."
        )
    resolved_temperature = float(
        temperature if temperature is not None else settings.get("temperature", 0.2)
    )
    max_tokens = int(settings.get("max_tokens") or DEFAULT_MAX_TOKENS)
    headers = _headers(settings)

    if str(settings.get("api_style")) == "anthropic":
        system, conversation = _split_system(messages)
        if json_mode:
            system = (system + "\n\nRespond with a single valid JSON object and no other text.").strip()
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": min(max(resolved_temperature, 0.0), 1.0),
            "messages": conversation,
        }
        if system:
            payload["system"] = system
        return chat_url(settings), headers, payload

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": resolved_temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    return chat_url(settings), headers, payload


def parse_response(settings: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    """Normalize a provider response into {content, usage, model, raw}."""

    if str(settings.get("api_style")) == "anthropic":
        blocks = data.get("content") or []
        text = "".join(
            str(block.get("text") or "")
            for block in blocks
            if isinstance(block, dict) and block.get("type") in (None, "text")
        )
        return {
            "content": text,
            "usage": data.get("usage"),
            "model": data.get("model"),
            "raw": data,
        }
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMClientError(
            f"{provider_label(settings)} returned an unexpected response body."
        ) from exc
    return {
        "content": content,
        "usage": data.get("usage"),
        "model": data.get("model"),
        "raw": data,
    }


def send_chat(
    config: dict[str, Any],
    messages: list[dict[str, str]],
    json_mode: bool = False,
    temperature: float | None = None,
) -> dict[str, Any]:
    """Send a non-streaming chat request and return a normalized response."""

    settings = resolve_settings(config)
    url, headers, payload = build_request(
        settings, messages, json_mode=json_mode, temperature=temperature
    )
    timeout = int(settings.get("timeout_seconds") or 120)
    label = provider_label(settings)
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise LLMClientError(f"Could not reach {label}: {exc}") from exc
    if response.status_code >= 400:
        raise LLMClientError(
            f"{label} returned HTTP {response.status_code}: {response.text[:1000]}"
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise LLMClientError(
            f"{label} returned a response that is not JSON: {response.text[:1000]}"
        ) from exc
    return parse_response(settings, data)


def test_connection(config: dict[str, Any]) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": "You are a connectivity test. Reply with exactly: OK"},
        {"role": "user", "content": "ping"},
    ]
    return send_chat(config, messages, temperature=0)


def upload_file(
    config: dict[str, Any],
    filename: str,
    file_bytes: bytes,
    purpose: str | None = None,
) -> dict[str, Any]:
    """POST a file to an OpenAI-style Files endpoint when the provider supports it."""

    settings = resolve_settings(config)
    endpoint = upload_url(settings)
    if not endpoint:
        raise LLMClientError(
            f"{provider_label(settings)} does not expose a file upload endpoint. "
            "The frontend will extract the document text locally instead."
        )
    auth_style = str(settings.get("auth_style") or "bearer")
    api_key = str(settings.get("api_key") or "").strip()
    if auth_style != "none" and not api_key:
        raise LLMClientError(f"No API key configured for {provider_label(settings)}.")
    headers: dict[str, str] = {}
    if auth_style == "x-api-key":
        headers["x-api-key"] = api_key
    elif auth_style == "bearer":
        headers["Authorization"] = f"Bearer {api_key}"
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    payload_data = {
        "purpose": purpose or str(settings.get("upload_purpose") or "assistants")
    }
    timeout = int(settings.get("timeout_seconds") or 120)
    try:
        response = requests.post(
            endpoint,
            headers=headers,
            data=payload_data,
            files={"file": (filename, file_bytes, mime_type)},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise LLMClientError(f"File upload failed: {exc}") from exc
    if response.status_code >= 400:
        raise LLMClientError(
            f"File upload returned HTTP {response.status_code}: {response.text[:1000]}"
        )
    try:
        data = response.json()
    except ValueError:
        data = {"text": response.text}
    return {"filename": filename, "status_code": response.status_code, "response": data}
