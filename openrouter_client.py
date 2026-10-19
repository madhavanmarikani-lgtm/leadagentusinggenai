"""Compatibility layer forwarding to nvidia_client."""

from __future__ import annotations

from nvidia_client import (
    DEFAULT_MODEL,
    FALLBACK_MODEL,
    NVIDIA_BASE_URL,
    call_nvidia_json,
    call_openrouter_json,
    extract_lead_intelligence_with_llm,
    parse_user_query_with_llm,
)

__all__ = [
    "DEFAULT_MODEL",
    "FALLBACK_MODEL",
    "NVIDIA_BASE_URL",
    "call_nvidia_json",
    "call_openrouter_json",
    "extract_lead_intelligence_with_llm",
    "parse_user_query_with_llm",
]
