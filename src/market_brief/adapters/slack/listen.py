"""Socket Mode loop. It acks Slack, then asks the app for a reply."""

import sys
import threading
import traceback
from collections.abc import Callable

from slack_sdk.errors import SlackApiError
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.web import WebClient

from market_brief.adapters.slack.messages import should_handle, thread_target

OUTSIDE_CHANNEL = "Market Brief chỉ trả lời trong kênh đã cấu hình."
from market_brief.adapters.slack.web import SlackDeliveryError, SlackMessenger, SlackWeb
from market_brief.app.errors import ConfigError


class SlackSession:
    def __init__(self, reply: Callable[[str], str], messenger: SlackMessenger, channel: str) -> None:
        self._reply = reply
        self._messenger = messenger
        self._channel = channel
        self._seen: set[str] = set()

    def handle(self, kind: str, payload: dict[str, object]) -> None:
        if kind == "events_api":
            self._on_event(payload)
        elif kind == "slash_commands":
            self._on_slash(payload)

    def _on_event(self, payload: dict[str, object]) -> None:
        event_id = payload.get("event_id")
        if isinstance(event_id, str) and not self._remember(event_id):
            return
        event = payload.get("event")
        if not isinstance(event, dict) or not should_handle(event):
            return
        channel = event.get("channel")
        text = event.get("text")
        if not isinstance(channel, str) or not isinstance(text, str) or channel != self._channel:
            return
        self._messenger.post(channel, self._answer(text), thread_ts=thread_target(event))

    def _on_slash(self, payload: dict[str, object]) -> None:
        raw = payload.get("text")
        text = raw.strip() if isinstance(raw, str) else ""
        command = payload.get("command")
        if command == "/help" or (command == "/brief" and not text):
            text = f"help {text}".strip()
        response_url = payload.get("response_url")
        channel = payload.get("channel_id")
        if channel != self._channel:
            if isinstance(response_url, str) and response_url:
                self._messenger.respond(response_url, OUTSIDE_CHANNEL, in_channel=False)
            return
        answer = self._answer(text or "brief")
        if isinstance(response_url, str) and response_url:
            self._messenger.respond(response_url, answer)
            return
        if isinstance(channel, str):
            self._messenger.post(channel, answer)

    def _answer(self, text: str) -> str:
        try:
            return self._reply(text)
        except Exception as exc:
            return f"Không tạo được bản tóm tắt: {exc}"

    def _remember(self, event_id: str) -> bool:
        if event_id in self._seen:
            return False
        self._seen.add(event_id)
        if len(self._seen) > 500:
            self._seen.clear()
            self._seen.add(event_id)
        return True


def serve(reply: Callable[[str], str], bot_token: str, app_token: str, channel: str) -> None:
    web = WebClient(token=bot_token, timeout=30)
    messenger = SlackWeb(client=web)
    try:
        auth = web.auth_test()
    except SlackApiError as exc:
        raise ConfigError(_api_error("Slack từ chối bot token", exc)) from exc
    user = auth.get("user") or "bot"
    print(f"Market Brief đang nghe kênh {channel} với tư cách @{user}. Ctrl+C để dừng.", flush=True)
    session = SlackSession(reply, messenger, channel)
    client = SocketModeClient(app_token=app_token, web_client=web)

    def process(sock: SocketModeClient, req: SocketModeRequest) -> None:
        sock.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
        try:
            session.handle(req.type, req.payload)
        except SlackDeliveryError as exc:
            print(exc, file=sys.stderr)
        except Exception:
            traceback.print_exc()

    client.socket_mode_request_listeners.append(process)
    try:
        client.connect()
    except SlackApiError as exc:
        raise ConfigError(_api_error("Không mở được Socket Mode", exc)) from exc
    except Exception as exc:
        raise ConfigError(f"Không mở được Socket Mode: {exc}") from exc
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        return


def _api_error(prefix: str, exc: SlackApiError) -> str:
    response = exc.response
    error = response.get("error", "unknown") if response is not None else "unknown"
    return f"{prefix}: {error}."
