"""Plain-text brief for a terminal."""

import sys
from collections.abc import Sequence
from decimal import Decimal
from typing import TextIO
from zoneinfo import ZoneInfo

from market_brief.domain.briefing import DISCLAIMER, DISCLAIMER_EN
from market_brief.domain.models import Board, Brief, PriceUnit, Quote

ICT = ZoneInfo("Asia/Ho_Chi_Minh")

_LABELS = {
    "vn": {"session": "Phiên", "symbol": "Mã"},
    "en": {"session": "Session", "symbol": "Symbol"},
}


class TerminalPublisher:
    name = "terminal"

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = sys.stdout if stream is None else stream

    def publish(self, board: Board) -> None:
        self._stream.write(render_sources(board))


def render_sources(board: Board) -> str:
    """One table, one column per source. A failed source stays as a note under the table."""
    selected = _language(board.language)
    labels = _LABELS[selected]
    briefs = [column.brief for column in board.columns if column.brief is not None]
    quotes = [quote for brief in briefs for quote in brief.quotes]
    stamp = briefs[0].generated_at if briefs else board.generated_at
    lines = [
        f"Market Brief · {stamp.astimezone(ICT).strftime('%d/%m/%Y %H:%M ICT')}",
        _session_line(quotes, selected),
        "",
        _source_row(labels["symbol"], [column.name for column in board.columns]),
        _source_row("---", ["---" for _ in board.columns]),
    ]
    order = list(briefs[0].quotes) if briefs else []
    for sample in order:
        cells = [_cell(_find(column.brief, sample.symbol.ticker), selected) for column in board.columns]
        label = sample.symbol.ticker if sample.symbol.name == sample.symbol.ticker else f"{sample.symbol.ticker}  {sample.symbol.name}"
        lines.append(_source_row(label, cells))
    errors = [f"{column.name}: {column.error}" for column in board.columns if column.error]
    if errors:
        lines.extend(["", *errors])
    disclaimer = DISCLAIMER_EN if selected == "en" else DISCLAIMER
    lines.extend(["", disclaimer, ""])
    return "\n".join(lines)


def _language(language: str) -> str:
    return "en" if language == "en" else "vn"


def _session_line(quotes: Sequence[Quote], language: str) -> str:
    label = _LABELS[language]["session"]
    dates = sorted({quote.as_of.astimezone(ICT).date() for quote in quotes})
    if not dates:
        return f"{label}: —"
    if len(dates) == 1:
        return f"{label}: {dates[0].strftime('%d/%m/%Y')}"
    start = dates[0].strftime("%d/%m/%Y")
    end = dates[-1].strftime("%d/%m/%Y")
    return f"{label}: {start} – {end}"


def _source_row(symbol: str, cells: Sequence[str]) -> str:
    body = "".join(f"{cell:<22}" for cell in cells)
    return f"{symbol:<24}{body}".rstrip()


def _cell(quote: Quote | None, language: str) -> str:
    if quote is None:
        return "—"
    return f"{_format_price(quote, language)} {_format_percent(quote.change_percent, language)}"


def _find(brief: Brief | None, ticker: str) -> Quote | None:
    if brief is None:
        return None
    for quote in brief.quotes:
        if quote.symbol.ticker == ticker:
            return quote
    return None


def _format_price(quote: Quote, language: str) -> str:
    if quote.symbol.price_unit is PriceUnit.VND:
        return _group(f"{int(quote.price)}", language)
    return _group_decimal(quote.price, 2, language)


def _format_percent(value: Decimal | None, language: str) -> str:
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{_group_decimal(value, 2, language)}%"


def _group(digits: str, language: str) -> str:
    sign = ""
    body = digits
    if body.startswith("-"):
        sign = "-"
        body = body[1:]
    head, dot, frac = body.partition(".")
    if language == "en":
        grouped = f"{int(head):,}"
        return f"{sign}{grouped}.{frac}" if dot else f"{sign}{grouped}"
    grouped = f"{int(head):,}".replace(",", ".")
    if dot:
        return f"{sign}{grouped},{frac}"
    return f"{sign}{grouped}"


def _group_decimal(value: Decimal, places: int, language: str) -> str:
    text = f"{value:.{places}f}"
    return _group(text, language)
