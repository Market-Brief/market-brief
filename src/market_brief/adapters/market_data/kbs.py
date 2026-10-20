"""KB Securities price board. Equities are the live match; indexes use today's daily bar."""

import urllib.parse
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from market_brief.adapters.market_data.http import request_json
from market_brief.domain.models import Asset, Observation, Symbol
from market_brief.ports.market_data import MarketDataError

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
BASE_URL = "https://kbbuddywts.kbsec.com.vn/iis-server/investment"
BOARD_URL = f"{BASE_URL}/stock/iss"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "market-brief",
    "x-lang": "vi",
}
Fetch = Callable[[str, Mapping[str, object] | None], object]


class KbsMarketData:
    name = "kbs"

    def __init__(self, fetch: Fetch | None = None, now: Callable[[], datetime] | None = None) -> None:
        self._fetch = fetch or (lambda url, payload=None: request_json(url, payload, "KBS", HEADERS))
        self._now = now or (lambda: datetime.now(ICT))

    def fetch_observations(self, symbols: Sequence[Symbol]) -> Sequence[Observation]:
        equities = [symbol for symbol in symbols if symbol.asset is Asset.EQUITY]
        indexes = [symbol for symbol in symbols if symbol.asset is Asset.INDEX]
        unknown = [symbol.ticker for symbol in symbols if symbol.asset not in (Asset.EQUITY, Asset.INDEX)]
        if unknown:
            raise MarketDataError(f"{unknown[0]}: loại tài sản chưa có adapter KBS.")
        found: dict[str, Observation] = {}
        if equities:
            payload = self._fetch(BOARD_URL, {"code": ",".join(symbol.ticker for symbol in equities)})
            found.update(_board_quotes(equities, payload, self._now()))
        for symbol in indexes:
            found[symbol.ticker] = _index_quote(symbol, self._fetch(_index_url(symbol, self._now()), None))
        return tuple(found[symbol.ticker] for symbol in symbols)


def _index_url(symbol: Symbol, now: datetime) -> str:
    end = now.astimezone(ICT).date()
    start = end - timedelta(days=20)
    query = urllib.parse.urlencode({"sdate": start.strftime("%d-%m-%Y"), "edate": end.strftime("%d-%m-%Y")})
    return f"{BASE_URL}/index/{symbol.ticker}/data_day?{query}"


def _board_quotes(symbols: Sequence[Symbol], payload: object, now: datetime) -> dict[str, Observation]:
    rows = _rows(payload)
    by_ticker = {symbol.ticker: symbol for symbol in symbols}
    found: dict[str, Observation] = {}
    for row in rows:
        ticker = row.get("SB")
        if not isinstance(ticker, str) or ticker not in by_ticker:
            continue
        symbol = by_ticker[ticker]
        if row.get("CP") is None:
            raise MarketDataError(f"{ticker}: KBS không có giá khớp.")
        price = _decimal(symbol, row.get("CP"), "giá khớp")
        change = row.get("CHP")
        percent = None if change is None else _decimal(symbol, change, "phần trăm")
        found[ticker] = Observation(
            symbol,
            price,
            None,
            percent,
            _volume(row.get("TT")),
            _millis(row.get("t"), now),
        )
    missing = [symbol.ticker for symbol in symbols if symbol.ticker not in found]
    if missing:
        raise MarketDataError(f"KBS không trả {', '.join(missing)}.")
    return found


def _index_quote(symbol: Symbol, payload: object) -> Observation:
    if not isinstance(payload, dict):
        raise MarketDataError(f"{symbol.ticker}: KBS không trả nến chỉ số.")
    rows = payload.get("data_day")
    if not isinstance(rows, list) or not rows:
        raise MarketDataError(f"{symbol.ticker}: KBS không trả nến chỉ số.")
    candles = [_candle(symbol, row) for row in rows if isinstance(row, dict)]
    candles.sort(key=lambda item: item[0])
    if not candles:
        raise MarketDataError(f"{symbol.ticker}: KBS không trả nến chỉ số.")
    as_of, price, volume = candles[-1]
    previous = candles[-2][1] if len(candles) > 1 else None
    return Observation(symbol, price, previous, None, volume, as_of)


def _candle(symbol: Symbol, row: Mapping[str, object]) -> tuple[datetime, Decimal, int | None]:
    raw_time = row.get("t")
    if not isinstance(raw_time, str):
        raise MarketDataError(f"{symbol.ticker}: KBS thiếu thời điểm nến.")
    as_of = datetime.strptime(raw_time, "%Y-%m-%d %H:%M").replace(tzinfo=ICT)
    return as_of, _decimal(symbol, row.get("c"), "điểm chỉ số"), _volume(row.get("v"))


def _rows(payload: object) -> list[Mapping[str, object]]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        payload = payload["data"]
    if not isinstance(payload, list):
        raise MarketDataError("KBS không trả bảng giá.")
    return [row for row in payload if isinstance(row, dict)]


def _decimal(symbol: Symbol, raw: object, label: str) -> Decimal:
    if raw is None or raw == "":
        raise MarketDataError(f"{symbol.ticker}: KBS thiếu {label}.")
    try:
        return Decimal(str(raw))
    except Exception as exc:
        raise MarketDataError(f"{symbol.ticker}: KBS {label} không đọc được.") from exc


def _volume(raw: object) -> int | None:
    if raw is None:
        return None
    return int(Decimal(str(raw)))


def _millis(raw: object, fallback: datetime) -> datetime:
    if isinstance(raw, int | float) and raw:
        return datetime.fromtimestamp(int(raw) / 1000, ICT)
    return fallback
