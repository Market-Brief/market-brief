"""Write crawled DNSE daily bars to CSV. Prices stay in the source unit."""

import csv
from collections.abc import Sequence
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from market_brief.adapters.market_data.dnse import DnseMarketData, DailyBar
from market_brief.domain.models import Asset, Symbol

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
COLUMNS = (
    "ticker",
    "name",
    "exchange",
    "asset",
    "native_unit",
    "session_date",
    "observed_at",
    "open",
    "high",
    "low",
    "close",
    "volume",
)


def crawl_daily_csv(symbols: Sequence[Symbol], years: int, destination: Path, now: datetime | None = None) -> int:
    end = (now or datetime.now(ICT)).astimezone(ICT)
    start = datetime.combine(end.date().replace(year=end.year - years), time.min, tzinfo=ICT)
    market = DnseMarketData(now=lambda: end)
    rows: list[DailyBar] = []
    for symbol in symbols:
        rows.extend(market.fetch_daily_bars(symbol, start, end))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for bar in rows:
            writer.writerow(_row(bar))
    return len(rows)


def _row(bar: DailyBar) -> dict[str, str]:
    observed = bar.observed_at.astimezone(ICT)
    return {
        "ticker": bar.symbol.ticker,
        "name": bar.symbol.name,
        "exchange": bar.symbol.exchange,
        "asset": bar.symbol.asset.value,
        "native_unit": "point" if bar.symbol.asset is Asset.INDEX else "thousand_vnd",
        "session_date": observed.date().isoformat(),
        "observed_at": observed.isoformat(),
        "open": format(bar.open, "f"),
        "high": format(bar.high, "f"),
        "low": format(bar.low, "f"),
        "close": format(bar.close, "f"),
        "volume": "" if bar.volume is None else str(bar.volume),
    }
