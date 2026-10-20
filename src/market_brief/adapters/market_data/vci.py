"""Vietcap price board. Equities are the live match; indexes use today's daily bar."""

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from market_brief.adapters.market_data.http import request_json
from market_brief.domain.models import Asset, Observation, Symbol
from market_brief.ports.market_data import MarketDataError

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
BOARD_URL = "https://trading.vietcap.com.vn/api/price/symbols/getList"
CHART_URL = "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "market-brief",
    "Origin": "https://trading.vietcap.com.vn",
    "Referer": "https://trading.vietcap.com.vn/",
}
Fetch = Callable[[str, Mapping[str, object] | None], object]


class VciMarketData:
    name = "vci"

    def __init__(self, fetch: Fetch | None = None, now: Callable[[], datetime] | None = None) -> None:
        self._fetch = fetch or (lambda url, payload=None: request_json(url, payload, "VCI", HEADERS))
        self._now = now or (lambda: datetime.now(ICT))

    def fetch_observations(self, symbols: Sequence[Symbol]) -> Sequence[Observation]:
        equities = [symbol for symbol in symbols if symbol.asset is Asset.EQUITY]
        indexes = [symbol for symbol in symbols if symbol.asset is Asset.INDEX]
        unknown = [symbol.ticker for symbol in symbols if symbol.asset not in (Asset.EQUITY, Asset.INDEX)]
        if unknown:
            raise MarketDataError(f"{unknown[0]}: loại tài sản chưa có adapter VCI.")
        found: dict[str, Observation] = {}
        if equities:
            payload = self._fetch(BOARD_URL, {"symbols": [symbol.ticker for symbol in equities]})
            found.update(_board_quotes(equities, payload, self._now()))
        for symbol in indexes:
            found[symbol.ticker] = _index_quote(symbol, self._fetch(CHART_URL, _chart_body(symbol, self._now())))
        return tuple(found[symbol.ticker] for symbol in symbols)


def _chart_body(symbol: Symbol, now: datetime) -> dict[str, object]:
    return {
        "timeFrame": "ONE_DAY",
        "symbols": [symbol.ticker],
        "to": int(now.timestamp()) + 86_400,
        "countBack": 10,
    }


def _board_quotes(symbols: Sequence[Symbol], payload: object, now: datetime) -> dict[str, Observation]:
    if not isinstance(payload, list):
        raise MarketDataError("VCI không trả bảng giá.")
    by_ticker = {symbol.ticker: symbol for symbol in symbols}
    found: dict[str, Observation] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        listing = _mapping(item.get("listingInfo"))
        match = _mapping(item.get("matchPrice"))
        ticker = listing.get("symbol") or match.get("symbol")
        if not isinstance(ticker, str) or ticker not in by_ticker:
            continue
        symbol = by_ticker[ticker]
        price = _decimal(symbol, match.get("matchPrice"), "giá khớp")
        if price <= 0:
            raise MarketDataError(f"{ticker}: VCI không có giá khớp.")
        reference = _decimal(symbol, listing.get("refPrice"), "giá tham chiếu")
        found[ticker] = Observation(
            symbol,
            price,
            reference,
            None,
            _volume(match.get("accumulatedVolume")),
            _stamp(match.get("receivedTime"), now),
        )
    missing = [symbol.ticker for symbol in symbols if symbol.ticker not in found]
    if missing:
        raise MarketDataError(f"VCI không trả {', '.join(missing)}.")
    return found


def _index_quote(symbol: Symbol, payload: object) -> Observation:
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        raise MarketDataError(f"{symbol.ticker}: VCI không trả nến chỉ số.")
    item = payload[0]
    closes = item.get("c")
    times = item.get("t")
    volumes = item.get("v")
    if not isinstance(closes, list) or not isinstance(times, list) or not closes or len(closes) != len(times):
        raise MarketDataError(f"{symbol.ticker}: VCI không trả nến chỉ số.")
    price = _decimal(symbol, closes[-1], "điểm chỉ số")
    previous = None if len(closes) < 2 else _decimal(symbol, closes[-2], "điểm chỉ số")
    volume = None if not isinstance(volumes, list) or not volumes else _volume(volumes[-1])
    return Observation(
        symbol,
        price,
        previous,
        None,
        volume,
        datetime.fromtimestamp(int(str(times[-1])), ICT),
    )


def _decimal(symbol: Symbol, raw: object, label: str) -> Decimal:
    if raw is None or raw == "":
        raise MarketDataError(f"{symbol.ticker}: VCI thiếu {label}.")
    try:
        return Decimal(str(raw))
    except Exception as exc:
        raise MarketDataError(f"{symbol.ticker}: VCI {label} không đọc được.") from exc


def _volume(raw: object) -> int | None:
    if raw is None:
        return None
    return int(Decimal(str(raw)))


def _stamp(raw: object, fallback: datetime) -> datetime:
    if isinstance(raw, str) and raw:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(ICT)
    return fallback


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, dict):
        return value
    return {}
