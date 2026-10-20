"""Map source payloads into observations. Prices stay in the source's own unit."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from math import isnan

from market_brief.domain.models import Observation, Symbol
from market_brief.ports.market_data import MarketDataError


def observation_from_candles(symbol: Symbol, rows: Sequence[Mapping[str, object]]) -> Observation:
    if not rows:
        raise MarketDataError(f"{symbol.ticker}: nguồn không trả nến.")
    ordered = sorted(rows, key=lambda row: _as_datetime(row["time"]))
    last = ordered[-1]
    previous = ordered[-2] if len(ordered) > 1 else None
    return Observation(
        symbol=symbol,
        price=_decimal(symbol.ticker, last.get("close"), "giá đóng cửa"),
        previous_price=None if previous is None else _decimal(symbol.ticker, previous.get("close"), "giá đóng cửa"),
        change_percent=None,
        volume=_volume(last.get("volume")),
        as_of=_as_datetime(last["time"]),
    )


def _decimal(ticker: str, raw: object, label: str) -> Decimal:
    if raw is None:
        raise MarketDataError(f"{ticker}: thiếu {label}.")
    if isinstance(raw, float) and isnan(raw):
        raise MarketDataError(f"{ticker}: thiếu {label}.")
    try:
        return Decimal(str(raw))
    except Exception as exc:
        raise MarketDataError(f"{ticker}: {label} không đọc được ({raw}).") from exc


def _volume(raw: object) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, float) and isnan(raw):
        return None
    return int(raw)


def _as_datetime(raw: object) -> datetime:
    if isinstance(raw, datetime):
        return raw
    return datetime.fromisoformat(str(raw))
