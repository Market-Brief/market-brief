from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from market_brief.adapters.market_data.vci import VciMarketData
from market_brief.domain.models import Asset, PriceUnit, Symbol
from market_brief.ports.market_data import MarketDataError

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
NOW = datetime(2026, 10, 20, 11, 50, tzinfo=ICT)


def _equity() -> Symbol:
    return Symbol("VCB", "Vietcombank", "HOSE", Asset.EQUITY, PriceUnit.VND)


def _index() -> Symbol:
    return Symbol("VNINDEX", "VN-Index", "INDEX", Asset.INDEX, PriceUnit.POINT)


def test_vci_keeps_match_price_in_dong_and_index_points() -> None:
    def fetch(url: str, payload: dict | None = None) -> object:
        if "getList" in url:
            assert payload == {"symbols": ["VCB"]}
            return [
                {
                    "listingInfo": {"symbol": "VCB", "refPrice": 56200},
                    "matchPrice": {
                        "matchPrice": 55700,
                        "accumulatedVolume": 2106400,
                        "receivedTime": "2026-10-20T04:53:22.236Z",
                    },
                }
            ]
        assert payload is not None
        assert payload["symbols"] == ["VNINDEX"]
        return [{"c": [1689.84, 1679.01], "t": ["1792368000", "1792454400"], "v": [10, 226050877]}]

    observations = VciMarketData(fetch=fetch, now=lambda: NOW).fetch_observations([_index(), _equity()])
    assert [item.symbol.ticker for item in observations] == ["VNINDEX", "VCB"]
    assert observations[1].price == Decimal("55700")
    assert observations[1].previous_price == Decimal("56200")
    assert observations[1].change_percent is None
    assert observations[1].volume == 2106400
    assert observations[1].as_of == datetime(2026, 10, 20, 11, 53, 22, 236000, tzinfo=ICT)
    assert observations[0].price == Decimal("1679.01")
    assert observations[0].previous_price == Decimal("1689.84")
    assert observations[0].change_percent is None
    assert observations[0].volume == 226050877


def test_vci_missing_symbol_is_an_error() -> None:
    def fetch(url: str, payload: dict | None = None) -> object:
        return []

    try:
        VciMarketData(fetch=fetch, now=lambda: NOW).fetch_observations([_equity()])
    except MarketDataError as exc:
        assert "VCB" in str(exc)
    else:
        raise AssertionError("expected MarketDataError")
