import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from slack_sdk.errors import SlackApiError

from market_brief.adapters.publish.slack import SlackPublisher
from market_brief.adapters.slack.listen import OUTSIDE_CHANNEL, SlackSession
from market_brief.adapters.slack.messages import parse_command, should_handle, thread_target
from market_brief.adapters.slack.web import SlackDeliveryError, SlackWeb
from market_brief.app.chat import brief_reply, require_slack_channel, require_slack_tokens
from market_brief.app.config import load_env_file
from market_brief.app.errors import ConfigError
from market_brief.app.wiring import wire
from market_brief.domain.briefing import build_brief
from market_brief.domain.models import Asset, Board, BoardColumn, PriceUnit, Quote, Symbol
from market_brief.entrypoints.cli import main
from market_brief.ports.market_data import MarketDataError

ICT = ZoneInfo("Asia/Ho_Chi_Minh")


class MemorySlack:
    def __init__(self) -> None:
        self.posts: list[tuple[str, str, str | None]] = []
        self.responses: list[tuple[str, str, bool]] = []

    def post(self, channel: str, text: str, thread_ts: str | None = None) -> None:
        self.posts.append((channel, text, thread_ts))

    def respond(self, response_url: str, text: str, in_channel: bool = True) -> None:
        self.responses.append((response_url, text, in_channel))


class BoomClient:
    def chat_postMessage(self, **kwargs: str) -> None:
        raise SlackApiError("fail", {"error": "not_in_channel"})


def _quote() -> Quote:
    return Quote(
        symbol=Symbol("VCB", "Vietcombank", "HOSE", Asset.EQUITY, PriceUnit.VND),
        price=Decimal("56700"),
        change_percent=Decimal("1.25"),
        volume=1500,
        as_of=datetime(2026, 10, 9, 15, 0, tzinfo=ICT),
        source="fixed",
    )


def _write(root: Path) -> None:
    config = root / "config"
    config.mkdir(parents=True)
    runtime = {
        "ingest": "api",
        "publish": ["terminal"],
    }
    symbols = {
        "symbols": [
            {"ticker": "VCB", "name": "Vietcombank", "exchange": "HOSE", "asset": "equity"},
        ]
    }
    (config / "runtime.yaml").write_text(yaml.safe_dump(runtime), encoding="utf-8")
    (config / "watchlist.yaml").write_text(yaml.safe_dump(symbols), encoding="utf-8")


def test_parse_command_reads_mention_help_and_tickers() -> None:
    assert parse_command("<@U123|brief>").kind == "help"
    assert parse_command("trợ giúp").kind == "help"
    assert parse_command("<@U123> brief vcb fpt").tickers == ("VCB", "FPT")
    assert parse_command("tóm tắt HPG").tickers == ("HPG",)
    assert parse_command("tom tat VCB").tickers == ("VCB",)
    assert parse_command("VCB").tickers == ("VCB",)
    assert parse_command("brief").tickers == ()
    chosen = parse_command("brief VCB en")
    assert chosen.tickers == ("VCB",)
    assert chosen.language == "en"
    assert parse_command("help en").kind == "help"
    assert parse_command("help en").language == "en"


def test_channel_noise_is_ignored_and_mention_uses_a_thread() -> None:
    mention = {"type": "app_mention", "channel": "C1", "text": "brief", "ts": "1.2", "user": "U2"}
    assert should_handle(mention)
    assert thread_target(mention) == "1.2"
    assert not should_handle({"type": "message", "channel_type": "channel", "channel": "C1", "text": "brief"})
    direct = {"type": "message", "channel_type": "im", "channel": "D1", "text": "VCB", "user": "U2", "ts": "3.4"}
    assert not should_handle(direct)
    assert thread_target(direct) is None


def test_session_replies_once_and_answers_slash_commands() -> None:
    box = MemorySlack()
    session = SlackSession(lambda text: f"ok:{text}", box, "C1")
    payload = {
        "event_id": "Ev1",
        "event": {"type": "app_mention", "channel": "C1", "text": "<@U9> VCB", "ts": "111.222", "user": "U2"},
    }
    session.handle("events_api", payload)
    session.handle("events_api", payload)
    session.handle(
        "slash_commands",
        {"command": "/brief", "text": "", "channel_id": "C1", "response_url": "https://hooks.slack.com/commands/T/1/x"},
    )
    session.handle(
        "slash_commands",
        {"command": "/brief", "text": "VCB", "channel_id": "C1", "response_url": "https://hooks.slack.com/commands/T/1/y"},
    )
    assert box.posts == [("C1", "ok:<@U9> VCB", "111.222")]
    assert box.responses[0] == ("https://hooks.slack.com/commands/T/1/x", "ok:help", True)
    assert box.responses[1] == ("https://hooks.slack.com/commands/T/1/y", "ok:VCB", True)
    session.handle(
        "slash_commands",
        {"command": "/help", "text": "en", "channel_id": "C1", "response_url": "https://hooks.slack.com/commands/T/1/z"},
    )
    assert box.responses[-1] == ("https://hooks.slack.com/commands/T/1/z", "ok:help en", True)


