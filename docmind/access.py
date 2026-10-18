"""Hosted-deployment owner-key access (no Streamlit imports).

The UI passes ``st.secrets`` (or any mapping) in. On a hosted deployment the owner can put
``ANTHROPIC_API_KEY`` and ``ACCESS_CODE`` in the platform secrets; visitors who enter the access
code may use the owner's key for a capped number of Live requests per session. No returned string
ever contains a key.
"""
from __future__ import annotations

import hmac
import os
from collections.abc import Mapping
from typing import Any, Literal

LIVE_REQUEST_CAP = 20

ACCESS_GRANTED_MESSAGE = "Access code accepted — Live mode can use the owner's API key."
ACCESS_DENIED_MESSAGE = "That access code is not correct. You can paste your own API key or use Demo mode."
CAP_REACHED_MESSAGE = (
    f"You've used all {LIVE_REQUEST_CAP} Live requests for this session. "
    "Paste your own Anthropic API key to keep using Live mode — answered in Demo mode for now."
)

KeySource = Literal["user", "owner", "env"]


def _get(secrets: Any, name: str) -> str:
    """Read a secret safely; st.secrets may raise if no secrets file exists."""
    if secrets is None:
        return ""
    try:
        value = secrets.get(name) if hasattr(secrets, "get") else secrets[name]
    except Exception:  # missing file / missing key: treat as not configured
        return ""
    return value.strip() if isinstance(value, str) else ""


def owner_access_configured(secrets: Mapping[str, Any] | Any) -> bool:
    """True when both ANTHROPIC_API_KEY and ACCESS_CODE are non-empty in ``secrets``."""
    return bool(_get(secrets, "ANTHROPIC_API_KEY")) and bool(_get(secrets, "ACCESS_CODE"))


def check_access_code(secrets: Mapping[str, Any] | Any, entered: str | None) -> bool:
    """Constant-time comparison of the entered code with ``ACCESS_CODE``."""
    if not owner_access_configured(secrets):
        return False
    entered = (entered or "").strip()
    if not entered:
        return False
    return hmac.compare_digest(entered.encode("utf-8"), _get(secrets, "ACCESS_CODE").encode("utf-8"))


def resolve_key_source(secrets: Mapping[str, Any] | Any, user_key: str | None, unlocked: bool,
                       env: Mapping[str, str] | None = None) -> KeySource | None:
    """Which key resolve_key would use: user-pasted > owner (if unlocked) > env var."""
    env = os.environ if env is None else env
    if (user_key or "").strip():
        return "user"
    if unlocked and owner_access_configured(secrets):
        return "owner"
    if (env.get("ANTHROPIC_API_KEY") or "").strip():
        return "env"
    return None


def resolve_key(secrets: Mapping[str, Any] | Any, user_key: str | None, unlocked: bool,
                env: Mapping[str, str] | None = None) -> str | None:
    """Return the API key to use, or None. Priority: user key > owner key if unlocked > env."""
    env = os.environ if env is None else env
    source = resolve_key_source(secrets, user_key, unlocked, env)
    if source == "user":
        return (user_key or "").strip()
    if source == "owner":
        return _get(secrets, "ANTHROPIC_API_KEY")
    if source == "env":
        return (env.get("ANTHROPIC_API_KEY") or "").strip()
    return None


def can_make_live_request(count: int) -> bool:
    """True while fewer than LIVE_REQUEST_CAP owner-key Live requests were made this session."""
    return count < LIVE_REQUEST_CAP


def next_count(count: int) -> int:
    return count + 1


def cap_message() -> str:
    return CAP_REACHED_MESSAGE
