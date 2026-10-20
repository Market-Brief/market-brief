"""Parse a Slack message and render a Brief for Slack mrkdwn."""

import re
from dataclasses import dataclass

from market_brief.adapters.publish.terminal import render_sources
from market_brief.domain.briefing import DISCLAIMER, DISCLAIMER_EN
from market_brief.domain.models import Board

_MENTION = re.compile(r"<@[A-Z0-9]+(?:\|[^>]+)?>")
_HELP = {"help", "giúp", "giup", "trợ giúp", "tro giup"}
_LANG = {"vn": "vn", "vi": "vn", "en": "en"}
_LANG_WORDS = {"lang", "language", "ngonngu", "ngônngữ"}

HELP = (
    "Các lệnh có thể chạy:\n"
    "\n"
    "• `/brief` — danh sách này\n"
    "• `brief` hoặc `tóm tắt` — cả watchlist, đủ dnse, vci và kbs\n"
    "• `brief VCB FPT` — vài mã trong watchlist\n"
    "• `brief vn` hoặc `brief en` — ngôn ngữ\n"
    "\n"
    "Gõ `/brief` để mở danh sách này. Nhắc tên bot kèm `brief` để lấy cả watchlist.\n"
    f"{DISCLAIMER}"
)

HELP_EN = (
    "Commands you can run:\n"
    "\n"
    "• `/brief` — this list\n"
    "• `brief` — the whole watchlist, with dnse, vci, and kbs\n"
    "• `brief VCB FPT` — a few tickers on the watchlist\n"
    "• `brief vn` or `brief en` — language\n"
    "\n"
    "Use `/brief` for this list. Mention the bot with `brief` for the whole watchlist.\n"
    f"{DISCLAIMER_EN}"
)

CLI_HELP = (
    "Các lệnh có thể chạy:\n"
    "\n"
    "• `market-brief help` — danh sách này\n"
    "• `market-brief brief` — in cả watchlist, đủ dnse, vci và kbs\n"
    "• `market-brief brief --symbol VCB --lang en` — một mã, tiếng Anh\n"
    "• `market-brief slack` — chạy bot Slack\n"
    "• `market-brief candles` — ghi nến ngày DNSE 5 năm ra CSV\n"
    "• `market-brief import-candles` — đưa CSV nến vào backend\n"
    "\n"
    "Trong kênh Slack đã cấu hình:\n"
    "\n"
    "• `/brief` — danh sách lệnh của bot\n"
    "• `@Market Brief brief` — cả watchlist\n"
    "• `/brief VCB en` — một mã, tiếng Anh\n"
    "\n"
    f"{DISCLAIMER}"
)

CLI_HELP_EN = (
    "Commands you can run:\n"
    "\n"
    "• `market-brief help` — this list\n"
    "• `market-brief brief` — print the watchlist, with dnse, vci, and kbs\n"
    "• `market-brief brief --symbol VCB --lang en` — one ticker, in English\n"
    "• `market-brief slack` — run the Slack bot\n"
    "• `market-brief candles` — write five years of DNSE daily bars to CSV\n"
    "• `market-brief import-candles` — send the candle CSV to the backend\n"
    "\n"
    "In the configured Slack channel:\n"
    "\n"
    "• `/brief` — the bot command list\n"
    "• `@Market Brief brief` — the whole watchlist\n"
    "• `/brief VCB en` — one ticker, in English\n"
    "\n"
    f"{DISCLAIMER_EN}"
)


@dataclass(frozen=True)
class Command:
    kind: str
    tickers: tuple[str, ...]
    language: str = "vn"


def help_text(language: str) -> str:
    return HELP_EN if language == "en" else HELP


def cli_help(language: str) -> str:
    return CLI_HELP_EN if language == "en" else CLI_HELP


def parse_command(text: str) -> Command:
    cleaned = " ".join(_MENTION.sub(" ", text).split())
    if not cleaned or cleaned.casefold() in _HELP:
        return Command("help", ())
    parts = cleaned.split(" ")
    head = parts[0].casefold()
    rest = parts[1:]
    if head in _HELP:
        language, _ = _options(rest)
        return Command("help", (), language)
    if head in {"tóm", "tom"} and rest and rest[0].casefold() in {"tắt", "tat"}:
        rest = rest[1:]
    elif head not in {"brief", "tómtắt", "tomtat"}:
        rest = parts
    language, tickers = _options(rest)
    return Command("brief", tickers, language)


def render_slack_board(board: Board) -> str:
    body = render_sources(board).strip("\n")
    return f"```\n{body}\n```"


def _options(tokens: list[str]) -> tuple[str, tuple[str, ...]]:
    language = "vn"
    tickers: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        folded = token.casefold()
        if ":" in folded:
            key, _, value = folded.partition(":")
            if key in _LANG_WORDS and value in _LANG:
                language = _LANG[value]
                index += 1
                continue
        if folded in _LANG:
            language = _LANG[folded]
            index += 1
            continue
        tickers.append(token.upper())
        index += 1
    return language, tuple(tickers)


def should_handle(event: dict[str, object]) -> bool:
    if event.get("bot_id") or event.get("bot_profile") or event.get("subtype"):
        return False
    if not isinstance(event.get("user"), str):
        return False
    channel = event.get("channel")
    text = event.get("text")
    if not isinstance(channel, str) or not isinstance(text, str):
        return False
    return event.get("type") == "app_mention"


def thread_target(event: dict[str, object]) -> str | None:
    if event.get("type") != "app_mention" and "thread_ts" not in event:
        return None
    thread = event.get("thread_ts") or event.get("ts")
    if isinstance(thread, str):
        return thread
    return None
