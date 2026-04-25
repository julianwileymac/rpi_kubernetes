"""Unit tests that exercise the client end-to-end against a mocked transport."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from alphavantage_client import AlphaVantageClient, RateLimitError, RateLimitKind
from alphavantage_client._errors import classify_payload


@pytest.fixture
def token_file(tmp_path: Path) -> Path:
    path = tmp_path / "av.key"
    path.write_text("demo-key\n", encoding="utf-8")
    return path


@pytest.fixture
def client(token_file: Path) -> AlphaVantageClient:
    client = AlphaVantageClient(
        api_key_file=str(token_file),
        rate_limit_rpm=600,
        daily_limit=0,
        cache_backend="memory",
    )
    yield client
    client.close()


@respx.mock
def test_global_quote_roundtrip(client: AlphaVantageClient) -> None:
    respx.get("https://www.alphavantage.co/query").mock(
        return_value=httpx.Response(
            200,
            json={
                "Global Quote": {
                    "01. symbol": "IBM",
                    "02. open": "250.12",
                    "05. price": "251.50",
                    "06. volume": "1234567",
                    "07. latest trading day": "2026-04-23",
                    "09. change": "1.38",
                    "10. change percent": "0.55%",
                }
            },
        )
    )
    quote = client.timeseries.global_quote("IBM")
    assert quote.symbol == "IBM"
    assert quote.price == pytest.approx(251.50)
    assert quote.volume == pytest.approx(1234567)


@respx.mock
def test_rate_limit_raised_on_note(client: AlphaVantageClient) -> None:
    respx.get("https://www.alphavantage.co/query").mock(
        return_value=httpx.Response(
            200,
            json={
                "Note": (
                    "Thank you for using Alpha Vantage! Our standard API rate limit is 25 "
                    "requests per day."
                )
            },
        )
    )
    with pytest.raises(RateLimitError) as excinfo:
        client.timeseries.global_quote("IBM")
    assert excinfo.value.kind == RateLimitKind.DAILY


def test_classify_empty_ok() -> None:
    assert classify_payload({"Global Quote": {}}) is None


def test_classify_info_rpm() -> None:
    err = classify_payload({"Information": "Our standard API call frequency is 5 calls per minute."})
    assert isinstance(err, RateLimitError)
    assert err.kind == RateLimitKind.RPM


def test_rate_limiter_snapshot(client: AlphaVantageClient) -> None:
    snap = client.rate_limiter.snapshot()
    assert snap.rpm_limit == 600
    assert snap.requests_this_minute == 0
