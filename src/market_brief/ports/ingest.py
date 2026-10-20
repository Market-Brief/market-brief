"""Ingest delivers a crawl to the backend. It does not scale prices."""

from collections.abc import Sequence
from typing import Protocol

from market_brief.domain.models import Observation, Quote


class Ingest(Protocol):
    def accept(self, source: str, observations: Sequence[Observation]) -> Sequence[Quote]:
        """Send one source batch and return the quotes the backend stored."""
