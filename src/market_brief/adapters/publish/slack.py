"""Post one Brief into a Slack channel."""

import os

from market_brief.adapters.slack.messages import render_slack_board
from market_brief.adapters.slack.web import SlackMessenger, SlackWeb
from market_brief.app.errors import ConfigError
from market_brief.domain.models import Board


class SlackPublisher:
    name = "slack"

    def __init__(self, channel: str, messenger: SlackMessenger) -> None:
        self._channel = channel
        self._messenger = messenger

    def publish(self, board: Board) -> None:
        self._messenger.post(self._channel, render_slack_board(board))


def slack_publisher_from_env() -> SlackPublisher:
    token = os.environ.get("SLACK_BOT_TOKEN", "").strip()
    channel = os.environ.get("SLACK_CHANNEL", "").strip()
    if not token or not channel:
        raise ConfigError("Kênh slack cần SLACK_BOT_TOKEN và SLACK_CHANNEL.")
    return SlackPublisher(channel, SlackWeb(token))
