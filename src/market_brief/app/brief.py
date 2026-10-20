"""Use case: crawl every source, hand the batch to the backend, then publish one Board."""

from collections.abc import Mapping, Sequence
from datetime import datetime

from market_brief.app.errors import ConfigError, IngestError
from market_brief.domain.briefing import build_brief
from market_brief.domain.models import Board, BoardColumn, Brief, Symbol
from market_brief.ports.ingest import Ingest
from market_brief.ports.market_data import MarketData, MarketDataError
from market_brief.ports.publisher import Publisher


def select_symbols(
    symbols: Sequence[Symbol],
    tickers: Sequence[str] | None,
    language: str = "vn",
) -> tuple[Symbol, ...]:
    if tickers is None:
        return tuple(symbols)
    by_ticker = {symbol.ticker: symbol for symbol in symbols}
    selected: list[Symbol] = []
    for raw in tickers:
        ticker = raw.strip().upper()
        if ticker not in by_ticker:
            known = ", ".join(symbol.ticker for symbol in symbols)
            if language == "en":
                raise ConfigError(f"{ticker} is not on the watchlist. Tracking: {known}.")
            raise ConfigError(f"Mã {ticker} không có trong watchlist. Đang theo dõi: {known}.")
        selected.append(by_ticker[ticker])
    return tuple(selected)


def run_brief(
    symbols: Sequence[Symbol],
    market_data: MarketData,
    ingest: Ingest,
    generated_at: datetime,
    language: str = "vn",
) -> Brief:
    if not symbols:
        if language == "en":
            raise ConfigError("There are no symbols to summarize.")
        raise ConfigError("Không có mã nào để tóm tắt.")
    observations = tuple(market_data.fetch_observations(symbols))
    expected = [symbol.ticker for symbol in symbols]
    received = [item.symbol.ticker for item in observations]
    if received != expected:
        raise MarketDataError(f"Nguồn trả sai danh sách mã. Cần {expected}, nhận {received}.")
    quotes = tuple(ingest.accept(market_data.name, observations))
    stored = [quote.symbol.ticker for quote in quotes]
    if stored != expected:
        raise IngestError(f"BE trả sai danh sách mã. Cần {expected}, nhận {stored}.")
    return build_brief(quotes, generated_at=generated_at, source=market_data.name, language=language)


def run_board(
    symbols: Sequence[Symbol],
    sources: Mapping[str, MarketData],
    ingest: Ingest,
    publishers: Sequence[Publisher],
    generated_at: datetime,
    language: str = "vn",
) -> Board:
    if not symbols:
        if language == "en":
            raise ConfigError("There are no symbols to summarize.")
        raise ConfigError("Không có mã nào để tóm tắt.")
    columns: list[BoardColumn] = []
    for name, market in sources.items():
        try:
            brief = run_brief(symbols, market, ingest, generated_at, language)
        except (MarketDataError, IngestError) as exc:
            columns.append(BoardColumn(name, None, str(exc)))
        else:
            columns.append(BoardColumn(name, brief, None))
    board = Board(generated_at=generated_at, columns=tuple(columns), language=language)
    for publisher in publishers:
        publisher.publish(board)
    return board
