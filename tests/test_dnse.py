from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from market_brief.adapters.market_data.dnse import DnseMarketData, candles_from_payload, chart_url, fetch_daily_bars
from market_brief.domain.models import Asset, PriceUnit, Symbol
from market_brief.ports.market_data import MarketDataError

ICT = ZoneInfo("Asia/Ho_Chi_Minh")


def _equity() -> Symbol:
    return Symbol("VCB", "Vietcombank", "HOSE", Asset.EQUITY, PriceUnit.VND)


def test_chart_url_uses_stock_or_index_path() -> None:
    start = datetime(2026, 10, 1, tzinfo=ICT)
    end = datetime(2026, 10, 20, tzinfo=ICT)
    equity = chart_url(_equity(), start, end)
    index = chart_url(Symbol("VNINDEX", "VN-Index", "INDEX", Asset.INDEX, PriceUnit.POINT), start, end)
    assert "/ohlcs/stock?" in equity
    assert "symbol=VCB" in equity
    assert "/ohlcs/index?" in index
    assert "symbol=VNINDEX" in index


def test_fetch_observations_keeps_the_last_close_in_thousands() -> None:
    payload = {
        "t": [1792288800, 1792375200],
        "c": [Decimal("57.3"), Decimal("56.2")],
        "v": [100, 4165400],
    }

    def fetch(url: str) -> dict:
        assert "symbol=VCB" in url
        return payload

    observations = DnseMarketData(fetch=fetch, now=lambda: datetime(2026, 10, 20, 10, 0, tzinfo=ICT)).fetch_observations([_equity()])
    assert observations[0].price == Decimal("56.2")
    assert observations[0].previous_price == Decimal("57.3")
    assert observations[0].volume == 4165400
    assert observations[0].change_percent is None


def test_fetch_daily_bars_keeps_ohlc_in_source_units() -> None:
    payload = {
        "t": [1634850000, 1792486800],
        "o": [Decimal("41.02"), Decimal("58.0")],
        "h": [Decimal("41.02"), Decimal("58.5")],
        "l": [Decimal("40.58"), Decimal("57.4")],
        "c": [Decimal("40.71"), Decimal("57.9")],
        "v": [240000, Decimal("4165400")],
        "nextTime": 0,
    }
    bars = fetch_daily_bars(
        _equity(),
        datetime(2021, 10, 20, tzinfo=ICT),
        datetime(2026, 10, 20, 16, tzinfo=ICT),
        lambda url: payload,
    )
    assert len(bars) == 2
    assert bars[0].open == Decimal("41.02")
    assert bars[0].high == Decimal("41.02")
    assert bars[0].low == Decimal("40.58")
    assert bars[0].close == Decimal("40.71")
    assert bars[0].volume == 240000
    assert bars[1].volume == 4165400


def test_empty_payload_is_an_error() -> None:
    try:
        candles_from_payload(_equity(), {"t": [], "c": []})
    except MarketDataError as exc:
        assert "VCB" in str(exc)
    else:
        raise AssertionError("expected MarketDataError")
