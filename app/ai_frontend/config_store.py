"""Local configuration storage for the multi-provider AI frontend.

The configuration file is a single JSON document stored at
``app/data/ai_config.json`` (git-ignored). It holds shared request settings and
a per-provider block, so switching between GPT, Claude, DeepSeek, GLM, Qwen,
Moonshot, Ollama or a custom OpenAI-compatible gateway never loses API keys or
model choices.

Legacy single-provider files (the original DeepSeek-only format) are migrated
automatically on load.
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from app.ai_frontend import providers
from app.paths import data_path

DEFAULT_CONFIG_PATH = data_path("ai_config.json")

SHARED_DEFAULTS: dict[str, Any] = {
    "provider": providers.DEFAULT_PROVIDER_ID,
    "temperature": 0.2,
    "timeout_seconds": 120,
    "max_context_chars": 60000,
    "upload_purpose": "assistants",
    "providers": {},
}

PROVIDER_DEFAULTS: dict[str, Any] = {
    "api_key": "",
    "model": "",
    "base_url": "",
    "chat_path": "",
    "upload_endpoint": "",
}

DEFAULT_CONFIG: dict[str, Any] = {**SHARED_DEFAULTS, "providers": {}}


def _clean_str(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _migrate_legacy(stored: dict[str, Any]) -> dict[str, Any]:
    """Convert the original single-provider (DeepSeek) file into the new schema."""

    provider_id = providers.guess_provider_from_url(_clean_str(stored.get("base_url")))
    legacy_values = {
        "api_key": _clean_str(stored.get("api_key")),
        "model": _clean_str(stored.get("model")) or providers.get_provider(provider_id).default_model,
        "base_url": _clean_str(stored.get("base_url")),
        "chat_path": _clean_str(stored.get("chat_endpoint_path")),
        "upload_endpoint": _clean_str(stored.get("upload_endpoint")),
    }
    legacy_values = {key: value for key, value in legacy_values.items() if value}
    migrated: dict[str, Any] = {
        "provider": provider_id,
        "temperature": stored.get("temperature", SHARED_DEFAULTS["temperature"]),
        "timeout_seconds": stored.get("timeout_seconds", SHARED_DEFAULTS["timeout_seconds"]),
        "max_context_chars": stored.get("max_context_chars", SHARED_DEFAULTS["max_context_chars"]),
        "upload_purpose": _clean_str(stored.get("upload_purpose")) or SHARED_DEFAULTS["upload_purpose"],
        "providers": {provider_id: legacy_values},
    }
    return migrated


def load_config(path=None) -> dict[str, Any]:
    """Load configuration from disk, applying defaults and legacy migration."""

    target = path or DEFAULT_CONFIG_PATH
    config = deepcopy(DEFAULT_CONFIG)
    if not target.exists():
        return config
    try:
        stored = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return config
    if not isinstance(stored, dict):
        return config

    if "providers" not in stored and (
        "api_key" in stored or "base_url" in stored or "model" in stored
    ):
        stored = _migrate_legacy(stored)

    for key in SHARED_DEFAULTS:
        if key == "providers":
            continue
        if key in stored:
            config[key] = stored[key]
    raw_providers = stored.get("providers") or {}
    if isinstance(raw_providers, dict):
        config["providers"] = {
            str(provider_id): dict(values or {})
            for provider_id, values in raw_providers.items()
            if isinstance(values, dict)
        }
    if config.get("provider") not in providers.PROVIDERS:
        config["provider"] = providers.DEFAULT_PROVIDER_ID
    return config


def save_config(config: dict[str, Any], path=None) -> None:
    target = path or DEFAULT_CONFIG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "provider": config.get("provider") or providers.DEFAULT_PROVIDER_ID,
        "temperature": float(config.get("temperature", SHARED_DEFAULTS["temperature"])),
        "timeout_seconds": int(config.get("timeout_seconds", SHARED_DEFAULTS["timeout_seconds"])),
        "max_context_chars": int(config.get("max_context_chars", SHARED_DEFAULTS["max_context_chars"])),
        "upload_purpose": _clean_str(config.get("upload_purpose")) or SHARED_DEFAULTS["upload_purpose"],
        "providers": {
            str(provider_id): {
                key: values.get(key, PROVIDER_DEFAULTS[key])
                for key in PROVIDER_DEFAULTS
            }
            for provider_id, values in (config.get("providers") or {}).items()
            if isinstance(values, dict)
        },
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def provider_settings(config: dict[str, Any], provider_id: str | None = None) -> dict[str, Any]:
    """Merge provider defaults with the user's saved values for one provider."""

    selected = provider_id or str(config.get("provider") or providers.DEFAULT_PROVIDER_ID)
    spec = providers.get_provider(selected)
    stored = dict((config.get("providers") or {}).get(selected) or {})
    settings: dict[str, Any] = {
        "provider": spec.id,
        "provider_label": spec.label,
        "api_style": spec.api_style,
        "auth_style": spec.auth_style,
        "api_key": _clean_str(stored.get("api_key")),
        "model": _clean_str(stored.get("model")) or spec.default_model,
        "base_url": (_clean_str(stored.get("base_url")) or spec.base_url).rstrip("/"),
        "chat_path": _clean_str(stored.get("chat_path")) or spec.chat_path,
        "upload_endpoint": _clean_str(stored.get("upload_endpoint")),
        "upload_path": spec.upload_path,
        "upload_purpose": _clean_str(config.get("upload_purpose")) or SHARED_DEFAULTS["upload_purpose"],
        "temperature": float(config.get("temperature", SHARED_DEFAULTS["temperature"])),
        "timeout_seconds": int(config.get("timeout_seconds", SHARED_DEFAULTS["timeout_seconds"])),
        "max_context_chars": int(config.get("max_context_chars", SHARED_DEFAULTS["max_context_chars"])),
        "docs_url": spec.docs_url,
        "notes": spec.notes,
        "models": list(spec.models),
    }
    return settings


def update_provider(
    config: dict[str, Any],
    provider_id: str,
    values: dict[str, Any],
) -> dict[str, Any]:
    """Return a copy of ``config`` with one provider's values replaced."""

    updated = deepcopy(config)
    blocks = dict(updated.get("providers") or {})
    block = dict(blocks.get(provider_id) or {})
    for key, value in values.items():
        if key not in PROVIDER_DEFAULTS or value is None:
            continue
        text = _clean_str(value)
        block[key] = text
    blocks[provider_id] = block
    updated["providers"] = blocks
    return updated


def mask_api_key(api_key: str) -> str:
    if not api_key:
        return "(not set)"
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return api_key[:4] + "*" * max(4, len(api_key) - 8) + api_key[-4:]
