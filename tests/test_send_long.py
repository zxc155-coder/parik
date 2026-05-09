"""Tests for _send_long: HTML parse-mode fallback and chunked splitting."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from aiogram.exceptions import TelegramBadRequest

from app.bot.handlers import _send_long


class FakeMessage:
    """Records calls to .answer() and fails any call that did not explicitly
    override parse_mode (i.e. simulates a default-HTML bot rejecting unbalanced
    angle brackets)."""

    def __init__(self, fail_default_parse_mode: bool = False) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._fail_default = fail_default_parse_mode

    async def answer(self, text: str, **kwargs: Any) -> None:
        self.calls.append((text, kwargs))
        if self._fail_default and "parse_mode" not in kwargs:
            raise TelegramBadRequest(
                method=type("M", (), {"__api_method__": "sendMessage"})(),  # type: ignore[arg-type]
                message="can't parse entities",
            )


@pytest.mark.asyncio
async def test_send_long_short_text_no_failure():
    msg = FakeMessage()
    await _send_long(msg, "hi")  # type: ignore[arg-type]
    assert len(msg.calls) == 1
    assert msg.calls[0][0] == "hi"


@pytest.mark.asyncio
async def test_send_long_falls_back_when_html_parse_fails():
    """When the default HTML parser rejects the text, retry with parse_mode=None."""
    msg = FakeMessage(fail_default_parse_mode=True)
    await _send_long(msg, "x < y && z > 0")  # type: ignore[arg-type]
    # Two attempts: first without parse_mode override, second with parse_mode=None
    assert len(msg.calls) == 2
    assert msg.calls[0][1] == {}
    assert msg.calls[1][1] == {"parse_mode": None}


@pytest.mark.asyncio
async def test_send_long_splits_long_text_into_chunks():
    big = "a" * 9500  # > 2 chunks of 4000
    msg = FakeMessage()
    await _send_long(msg, big)  # type: ignore[arg-type]
    # Expected chunks: 4000, 4000, 1500
    assert [len(c[0]) for c in msg.calls] == [4000, 4000, 1500]


@pytest.mark.asyncio
async def test_send_long_falls_back_per_chunk():
    """Even in chunked mode, each chunk that fails HTML parsing should retry."""
    big = "a" * 5000  # 2 chunks
    msg = FakeMessage(fail_default_parse_mode=True)
    await _send_long(msg, big)  # type: ignore[arg-type]
    # 2 chunks * 2 attempts each = 4 calls
    assert len(msg.calls) == 4
    assert msg.calls[1][1] == {"parse_mode": None}
    assert msg.calls[3][1] == {"parse_mode": None}


def test_event_loop_marker():
    """Sanity check that pytest-asyncio is configured correctly."""
    asyncio.get_event_loop_policy()
