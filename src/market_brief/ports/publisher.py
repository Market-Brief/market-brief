"""Publisher delivers one Board. It does not fetch prices."""

from typing import Protocol

from market_brief.domain.models import Board


class Publisher(Protocol):
    name: str

    def publish(self, board: Board) -> None:
        """Deliver the board. Raise on delivery failure."""
