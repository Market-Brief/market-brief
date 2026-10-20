"""Composition root. This dict is the full list of adapters the process can build."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from market_brief.adapters.ingest.api import ApiIngest
from market_brief.adapters.market_data.dnse import DnseMarketData
from market_brief.adapters.market_data.kbs import KbsMarketData
from market_brief.adapters.market_data.vci import VciMarketData
from market_brief.adapters.publish.slack import slack_publisher_from_env
from market_brief.adapters.publish.terminal import TerminalPublisher
from market_brief.app.brief import run_board, select_symbols
from market_brief.app.config import load_runtime, load_watchlist
from market_brief.app.errors import UnknownAdapterError
from market_brief.domain.models import Board, Symbol
from market_brief.ports.ingest import Ingest
from market_brief.ports.market_data import MarketData
from market_brief.ports.publisher import Publisher

ICT = ZoneInfo("Asia/Ho_Chi_Minh")

MARKET_DATA: dict[str, Callable[[], MarketData]] = {
    "dnse": DnseMarketData,
    "vci": VciMarketData,
    "kbs": KbsMarketData,
}

PUBLISHERS: dict[str, Callable[[], Publisher]] = {
    "terminal": TerminalPublisher,
    "slack": slack_publisher_from_env,
}


@dataclass(frozen=True)
class Services:
    symbols: tuple[Symbol, ...]
    ingest: Ingest
    publishers: tuple[Publisher, ...]
    sources: dict[str, MarketData]

    def run_board(
        self,
        tickers: tuple[str, ...] | None = None,
        publishers: Sequence[Publisher] | None = None,
        language: str = "vn",
    ) -> Board:
        selected = select_symbols(self.symbols, tickers, language)
        return run_board(
            selected,
            self.sources,
            self.ingest,
            self.publishers if publishers is None else publishers,
            datetime.now(ICT),
            language,
        )


def wire(root: Path) -> Services:
    runtime = load_runtime(root)
    names = tuple(MARKET_DATA) if runtime.sources is None else runtime.sources
    unknown_source = next((name for name in names if name not in MARKET_DATA), None)
    if unknown_source is not None:
        raise UnknownAdapterError("sources", unknown_source, list(MARKET_DATA))
    if runtime.ingest != "api":
        raise UnknownAdapterError("ingest", runtime.ingest, ["api"])
    unknown = [name for name in runtime.publish if name not in PUBLISHERS]
    if unknown:
        raise UnknownAdapterError("publish", unknown[0], list(PUBLISHERS))
    return Services(
        symbols=load_watchlist(root),
        ingest=ApiIngest(),
        publishers=tuple(PUBLISHERS[name]() for name in runtime.publish),
        sources={name: MARKET_DATA[name]() for name in names},
    )