def test_reply_failure_is_sent_back() -> None:
    box = MemorySlack()

    def fail(text: str) -> str:
        raise RuntimeError("boom")

    SlackSession(fail, box, "C1").handle(
        "events_api",
        {
            "event_id": "Ev2",
            "event": {"type": "app_mention", "channel": "C1", "text": "brief", "user": "U2", "ts": "9.1"},
        },
    )
    assert box.posts[0][0] == "C1"
    assert "boom" in box.posts[0][1]
    assert box.posts[0][2] == "9.1"


def test_other_channels_get_no_brief() -> None:
    box = MemorySlack()
    session = SlackSession(lambda text: f"ok:{text}", box, "C0ALLOWED01")
    session.handle(
        "events_api",
        {
            "event_id": "Ev3",
            "event": {"type": "app_mention", "channel": "C0OTHER001", "text": "brief", "user": "U2", "ts": "1"},
        },
    )
    session.handle(
        "slash_commands",
        {"text": "VCB", "channel_id": "C0OTHER001", "response_url": "https://hooks.slack.com/commands/T/1/y"},
    )
    assert box.posts == []
    assert box.responses == [("https://hooks.slack.com/commands/T/1/y", OUTSIDE_CHANNEL, False)]


def test_slack_channel_rejects_the_sample_id(monkeypatch) -> None:
    monkeypatch.setenv("SLACK_CHANNEL", "C0123456789")
    try:
        require_slack_channel()
    except ConfigError as exc:
        assert "ID kênh thật" in str(exc)
    else:
        raise AssertionError("expected ConfigError")
    monkeypatch.setenv("SLACK_CHANNEL", "C0REALCHAN")
    assert require_slack_channel() == "C0REALCHAN"


def test_reply_renders_one_ticker_without_publishing() -> None:
    brief = build_brief([_quote()], datetime(2026, 10, 20, 8, 15, tzinfo=ICT), "fixed")
    calls: list[tuple[object, object]] = []

    class Services:
        def run_board(
            self,
            tickers: tuple[str, ...] | None = None,
            publishers: object = None,
            language: str = "vn",
        ) -> Board:
            calls.append((tickers, publishers, language))
            return Board(
                brief.generated_at,
                (
                    BoardColumn("dnse", brief, None),
                    BoardColumn("vci", brief, None),
                    BoardColumn("kbs", brief, None),
                ),
                language,
            )

    text = brief_reply(Services(), "<@U123> brief vcb")
    assert calls == [(("VCB",), (), "vn")]
    assert text.startswith("```")
    assert "dnse" in text
    assert "vci" in text
    assert "kbs" in text
    assert "56.700" in text


def test_help_and_market_errors_stay_in_the_reply() -> None:
    class Idle:
        def run_brief(self, tickers: tuple[str, ...] | None = None, publishers: object = None) -> object:
            raise AssertionError("không được lấy giá khi hỏi help")

    reply = brief_reply(Idle(), "help")
    assert "watchlist" in reply
    assert "/brief" in reply

    class Broken:
        def run_board(
            self,
            tickers: tuple[str, ...] | None = None,
            publishers: object = None,
            language: str = "vn",
        ) -> Board:
            raise MarketDataError("Nguồn giá không trả lời.")

    assert "Nguồn giá" in brief_reply(Broken(), "VCB")


def test_reply_switches_language_and_keeps_every_source() -> None:
    english = build_brief([_quote()], datetime(2026, 10, 20, 8, 15, tzinfo=ICT), "vci", "en")

    class Every:
        def run_board(
            self,
            tickers: tuple[str, ...] | None = None,
            publishers: object = None,
            language: str = "vn",
        ) -> Board:
            assert tickers == ("VCB",)
            assert publishers == ()
            assert language == "en"
            return Board(
                english.generated_at,
                (
                    BoardColumn("dnse", english, None),
                    BoardColumn("vci", english, None),
                    BoardColumn("kbs", None, "kbs down"),
                ),
                language,
            )

    compared = brief_reply(Every(), "brief VCB en")
    assert "dnse" in compared
    assert "56,700" in compared
    assert "kbs: kbs down" in compared


