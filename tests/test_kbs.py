from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from market_brief.adapters.market_data.kbs import KbsMarketData
from market_brief.domain.models import Asset, PriceUnit, Symbol
from market_brief.ports.market_data import MarketDataError

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
NOW = datetime(2026, 10, 20, 11, 50, tzinfo=ICT)


def _equity() -> Symbol:
    return Symbol("VCB", "Vietcombank", "HOSE", Asset.EQUITY, PriceUnit.VND)


def _index() -> Symbol:
    return Symbol("VNINDEX", "VN-Index", "INDEX", Asset.INDEX, PriceUnit.POINT)


def test_kbs_uses_the_match_and_sorts_index_candles() -> None:
    def fetch(url: str, payload: dict | None = None) -> object:
        if url.endswith("/stock/iss"):
            assert payload == {"code": "VCB"}
            return [{"SB": "VCB", "CP": 55700, "CHP": "-0.8896797153024912", "TT": 2106400, "t": 1792472002226}]
        assert "index/VNINDEX/data_day" in url
        assert "sdate=" in url
        return {
            "data_day": [
                {"t": "2026-10-20 07:00", "c": "1679.01", "v": "226050877.0"},
                {"t": "2026-10-19 07:00", "c": 1689.84, "v": 519290379},
            ]
        }

    observations = KbsMarketData(fetch=fetch, now=lambda: NOW).fetch_observations([_equity(), _index()])
    assert [item.symbol.ticker for item in observations] == ["VCB", "VNINDEX"]
    assert observations[0].price == Decimal("55700")
    assert observations[0].change_percent == Decimal("-0.8896797153024912")
    assert observations[0].previous_price is None
    assert observations[0].volume == 2106400
    assert observations[1].price == Decimal("1679.01")
    assert observations[1].previous_price == Decimal("1689.84")
    assert observations[1].change_percent is None
    assert observations[1].volume == 226050877
    assert observations[1].as_of == datetime(2026, 10, 20, 7, 0, tzinfo=ICT)


def test_kbs_null_match_is_an_error() -> None:
    def fetch(url: str, payload: dict | None = None) -> object:
        return [{"SB": "VCB", "CP": None}]

    try:
        KbsMarketData(fetch=fetch, now=lambda: NOW).fetch_observations([_equity()])
    except MarketDataError as exc:
        assert "VCB" in str(exc)
    else:
        raise AssertionError("expected MarketDataError")
