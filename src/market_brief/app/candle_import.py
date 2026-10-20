"""Read a DNSE candle CSV and hand it to the backend in batches."""

import csv
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from market_brief.app.errors import ConfigError
from market_brief.domain.models import Asset, CandleObservation, PriceUnit, Symbol

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
BATCH_SIZE = 2000


def load_candle_csv(path: Path) -> tuple[tuple[CandleObservation, ...], int]:
    """One bar per ticker and ICT session. A later print on the same day replaces the earlier one."""
    if not path.is_file():
        raise ConfigError(f"Không thấy file nến {path}.")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = [_candle(row, line) for line, row in enumerate(csv.DictReader(handle), start=2)]
    return _one_bar_per_session(rows)


def iter_candle_batches(
    candles: tuple[CandleObservation, ...],
    batch_size: int = BATCH_SIZE,
) -> Iterator[tuple[CandleObservation, ...]]:
    for start in range(0, len(candles), batch_size):
        yield candles[start : start + batch_size]


def _one_bar_per_session(rows: list[CandleObservation]) -> tuple[tuple[CandleObservation, ...], int]:
    chosen: dict[tuple[str, str, object], CandleObservation] = {}
    order: list[tuple[str, str, object]] = []
    replaced = 0
    for candle in rows:
        session = candle.as_of.astimezone(ICT).date()
        key = (candle.symbol.ticker, candle.symbol.exchange, session)
        current = chosen.get(key)
        if current is None:
            chosen[key] = candle
            order.append(key)
            continue
        replaced += 1
        if candle.as_of >= current.as_of:
            chosen[key] = candle
    return tuple(chosen[key] for key in order), replaced


def _candle(row: dict[str, str], line: int) -> CandleObservation:
    ticker = _cell(row, "ticker", line).upper()
    asset = _asset(_cell(row, "asset", line), line)
    volume = _cell(row, "volume", line, required=False)
    return CandleObservation(
        symbol=Symbol(
            ticker=ticker,
            name=_cell(row, "name", line),
            exchange=_cell(row, "exchange", line),
            asset=asset,
            price_unit=PriceUnit.POINT if asset is Asset.INDEX else PriceUnit.VND,
        ),
        open=_decimal(row, "open", line),
        high=_decimal(row, "high", line),
        low=_decimal(row, "low", line),
        close=_decimal(row, "close", line),
        volume=None if volume == "" else int(volume),
        as_of=datetime.fromisoformat(_cell(row, "observed_at", line)),
    )


def _asset(value: str, line: int) -> Asset:
    try:
        return Asset(value)
    except ValueError as exc:
        raise ConfigError(f"Dòng {line}: asset '{value}' không hợp lệ.") from exc


def _decimal(row: dict[str, str], key: str, line: int) -> Decimal:
    text = _cell(row, key, line)
    try:
        return Decimal(text)
    except Exception as exc:
        raise ConfigError(f"Dòng {line}: cột {key} không đọc được.") from exc


def _cell(row: dict[str, str], key: str, line: int, required: bool = True) -> str:
    value = (row.get(key) or "").strip()
    if required and not value:
        raise ConfigError(f"Dòng {line}: thiếu cột {key}.")
    return value
