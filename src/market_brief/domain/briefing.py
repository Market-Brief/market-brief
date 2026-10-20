"""Build a Brief from quotes already in memory."""

from datetime import datetime

from market_brief.domain.models import Brief, Quote

DISCLAIMER = "Số liệu công khai, không phải khuyến nghị mua bán."
DISCLAIMER_EN = "Public market figures, not a recommendation to buy or sell."


def build_brief(
    quotes: tuple[Quote, ...] | list[Quote],
    generated_at: datetime,
    source: str,
    language: str = "vn",
) -> Brief:
    ordered = tuple(quotes)
    disclaimer = DISCLAIMER_EN if language == "en" else DISCLAIMER
    return Brief(
        generated_at=generated_at,
        quotes=ordered,
        source=source,
        disclaimer=disclaimer,
        language="en" if language == "en" else "vn",
    )
