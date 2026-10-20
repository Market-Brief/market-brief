from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from market_brief.app.candle_import import _one_bar_per_session
from market_brief.domain.models import Asset, CandleObservation, PriceUnit, Symbol

ICT = ZoneInfo("Asia/Ho_Chi_Minh")


def test_same_session_keeps_the_later_bar() -> None:
    symbol = Symbol("VCB", "Vietcombank", "HOSE", Asset.EQUITY, PriceUnit.VND)
    early = CandleObservation(symbol, Decimal("44.72"), Decimal("44.72"), Decimal("44.27"), Decimal("44.55"), 136100, datetime(2022, 12, 27, 7, 0, tzinfo=ICT))
    regular = CandleObservation(symbol, Decimal("44.55"), Decimal("44.89"), Decimal("44"), Decimal("44.11"), 1058000, datetime(2022, 12, 27, 9, 0, tzinfo=ICT))

    candles, replaced = _one_bar_per_session([early, regular])

    assert replaced == 1
    assert candles == (regular,)
