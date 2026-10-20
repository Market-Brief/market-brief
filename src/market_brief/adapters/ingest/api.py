"""POST crawled observations to the .NET ingest endpoint."""

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from datetime import datetime
from decimal import Decimal

from market_brief.app.errors import ConfigError, IngestError
from market_brief.domain.models import Asset, CandleObservation, Observation, PriceUnit, Quote, Symbol

Send = Callable[[str, bytes, str, str], tuple[int, bytes]]


class ApiIngest:
    def __init__(self, base_url: str | None = None, key: str | None = None, send: Send | None = None) -> None:
        self._base_url = base_url
        self._key = key
        self._send = send or _send

    def accept(self, source: str, observations: Sequence[Observation]) -> tuple[Quote, ...]:
        base_url, key = self._settings()
        url = f"{base_url.rstrip('/')}/ingest/quotes"
        payload = _payload(source, observations)
        timestamp, signature = _sign(key, payload)
        try:
            status, raw = self._send(url, payload, timestamp, signature)
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise ConfigError("BE từ chối chữ ký ingest. Kiểm tra INGEST_KEY và đồng hồ máy.") from exc
            raise IngestError(_detail(exc)) from exc
        except urllib.error.URLError as exc:
            raise ConfigError(f"Không gọi được BE ({exc.reason}).") from exc
        if status != 200:
            raise IngestError(f"BE trả HTTP {status}.")
        return _quotes(source, raw)

    def accept_candles(self, source: str, candles: Sequence[CandleObservation]) -> int:
        base_url, key = self._settings()
        url = f"{base_url.rstrip('/')}/ingest/candles"
        payload = _candle_payload(source, candles)
        timestamp, signature = _sign(key, payload)
        try:
            status, raw = self._send(url, payload, timestamp, signature)
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise ConfigError("BE từ chối chữ ký ingest. Kiểm tra INGEST_KEY và đồng hồ máy.") from exc
            raise IngestError(_detail(exc)) from exc
        except urllib.error.URLError as exc:
            raise ConfigError(f"Không gọi được BE ({exc.reason}).") from exc
        if status != 200:
            raise IngestError(f"BE trả HTTP {status}.")
        return _accepted(raw)

    def _settings(self) -> tuple[str, str]:
        base_url = (self._base_url if self._base_url is not None else os.environ.get("INGEST_URL", "")).strip()
        key = (self._key if self._key is not None else os.environ.get("INGEST_KEY", "")).strip()
        if not base_url:
            base_url = "http://127.0.0.1:8080"
        if not key:
            raise ConfigError("INGEST_KEY cần khớp khóa của market-brief-api.")
        return base_url, key


def _payload(source: str, observations: Sequence[Observation]) -> bytes:
    body = {
        "source": source,
        "observations": [
            {
                "ticker": item.symbol.ticker,
                "name": item.symbol.name,
                "exchange": item.symbol.exchange,
                "asset": item.symbol.asset.value,
                "observed_at": item.as_of.isoformat(),
                "price": format(item.price, "f"),
                "previous_price": None if item.previous_price is None else format(item.previous_price, "f"),
                "change_percent": None if item.change_percent is None else format(item.change_percent, "f"),
                "volume": item.volume,
            }
            for item in observations
        ],
    }
    return json.dumps(body).encode("utf-8")


def _candle_payload(source: str, candles: Sequence[CandleObservation]) -> bytes:
    body = {
        "source": source,
        "candles": [
            {
                "ticker": item.symbol.ticker,
                "name": item.symbol.name,
                "exchange": item.symbol.exchange,
                "asset": item.symbol.asset.value,
                "observed_at": item.as_of.isoformat(),
                "open": format(item.open, "f"),
                "high": format(item.high, "f"),
                "low": format(item.low, "f"),
                "close": format(item.close, "f"),
                "volume": item.volume,
            }
            for item in candles
        ],
    }
    return json.dumps(body).encode("utf-8")


def _accepted(raw: bytes) -> int:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise IngestError("BE trả JSON không đọc được.") from exc
    accepted = payload.get("accepted") if isinstance(payload, dict) else None
    if not isinstance(accepted, int):
        raise IngestError("BE trả về không có số nến đã ghi.")
    return accepted


def _quotes(source: str, raw: bytes) -> tuple[Quote, ...]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise IngestError("BE trả JSON không đọc được.") from exc
    rows = payload.get("quotes") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise IngestError("BE trả về không có danh sách giá.")
    return tuple(_quote(source, row) for row in rows)


def _quote(source: str, row: object) -> Quote:
    if not isinstance(row, dict):
        raise IngestError("BE trả một dòng giá không đọc được.")
    change = row.get("change_percent")
    volume = row.get("volume")
    return Quote(
        symbol=Symbol(
            ticker=str(row["ticker"]),
            name=str(row["name"]),
            exchange=str(row["exchange"]),
            asset=Asset(str(row["asset"])),
            price_unit=PriceUnit(str(row["price_unit"])),
        ),
        price=Decimal(str(row["price"])),
        change_percent=None if change is None else Decimal(str(change)),
        volume=None if volume is None else int(volume),
        as_of=datetime.fromisoformat(str(row["observed_at"])),
        source=source,
    )


def _detail(exc: urllib.error.HTTPError) -> str:
    raw = exc.read().decode("utf-8", errors="replace")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return f"BE trả HTTP {exc.code}."
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, str) and detail.strip():
        return detail.strip()
    return f"BE trả HTTP {exc.code}."


def _sign(key: str, payload: bytes, timestamp: int | None = None) -> tuple[str, str]:
    stamp = int(time.time()) if timestamp is None else timestamp
    message = f"{stamp}\n".encode() + payload
    signature = hmac.new(key.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return str(stamp), signature


def _send(url: str, payload: bytes, timestamp: str, signature: str) -> tuple[int, bytes]:
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Ingest-Timestamp": timestamp,
            "X-Ingest-Signature": signature,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.status, response.read()
