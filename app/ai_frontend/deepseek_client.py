"""Backwards-compatible alias for :mod:`app.ai_frontend.llm_client`.

DeepSeek was the first provider supported by this project, so the module name
is kept as a thin shim. New code should import ``llm_client`` directly.
"""

from __future__ import annotations

import requests  # noqa: F401  (re-exported for backwards compatibility)

from app.ai_frontend.llm_client import (  # noqa: F401
    LLMClientError,
    build_request,
    chat_url,
    parse_response,
    resolve_settings,
    send_chat,
    supports_upload,
    test_connection,
    upload_file,
    upload_url,
)

# The original exception name expected by earlier code and tests.
DeepSeekClientError = LLMClientError

__all__ = [
    "DeepSeekClientError",
    "LLMClientError",
    "build_request",
    "chat_url",
    "parse_response",
    "resolve_settings",
    "send_chat",
    "supports_upload",
    "test_connection",
    "upload_file",
    "upload_url",
]
