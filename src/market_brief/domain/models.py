"""Domain types. No network, no database, no publisher."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class Asset(str, Enum):
    EQUITY = "equity"
    INDEX = "index"


class PriceUnit(str, Enum):
    VND = "vnd"
    POINT = "point"


@dataclass(frozen=True)
class Symbol:
    ticker: str
    name: str
    exchange: str
    asset: Asset
    price_unit: PriceUnit


@dataclass(frozen=True)
class CandleObservation:
    """One daily bar in the source unit. The backend scales and stores it."""

    symbol: Symbol
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | None
    as_of: datetime


@dataclass(frozen=True)
class Observation:
    """Native numbers from a crawl. The backend scales and stores them."""

    symbol: Symbol
    price: Decimal
    previous_price: Decimal | None
    change_percent: Decimal | None
    volume: int | None
    as_of: datetime


@dataclass(frozen=True)
class Quote:
    symbol: Symbol
    price: Decimal
    change_percent: Decimal | None
    volume: int | None
    as_of: datetime
    source: str


@dataclass(frozen=True)
class Brief:
    generated_at: datetime
    quotes: tuple[Quote, ...]
    source: str
    disclaimer: str
    language: str = "vn"


@dataclass(frozen=True)
class BoardColumn:
    name: str
    brief: Brief | None
    error: str | None


@dataclass(frozen=True)
class Board:
    generated_at: datetime
    columns: tuple[BoardColumn, ...]
    language: str
