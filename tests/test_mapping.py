from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from market_brief.adapters.market_data.mapping import observation_from_candles
from market_brief.domain.models import Asset, PriceUnit, Symbol

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
WHEN = datetime(2026, 10, 9, 7, 0, tzinfo=ICT)


def _symbol(asset: Asset) -> Symbol:
    unit = PriceUnit.VND if asset is Asset.EQUITY else PriceUnit.POINT
    return Symbol("FPT" if asset is Asset.EQUITY else "VNINDEX", "Ten", "HOSE", asset, unit)


def test_equity_candle_keeps_the_source_unit() -> None:
    observation = observation_from_candles(
        _symbol(Asset.EQUITY),
        [
            {"time": "2026-10-08T07:00:00+07:00", "close": "59.7", "volume": 1000},
            {"time": "2026-10-09T07:00:00+07:00", "close": "57.9", "volume": 2000},
        ],
    )
    assert observation.price == Decimal("57.9")
    assert observation.previous_price == Decimal("59.7")
    assert observation.change_percent is None
    assert observation.volume == 2000
    assert observation.as_of == WHEN


def test_index_candle_keeps_points() -> None:
    observation = observation_from_candles(
        _symbol(Asset.INDEX),
        [
            {"time": WHEN, "close": "1738.97", "volume": 10},
            {"time": datetime(2026, 10, 10, 7, 0, tzinfo=ICT), "close": "1735.09", "volume": 11},
        ],
    )
    assert observation.price == Decimal("1735.09")
    assert observation.previous_price == Decimal("1738.97")
    assert observation.change_percent is None
