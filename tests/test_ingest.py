import hashlib
import hmac
import io
import json
import urllib.error
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from market_brief.adapters.ingest.api import ApiIngest
from market_brief.app.errors import ConfigError, IngestError
from market_brief.domain.models import Asset, CandleObservation, Observation, PriceUnit, Symbol

ICT = ZoneInfo("Asia/Ho_Chi_Minh")


def _observation() -> Observation:
    return Observation(
        symbol=Symbol("VCB", "Vietcombank", "HOSE", Asset.EQUITY, PriceUnit.VND),
        price=Decimal("56.2"),
        previous_price=Decimal("57.3"),
        change_percent=None,
        volume=100,
        as_of=datetime(2026, 10, 20, 15, 0, tzinfo=ICT),
    )


def test_accept_posts_native_prices_and_reads_the_backend_quote() -> None:
    sent: dict[str, object] = {}

    def send(url: str, payload: bytes, timestamp: str, signature: str) -> tuple[int, bytes]:
        sent["url"] = url
        sent["timestamp"] = timestamp
        sent["signature"] = signature
        sent["body"] = json.loads(payload.decode("utf-8"))
        message = f"{timestamp}\n".encode() + payload
        sent["expected"] = hmac.new(b"local-key", message, hashlib.sha256).hexdigest()
        return 200, json.dumps(
            {
                "source": "dnse",
                "quotes": [
                    {
                        "ticker": "VCB",
                        "name": "Vietcombank",
                        "exchange": "HOSE",
                        "asset": "equity",
                        "price_unit": "vnd",
                        "price": "56200",
                        "change_percent": "-1.92",
                        "volume": 100,
                        "observed_at": "2026-10-20T15:00:00+07:00",
                    }
                ],
            }
        ).encode("utf-8")

    quotes = ApiIngest("http://127.0.0.1:8080", "local-key", send).accept("dnse", [_observation()])
    assert sent["url"] == "http://127.0.0.1:8080/ingest/quotes"
    assert sent["signature"] == sent["expected"]
    assert "local-key" not in sent["signature"]
    body = sent["body"]
    assert isinstance(body, dict)
    assert body["observations"][0]["price"] == "56.2"
    assert body["observations"][0]["previous_price"] == "57.3"
    assert quotes[0].price == Decimal("56200")
    assert quotes[0].change_percent == Decimal("-1.92")
    assert quotes[0].source == "dnse"


def test_accept_candles_posts_native_ohlc() -> None:
    sent: dict[str, object] = {}

    def send(url: str, payload: bytes, timestamp: str, signature: str) -> tuple[int, bytes]:
        sent["url"] = url
        sent["body"] = json.loads(payload.decode("utf-8"))
        return 200, b'{"source":"dnse","accepted":1}'

    candle = CandleObservation(
        symbol=Symbol("VCB", "Vietcombank", "HOSE", Asset.EQUITY, PriceUnit.VND),
        open=Decimal("41.02"),
        high=Decimal("41.02"),
        low=Decimal("40.58"),
        close=Decimal("40.71"),
        volume=240000,
        as_of=datetime(2021, 10, 20, 9, 0, tzinfo=ICT),
    )
    accepted = ApiIngest("http://127.0.0.1:8080", "local-key", send).accept_candles("dnse", [candle])
    assert accepted == 1
    assert sent["url"] == "http://127.0.0.1:8080/ingest/candles"
    body = sent["body"]
    assert isinstance(body, dict)
    assert body["candles"][0]["open"] == "41.02"
    assert body["candles"][0]["close"] == "40.71"


def test_rejected_batch_uses_the_backend_detail() -> None:
    def send(url: str, payload: bytes, timestamp: str, signature: str) -> tuple[int, bytes]:
        raise urllib.error.HTTPError(url, 422, "no", hdrs=None, fp=io.BytesIO(b'{"detail":"VCB: gia phai lon hon 0."}'))

    try:
        ApiIngest("http://127.0.0.1:8080", "local-key", send).accept("dnse", [_observation()])
    except IngestError as exc:
        assert "VCB" in str(exc)
    else:
        raise AssertionError("expected IngestError")


def test_missing_key_is_configuration() -> None:
    try:
        ApiIngest("http://127.0.0.1:8080", "").accept("dnse", [_observation()])
    except ConfigError as exc:
        assert "INGEST_KEY" in str(exc)
    else:
        raise AssertionError("expected ConfigError")