def test_publisher_posts_the_rendered_brief() -> None:
    box = MemorySlack()
    when = datetime(2026, 10, 20, 8, 15, tzinfo=ICT)
    brief = build_brief([_quote()], when, "fixed")
    SlackPublisher("C9", box).publish(Board(when, (BoardColumn("dnse", brief, None),), "vn"))
    channel, text, thread = box.posts[0]
    assert channel == "C9"
    assert thread is None
    assert text.startswith("```")
    assert "VCB" in text


def test_web_post_reports_the_slack_error() -> None:
    try:
        SlackWeb(client=BoomClient()).post("C1", "hi")
    except SlackDeliveryError as exc:
        assert "not_in_channel" in str(exc)
    else:
        raise AssertionError("expected SlackDeliveryError")


def test_response_url_must_be_a_slack_hook() -> None:
    try:
        SlackWeb(client=BoomClient()).respond("https://evil.example/hook", "hi")
    except SlackDeliveryError as exc:
        assert "hooks.slack.com" in str(exc)
    else:
        raise AssertionError("expected SlackDeliveryError")


def test_env_file_fills_only_missing_keys(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-already")
    monkeypatch.delenv("SLACK_APP_TOKEN", raising=False)
    (tmp_path / ".env").write_text(
        'SLACK_BOT_TOKEN=xoxb-file\nexport SLACK_APP_TOKEN="xapp-1"\n# note\n\n',
        encoding="utf-8",
    )
    load_env_file(tmp_path)
    assert os.environ["SLACK_BOT_TOKEN"] == "xoxb-already"
    assert os.environ["SLACK_APP_TOKEN"] == "xapp-1"


def test_slack_tokens_reject_the_wrong_kind(monkeypatch) -> None:
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_APP_TOKEN", raising=False)
    try:
        require_slack_tokens()
    except ConfigError as exc:
        assert "SLACK_BOT_TOKEN" in str(exc)
    else:
        raise AssertionError("expected ConfigError")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxp-user")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-1")
    try:
        require_slack_tokens()
    except ConfigError as exc:
        assert "xoxb-" in str(exc)
    else:
        raise AssertionError("expected ConfigError")


def test_slack_publisher_requires_channel(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_CHANNEL", raising=False)
    config = tmp_path / "config"
    config.mkdir()
    (config / "runtime.yaml").write_text(
        yaml.safe_dump(
            {
                "ingest": "api",
                "publish": ["slack"],
            }
        ),
        encoding="utf-8",
    )
    (config / "watchlist.yaml").write_text(
        yaml.safe_dump(
            {"symbols": [{"ticker": "VCB", "name": "Vietcombank", "exchange": "HOSE", "asset": "equity"}]}
        ),
        encoding="utf-8",
    )
    try:
        wire(tmp_path)
    except ConfigError as exc:
        assert "SLACK_CHANNEL" in str(exc)
    else:
        raise AssertionError("expected ConfigError")


def test_slack_publisher_wires_from_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_CHANNEL", "C123")
    config = tmp_path / "config"
    config.mkdir()
    (config / "runtime.yaml").write_text(
        yaml.safe_dump(
            {
                "ingest": "api",
                "publish": ["slack"],
            }
        ),
        encoding="utf-8",
    )
    (config / "watchlist.yaml").write_text(
        yaml.safe_dump(
            {"symbols": [{"ticker": "VCB", "name": "Vietcombank", "exchange": "HOSE", "asset": "equity"}]}
        ),
        encoding="utf-8",
    )
    services = wire(tmp_path)
    assert services.publishers[0].name == "slack"


def test_cli_help_lists_commands_without_loading_config(capsys) -> None:
    assert main(["help"]) == 0
    text = capsys.readouterr().out
    assert "market-brief brief" in text
    assert "market-brief slack" in text
    assert "/brief" in text
    assert main(["help", "--lang", "en"]) == 0
    assert "Commands you can run" in capsys.readouterr().out


def test_cli_slack_stops_before_connecting(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_APP_TOKEN", raising=False)
    _write(tmp_path)
    assert main(["--root", str(tmp_path), "slack"]) == 1
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxp-user")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-1")
    assert main(["--root", str(tmp_path), "slack"]) == 1
