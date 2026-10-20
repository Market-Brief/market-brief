from datetime import datetime
from decimal import Decimal
from io import StringIO
from zoneinfo import ZoneInfo

from market_brief.adapters.publish.terminal import render_sources
from market_brief.app.brief import run_board, run_brief, select_symbols
from market_brief.app.errors import ConfigError
from market_brief.domain.briefing import DISCLAIMER, DISCLAIMER_EN, build_brief
from market_brief.domain.models import Asset, Board, BoardColumn, Observation, PriceUnit, Quote, Symbol
from market_brief.ports.market_data import MarketDataError

ICT = ZoneInfo("Asia/Ho_Chi_Minh")


class ListPublisher:
    name = "memory"

    def __init__(self) -> None:
        self.briefs = []

    def publish(self, board) -> None:
        self.briefs.append(board)


class FixedMarket:
    name = "fixed"

    def __init__(self, observations: tuple[Observation, ...]) -> None:
        self.observations = observations

    def fetch_observations(self, symbols) -> tuple[Observation, ...]:
        return self.observations


class MemoryIngest:
    def __init__(self, price: str = "56200") -> None:
        self.price = Decimal(price)
        self.batches: list[tuple[str, tuple[Observation, ...]]] = []

    def accept(self, source: str, observations) -> tuple[Quote, ...]:
        batch = tuple(observations)
        self.batches.append((source, batch))
        return tuple(
            Quote(item.symbol, self.price, Decimal("1.25"), item.volume, item.as_of, source)
            for item in batch
        )


def _observation(ticker: str, price: str) -> Observation:
    return Observation(
        symbol=Symbol(ticker, ticker, "HOSE", Asset.EQUITY, PriceUnit.VND),
        price=Decimal(price),
        previous_price=None,
        change_percent=None,
        volume=1500,
        as_of=datetime(2026, 10, 9, 15, 0, tzinfo=ICT),
    )


def _quote(ticker: str, price: str) -> Quote:
    return Quote(
        symbol=Symbol(ticker, ticker, "HOSE", Asset.EQUITY, PriceUnit.VND),
        price=Decimal(price),
        change_percent=Decimal("1.25"),
        volume=1500,
        as_of=datetime(2026, 10, 9, 15, 0, tzinfo=ICT),
        source="fixed",
    )


def test_run_brief_sends_the_crawl_and_uses_the_backend_price() -> None:
    symbols = (_observation("VCB", "56.7").symbol, _observation("FPT", "57.9").symbol)
    observations = (_observation("VCB", "56.7"), _observation("FPT", "57.9"))
    ingest = MemoryIngest()
    brief = run_brief(symbols, FixedMarket(observations), ingest, datetime(2026, 10, 20, 8, 15, tzinfo=ICT))
    assert [quote.symbol.ticker for quote in brief.quotes] == ["VCB", "FPT"]
    assert brief.quotes[0].price == Decimal("56200")
    assert brief.disclaimer == DISCLAIMER
    assert ingest.batches[0][0] == "fixed"
    assert ingest.batches[0][1][0].price == Decimal("56.7")


def test_run_board_publishes_one_board_and_keeps_a_failed_column() -> None:
    symbol = _observation("VCB", "56.7").symbol
    good = FixedMarket((_observation("VCB", "55.7"),))

    class Down:
        name = "kbs"

        def fetch_observations(self, symbols) -> tuple[Observation, ...]:
            raise MarketDataError("kbs down")

    publisher = ListPublisher()
    when = datetime(2026, 10, 20, 8, 15, tzinfo=ICT)
    board = run_board((symbol,), {"vci": good, "kbs": Down()}, MemoryIngest("55700"), [publisher], when, "en")
    assert publisher.briefs == [board]
    assert board.columns[0].brief is not None and board.columns[0].brief.source == "fixed"
    assert board.columns[1] == BoardColumn("kbs", None, "kbs down")
    text = render_sources(board)
    assert "55,700" in text
    assert "kbs: kbs down" in text
    assert DISCLAIMER_EN in text


def _board(brief) -> Board:
    return Board(brief.generated_at, (BoardColumn(brief.source, brief, None),), brief.language)


def test_terminal_uses_vietnamese_grouping() -> None:
    quote = _quote("VCB", "56700")
    text = render_sources(_board(build_brief([quote], datetime(2026, 10, 20, 8, 15, tzinfo=ICT), "fixed")))
    assert "VCB" in text
    assert "56.700" in text
    assert "+1,25%" in text
    assert "09/10/2026" in text
    assert DISCLAIMER in text


def test_english_brief_uses_english_labels_and_grouping() -> None:
    quote = _quote("VCB", "56700")
    text = render_sources(_board(build_brief([quote], datetime(2026, 10, 20, 8, 15, tzinfo=ICT), "vci", "en")))
    assert "vci" in text
    assert "Session: 09/10/2026" in text
    assert "Symbol" in text
    assert "56,700" in text
    assert "+1.25%" in text
    assert DISCLAIMER_EN in text


def test_unknown_symbol_names_the_watchlist() -> None:
    symbols = (_quote("VCB", "1").symbol,)
    try:
        select_symbols(symbols, ["HPG"])
    except ConfigError as exc:
        assert "HPG" in str(exc)
        assert "VCB" in str(exc)
    else:
        raise AssertionError("expected ConfigError")


def test_terminal_publisher_writes_the_stream() -> None:
    from market_brief.adapters.publish.terminal import TerminalPublisher
    from market_brief.domain.briefing import build_brief

    stream = StringIO()
    when = datetime(2026, 10, 20, 8, 15, tzinfo=ICT)
    brief = build_brief([_quote("FPT", "57900")], when, "fixed")
    board = Board(when, (BoardColumn("fixed", brief, None),), "vn")
    TerminalPublisher(stream).publish(board)
    assert "FPT" in stream.getvalue()
    assert "fixed" in stream.getvalue()
