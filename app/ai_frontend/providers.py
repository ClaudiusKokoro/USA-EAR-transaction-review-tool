"""Registry of supported LLM providers.

Every provider is described declaratively so the frontend can render the
configuration form, build requests, and pick the right file-handling strategy
without hard-coding vendor logic in the UI.

Two API styles are supported:

* ``openai``    - OpenAI-compatible ``POST /chat/completions`` (OpenAI, DeepSeek,
                  GLM/Zhipu, Qwen/DashScope, Moonshot, Ollama, custom gateways).
* ``anthropic`` - Anthropic Messages API (``POST /messages``).

Model names change frequently; they are only *suggestions*. The UI always lets
the user type any model identifier.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    label: str
    api_style: str
    base_url: str
    chat_path: str
    auth_style: str  # "bearer" | "x-api-key" | "none"
    default_model: str
    models: tuple[str, ...] = field(default_factory=tuple)
    upload_path: str | None = None
    docs_url: str = ""
    notes: str = ""

    @property
    def supports_upload(self) -> bool:
        return bool(self.upload_path)


PROVIDERS: dict[str, ProviderSpec] = {
    "openai": ProviderSpec(
        id="openai",
        label="OpenAI (GPT)",
        api_style="openai",
        base_url="https://api.openai.com/v1",
        chat_path="/chat/completions",
        auth_style="bearer",
        default_model="gpt-4.1-mini",
        models=("gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini", "o4-mini"),
        upload_path="/files",
        docs_url="https://platform.openai.com/docs/api-reference/chat",
        notes="Requires an OpenAI API key. Supports the OpenAI Files API for uploads.",
    ),
    "anthropic": ProviderSpec(
        id="anthropic",
        label="Anthropic (Claude)",
        api_style="anthropic",
        base_url="https://api.anthropic.com/v1",
        chat_path="/messages",
        auth_style="x-api-key",
        default_model="claude-sonnet-4-5",
        models=(
            "claude-sonnet-4-5",
            "claude-opus-4-1",
            "claude-3-7-sonnet-latest",
            "claude-3-5-haiku-latest",
        ),
        docs_url="https://docs.anthropic.com/en/api/messages",
        notes="Uses the Anthropic Messages API (x-api-key header, anthropic-version).",
    ),
    "deepseek": ProviderSpec(
        id="deepseek",
        label="DeepSeek",
        api_style="openai",
        base_url="https://api.deepseek.com/v1",
        chat_path="/chat/completions",
        auth_style="bearer",
        default_model="deepseek-chat",
        models=("deepseek-chat", "deepseek-reasoner"),
        docs_url="https://api-docs.deepseek.com/",
        notes="OpenAI-compatible endpoint. File content is sent as extracted text.",
    ),
    "glm": ProviderSpec(
        id="glm",
        label="Zhipu GLM",
        api_style="openai",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        chat_path="/chat/completions",
        auth_style="bearer",
        default_model="glm-4.5",
        models=("glm-4.6", "glm-4.5", "glm-4-plus", "glm-4-flash"),
        docs_url="https://docs.bigmodel.cn/",
        notes="Zhipu AI (GLM) OpenAI-compatible endpoint.",
    ),
    "qwen": ProviderSpec(
        id="qwen",
        label="Qwen (DashScope)",
        api_style="openai",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        chat_path="/chat/completions",
        auth_style="bearer",
        default_model="qwen-plus",
        models=("qwen3-max", "qwen-max", "qwen-plus", "qwen-turbo"),
        docs_url="https://help.aliyun.com/zh/model-studio/",
        notes="Alibaba Cloud DashScope OpenAI-compatible mode.",
    ),
    "moonshot": ProviderSpec(
        id="moonshot",
        label="Moonshot (Kimi)",
        api_style="openai",
        base_url="https://api.moonshot.cn/v1",
        chat_path="/chat/completions",
        auth_style="bearer",
        default_model="moonshot-v1-32k",
        models=("kimi-k2-0905-preview", "moonshot-v1-8k", "moonshot-v1-32k"),
        docs_url="https://platform.moonshot.cn/docs",
        notes="OpenAI-compatible endpoint.",
    ),
    "ollama": ProviderSpec(
        id="ollama",
        label="Ollama (local)",
        api_style="openai",
        base_url="http://localhost:11434/v1",
        chat_path="/chat/completions",
        auth_style="none",
        default_model="llama3.1",
        models=("llama3.1", "qwen2.5", "mistral"),
        docs_url="https://github.com/ollama/ollama/blob/main/docs/openai.md",
        notes="Runs locally; no API key. Start Ollama before testing the connection.",
    ),
    "custom": ProviderSpec(
        id="custom",
        label="Custom (OpenAI-compatible)",
        api_style="openai",
        base_url="",
        chat_path="/chat/completions",
        auth_style="bearer",
        default_model="",
        models=(),
        upload_path=None,
        notes="Point this at any OpenAI-compatible gateway or corporate proxy.",
    ),
}

DEFAULT_PROVIDER_ID = "openai"

# Optional path used to POST uploads for providers that expose an OpenAI-style
# Files API. Providers without it fall back to local text extraction.
OPENAI_FILES_PATH = "/files"


def get_provider(provider_id: str | None) -> ProviderSpec:
    """Return the provider spec, falling back to the custom OpenAI-compatible one."""

    if provider_id and provider_id in PROVIDERS:
        return PROVIDERS[provider_id]
    return PROVIDERS["custom"]


def provider_ids() -> list[str]:
    return list(PROVIDERS)


def provider_labels() -> dict[str, str]:
    return {key: spec.label for key, spec in PROVIDERS.items()}


def guess_provider_from_url(base_url: str | None) -> str:
    """Best-effort detection used when migrating legacy single-provider configs."""

    url = (base_url or "").lower()
    if not url:
        return DEFAULT_PROVIDER_ID
    if "anthropic" in url:
        return "anthropic"
    if "deepseek" in url:
        return "deepseek"
    if "bigmodel" in url:
        return "glm"
    if "dashscope" in url or "aliyuncs" in url:
        return "qwen"
    if "moonshot" in url:
        return "moonshot"
    if "11434" in url or "localhost" in url:
        return "ollama"
    if "openai" in url:
        return "openai"
    return "custom"
