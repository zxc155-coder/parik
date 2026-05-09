"""Validate Telegram WebApp `initData` per the official spec.

Spec: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import parse_qsl


def parse_init_data(init_data: str) -> dict[str, str]:
    """Return dict of parsed init data (still URL-encoded)."""
    return dict(parse_qsl(init_data, keep_blank_values=True))


def validate_init_data(init_data: str, bot_token: str, max_age: int = 86400) -> dict[str, Any]:
    """Verify the WebApp init data signature.

    Returns the parsed dict (with `user` json-decoded) if valid.
    Raises ValueError otherwise.
    """
    if not init_data:
        raise ValueError("empty init_data")

    parsed = parse_init_data(init_data)
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise ValueError("missing hash")

    # Build data_check_string: sorted "key=value\n..."
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))

    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise ValueError("invalid hash")

    # Check auth_date freshness if present
    if "auth_date" in parsed:
        try:
            auth_date = int(parsed["auth_date"])
        except (TypeError, ValueError) as e:
            raise ValueError("invalid auth_date") from e
        if max_age and (time.time() - auth_date) > max_age:
            raise ValueError("init_data expired")

    out: dict[str, Any] = dict(parsed)
    if "user" in out:
        try:
            out["user"] = json.loads(out["user"])
        except json.JSONDecodeError:
            pass
    return out
