"""Slack Web API and slash-command response URLs."""

import json
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from slack_sdk.errors import SlackApiError
from slack_sdk.web import WebClient

from market_brief.app.errors import ConfigError


class SlackDeliveryError(Exception):
    """Slack rejected or did not accept the message."""


class SlackMessenger(Protocol):
    def post(self, channel: str, text: str, thread_ts: str | None = None) -> None:
        """Send one message. Raise SlackDeliveryError on failure."""

    def respond(self, response_url: str, text: str, in_channel: bool = True) -> None:
        """Answer a slash command. Raise SlackDeliveryError on failure."""


class SlackWeb:
    def __init__(self, token: str | None = None, client: object | None = None) -> None:
        if client is None:
            if not token:
                raise ConfigError("Thiếu SLACK_BOT_TOKEN.")
            client = WebClient(token=token, timeout=30)
        self._client = client

    def post(self, channel: str, text: str, thread_ts: str | None = None) -> None:
        kwargs: dict[str, str] = {"channel": channel, "text": text}
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        try:
            self._client.chat_postMessage(**kwargs)  # type: ignore[attr-defined]
        except SlackApiError as exc:
            raise SlackDeliveryError(_api_error("Slack từ chối tin nhắn", exc)) from exc

    def respond(self, response_url: str, text: str, in_channel: bool = True) -> None:
        parsed = urlparse(response_url)
        if parsed.scheme != "https" or parsed.hostname != "hooks.slack.com":
            raise SlackDeliveryError("response_url không thuộc hooks.slack.com.")
        audience = "in_channel" if in_channel else "ephemeral"
        payload = json.dumps({"response_type": audience, "text": text}).encode()
        request = Request(
            response_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                if response.status >= 300:
                    raise SlackDeliveryError(f"Slack từ chối phản hồi lệnh: HTTP {response.status}.")
        except HTTPError as exc:
            raise SlackDeliveryError(f"Slack từ chối phản hồi lệnh: HTTP {exc.code}.") from exc
        except URLError as exc:
            raise SlackDeliveryError(f"Không gửi được phản hồi lệnh Slack: {exc.reason}.") from exc


def _api_error(prefix: str, exc: SlackApiError) -> str:
    response = exc.response
    error = response.get("error", "unknown") if response is not None else "unknown"
    return f"{prefix}: {error}."
