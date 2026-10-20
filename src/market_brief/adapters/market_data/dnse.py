"""DNSE public chart adapter.

vnstock is quarantined on PyPI, so this adapter calls the DNSE chart API
with the standard library. Equity closes stay in thousands of VND. The
backend converts them to đồng when it accepts the crawl.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from dataclasses import dataclass

from market_brief.adapters.market_data.mapping import observation_from_candles
from market_brief.domain.models import Asset, Observation, Symbol
from market_brief.ports.market_data import MarketDataError

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
BASE_URL = "https://services.entrade.com.vn/chart-api/v2/ohlcs"
LOOKBACK = timedelta(days=45)
Fetch = Callable[[str], Mapping[str, object]]


@dataclass(frozen=True)
class DailyBar:
    symbol: Symbol
    observed_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | None


class DnseMarketData:
    name = "dnse"

    def __init__(self, fetch: Fetch | None = None, now: Callable[[], datetime] | None = None) -> None:
        self._fetch = fetch or _fetch_json
        self._now = now or (lambda: datetime.now(ICT))

    def fetch_observations(self, symbols: Sequence[Symbol]) -> Sequence[Observation]:
        end = self._now().astimezone(ICT)
        start = end - LOOKBACK
        observations: list[Observation] = []
        for symbol in symbols:
            payload = self._fetch(chart_url(symbol, start, end))
            observations.append(observation_from_candles(symbol, candles_from_payload(symbol, payload)))
        return observations

    def fetch_daily_bars(self, symbol: Symbol, start: datetime, end: datetime) -> tuple[DailyBar, ...]:
        return fetch_daily_bars(symbol, start, end, self._fetch)


def fetch_daily_bars(
    symbol: Symbol,
    start: datetime,
    end: datetime,
    fetch: Fetch,
) -> tuple[DailyBar, ...]:
    """Daily OHLC in DNSE's own units. Equity prices stay in thousands of VND."""
    window_start = start.astimezone(ICT)
    cursor_end = end.astimezone(ICT)
    found: dict[datetime, DailyBar] = {}
    for _ in range(10):
        payload = fetch(chart_url(symbol, window_start, cursor_end))
        for bar in ohlc_from_payload(symbol, payload):
            if bar.observed_at >= window_start:
                found[bar.observed_at] = bar
        nxt = payload.get("nextTime")
        if not isinstance(nxt, int | Decimal) or int(nxt) <= 0:
            break
        older = datetime.fromtimestamp(int(nxt), ICT)
        if older >= cursor_end or older < window_start:
            break
        cursor_end = older
    return tuple(sorted(found.values(), key=lambda bar: bar.observed_at))


def chart_url(symbol: Symbol, start: datetime, end: datetime) -> str:
    kind = "index" if symbol.asset is Asset.INDEX else "stock"
    if symbol.asset not in (Asset.INDEX, Asset.EQUITY):
        raise MarketDataError(f"{symbol.ticker}: loại tài sản '{symbol.asset.value}' chưa có adapter.")
    query = urllib.parse.urlencode(
        {
            "from": int(start.timestamp()),
            "to": int(end.timestamp()),
            "symbol": symbol.ticker,
            "resolution": "1D",
        }
    )
    return f"{BASE_URL}/{kind}?{query}"


def candles_from_payload(symbol: Symbol, payload: Mapping[str, object]) -> list[dict[str, object]]:
    times = payload.get("t")
    closes = payload.get("c")
    volumes = payload.get("v")
    if not isinstance(times, list) or not isinstance(closes, list) or len(times) != len(closes) or not times:
        raise MarketDataError(f"{symbol.ticker}: DNSE không trả nến.")
    if volumes is not None and (not isinstance(volumes, list) or len(volumes) != len(times)):
        raise MarketDataError(f"{symbol.ticker}: DNSE trả khối lượng không khớp số nến.")
    rows: list[dict[str, object]] = []
    for index, stamp in enumerate(times):
        volume = None if not isinstance(volumes, list) else volumes[index]
        rows.append(
            {
                "time": datetime.fromtimestamp(int(str(stamp)), ICT),
                "close": closes[index],
                "volume": volume,
            }
        )
    return rows


def ohlc_from_payload(symbol: Symbol, payload: Mapping[str, object]) -> tuple[DailyBar, ...]:
    times = payload.get("t")
    opens = payload.get("o")
    highs = payload.get("h")
    lows = payload.get("l")
    closes = payload.get("c")
    volumes = payload.get("v")
    series = (times, opens, highs, lows, closes)
    if any(not isinstance(column, list) for column in series) or not times:
        raise MarketDataError(f"{symbol.ticker}: DNSE không trả nến OHLC.")
    width = len(times)
    if any(len(column) != width for column in series):
        raise MarketDataError(f"{symbol.ticker}: DNSE trả OHLC không khớp số nến.")
    if volumes is not None and (not isinstance(volumes, list) or len(volumes) != width):
        raise MarketDataError(f"{symbol.ticker}: DNSE trả khối lượng không khớp số nến.")
    rows: list[DailyBar] = []
    for index, stamp in enumerate(times):
        volume = None if not isinstance(volumes, list) else _whole(volumes[index])
        rows.append(
            DailyBar(
                symbol=symbol,
                observed_at=datetime.fromtimestamp(int(str(stamp)), ICT),
                open=_number(symbol, opens[index], "giá mở cửa"),
                high=_number(symbol, highs[index], "giá cao nhất"),
                low=_number(symbol, lows[index], "giá thấp nhất"),
                close=_number(symbol, closes[index], "giá đóng cửa"),
                volume=volume,
            )
        )
    return tuple(rows)


def _number(symbol: Symbol, raw: object, label: str) -> Decimal:
    if raw is None or raw == "":
        raise MarketDataError(f"{symbol.ticker}: DNSE thiếu {label}.")
    try:
        return Decimal(str(raw))
    except Exception as exc:
        raise MarketDataError(f"{symbol.ticker}: DNSE {label} không đọc được.") from exc


def _whole(raw: object) -> int | None:
    if raw is None:
        return None
    return int(Decimal(str(raw)))


def _fetch_json(url: str) -> Mapping[str, object]:
    request = urllib.request.Request(url, headers={"User-Agent": "market-brief", "Accept": "application/json"})
    ticker = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("symbol", ["mã"])[0]
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise MarketDataError(f"{ticker}: DNSE trả HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise MarketDataError(f"{ticker}: không gọi được DNSE ({exc.reason}).") from exc
    try:
        payload = json.loads(raw.decode("utf-8"), parse_float=Decimal)
    except json.JSONDecodeError as exc:
        raise MarketDataError(f"{ticker}: DNSE trả JSON không đọc được.") from exc
    if not isinstance(payload, dict):
        raise MarketDataError(f"{ticker}: DNSE trả về không phải object.")
    return payload
