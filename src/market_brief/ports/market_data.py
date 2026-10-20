"""MarketData is the only port allowed to talk to a price source."""

from collections.abc import Sequence
from typing import Protocol

from market_brief.domain.models import Observation, Symbol


class MarketDataError(Exception):
    """The source did not return a usable observation. Callers must not invent a price."""


class MarketData(Protocol):
    name: str

    def fetch_observations(self, symbols: Sequence[Symbol]) -> Sequence[Observation]:
        """Return one observation per symbol, in the same order. Prices stay in the source unit."""
