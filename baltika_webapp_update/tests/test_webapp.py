"""Проверка подписи initData для Telegram Mini App."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from urllib.parse import urlencode

from app.webapp import parse_settings, verify_init_data

TOKEN = "123456:TEST_TOKEN"
NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


def make_init(user_id: int = 42, auth_date: int | None = None, token: str = TOKEN) -> str:
    """Собирает initData так же, как это делает Telegram."""
    auth_date = auth_date if auth_date is not None else int(NOW.timestamp())
    fields = {
        "auth_date": str(auth_date),
        "query_id": "AAH",
        "user": json.dumps({"id": user_id, "first_name": "Вла"}, ensure_ascii=False),
    }
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_valid_signature_returns_user_id():
    assert verify_init_data(make_init(42), TOKEN, now=NOW) == 42


def test_wrong_token_rejected():
    assert verify_init_data(make_init(42), "999:OTHER", now=NOW) is None


def test_tampered_user_rejected():
    init = make_init(42)
    tampered = init.replace("%22id%22%3A+42", "%22id%22%3A+43")
    assert tampered != init, "подмена не сработала — тест бы прошёл вхолостую"
    assert verify_init_data(tampered, TOKEN, now=NOW) is None


def test_expired_rejected():
    old = int(NOW.timestamp()) - 2 * 24 * 3600
    assert verify_init_data(make_init(42, auth_date=old), TOKEN, now=NOW) is None


def test_missing_hash_rejected():
    assert verify_init_data("auth_date=1&user=%7B%7D", TOKEN, now=NOW) is None


def test_empty_inputs_rejected():
    assert verify_init_data("", TOKEN, now=NOW) is None
    assert verify_init_data(make_init(42), "", now=NOW) is None


def test_settings_keeps_only_known_bool_fields():
    assert parse_settings({"autoclean": True}) == {"autoclean": True}
    assert parse_settings({"hack": 1, "beer_enabled": False}) == {"beer_enabled": False}


def test_settings_rejects_bad_input():
    assert parse_settings({"autoclean": "yes"}) is None      # не bool
    assert parse_settings({"hack": 1}) is None               # только чужие ключи
    assert parse_settings({}) is None
    assert parse_settings(["autoclean"]) is None             # не объект
