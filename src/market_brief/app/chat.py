"""Turn a Slack message into the text the bot sends back."""

import os
import re
from collections.abc import Sequence
from typing import Protocol

from market_brief.adapters.slack.messages import help_text, parse_command, render_slack_board
from market_brief.app.errors import ConfigError
from market_brief.domain.models import Board
from market_brief.ports.market_data import MarketDataError
from market_brief.ports.publisher import Publisher


class BriefRunner(Protocol):
    def run_board(
        self,
        tickers: tuple[str, ...] | None = None,
        publishers: Sequence[Publisher] | None = None,
        language: str = "vn",
    ) -> Board:
        """Fetch every configured source and return one board."""


def brief_reply(services: BriefRunner, text: str) -> str:
    command = parse_command(text)
    if command.kind == "help":
        return help_text(command.language)
    try:
        board = services.run_board(command.tickers or None, publishers=(), language=command.language)
    except (ConfigError, MarketDataError) as exc:
        return str(exc)
    return render_slack_board(board)


def require_slack_tokens() -> tuple[str, str]:
    bot = os.environ.get("SLACK_BOT_TOKEN", "").strip()
    app = os.environ.get("SLACK_APP_TOKEN", "").strip()
    missing = [name for name, value in (("SLACK_BOT_TOKEN", bot), ("SLACK_APP_TOKEN", app)) if not value]
    if missing:
        joined = " và ".join(missing)
        raise ConfigError(f"Bot Slack cần {joined}. Đặt trong môi trường hoặc file .env.")
    if not bot.startswith("xoxb-"):
        raise ConfigError("SLACK_BOT_TOKEN phải là bot token, bắt đầu bằng xoxb-.")
    if not app.startswith("xapp-"):
        raise ConfigError("SLACK_APP_TOKEN phải là app-level token, bắt đầu bằng xapp-.")
    return bot, app


def require_slack_channel() -> str:
    channel = os.environ.get("SLACK_CHANNEL", "").strip()
    if not channel or channel == "C0123456789":
        raise ConfigError("SLACK_CHANNEL cần ID kênh thật. Mở chi tiết kênh trong Slack và copy Channel ID.")
    if re.fullmatch(r"[CG][A-Z0-9]{8,}", channel) is None:
        raise ConfigError("SLACK_CHANNEL phải là ID kênh, bắt đầu bằng C.")
    return channel
