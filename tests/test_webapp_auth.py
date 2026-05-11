import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from app.webapp.auth import validate_init_data


def _make_init_data(bot_token: str, params: dict) -> str:
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    sig = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    payload = dict(params)
    payload["hash"] = sig
    return urlencode(payload)


def test_valid_init_data_returns_user():
    bot_token = "123456:ABCDEF"
    user = {"id": 42, "first_name": "Alice"}
    params = {
        "auth_date": str(int(time.time())),
        "query_id": "AAH",
        "user": json.dumps(user, separators=(",", ":")),
    }
    init_data = _make_init_data(bot_token, params)
    out = validate_init_data(init_data, bot_token)
    assert out["user"]["id"] == 42


def test_invalid_hash_rejected():
    bot_token = "123456:ABCDEF"
    params = {
        "auth_date": str(int(time.time())),
        "query_id": "x",
        "user": json.dumps({"id": 1}, separators=(",", ":")),
    }
    init_data = _make_init_data(bot_token, params)
    # Tamper with the user
    init_data = init_data.replace("%22id%22%3A1", "%22id%22%3A2")
    with pytest.raises(ValueError):
        validate_init_data(init_data, bot_token)


def test_expired_init_data_rejected():
    bot_token = "123456:ABCDEF"
    params = {
        "auth_date": str(int(time.time()) - 200000),
        "query_id": "old",
        "user": json.dumps({"id": 1}, separators=(",", ":")),
    }
    init_data = _make_init_data(bot_token, params)
    with pytest.raises(ValueError, match="expired"):
        validate_init_data(init_data, bot_token, max_age=86400)


def test_missing_hash_rejected():
    with pytest.raises(ValueError):
        validate_init_data("auth_date=12345&user=%7B%7D", "token")


def test_empty_init_data_rejected():
    with pytest.raises(ValueError):
        validate_init_data("", "token")
