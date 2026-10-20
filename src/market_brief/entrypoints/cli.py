"""CLI entrypoint. It loads config and calls a use case. It does not fetch prices itself."""

import argparse
import sys
from pathlib import Path

from market_brief.adapters.ingest.api import ApiIngest
from market_brief.adapters.slack.listen import serve
from market_brief.adapters.slack.messages import cli_help
from market_brief.app.brief import select_symbols
from market_brief.app.candle_csv import crawl_daily_csv
from market_brief.app.candle_import import iter_candle_batches, load_candle_csv
from market_brief.app.chat import brief_reply, require_slack_channel, require_slack_tokens
from market_brief.app.config import find_root, load_env_file, load_watchlist
from market_brief.app.errors import ConfigError, IngestError
from market_brief.app.wiring import wire
from market_brief.ports.market_data import MarketDataError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="market-brief", description="Bản tóm tắt chứng khoán Việt Nam.")
    parser.add_argument("--root", type=Path, default=None, help="Thư mục project. Mặc định là thư mục hiện tại.")
    commands = parser.add_subparsers(dest="command", required=True)
    brief = commands.add_parser("brief", help="Lấy giá và in bản tóm tắt.")
    brief.add_argument("--symbol", action="append", dest="symbols", help="Một mã trong watchlist. Lặp lại để lấy nhiều mã.")
    brief.add_argument("--lang", choices=("vn", "en"), default="vn", help="Ngôn ngữ bản tóm tắt. Mặc định vn.")
    commands.add_parser("slack", help="Chạy bot Slack và trả lời bằng bản tóm tắt.")
    candles = commands.add_parser("candles", help="Lấy nến ngày DNSE và ghi CSV.")
    candles.add_argument("--years", type=int, default=5, help="Số năm lùi từ hôm nay. Mặc định 5.")
    candles.add_argument("--output", type=Path, default=Path("data/dnse-daily-5y.csv"), help="File CSV.")
    candles.add_argument("--symbol", action="append", dest="symbols", help="Một mã trong watchlist. Lặp lại để lấy nhiều mã.")
    import_candles = commands.add_parser("import-candles", help="Đưa CSV nến ngày vào backend.")
    import_candles.add_argument("--input", type=Path, default=Path("data/dnse-daily-5y.csv"), help="File CSV đã crawl.")
    guide = commands.add_parser("help", help="Liệt kê lệnh có thể chạy.")
    guide.add_argument("--lang", choices=("vn", "en"), default="vn", help="Ngôn ngữ danh sách lệnh. Mặc định vn.")
    args = parser.parse_args(argv)
    if args.command == "help":
        print(cli_help(args.lang))
        return 0
    try:
        root = args.root if args.root is not None else find_root(Path.cwd())
        if args.command == "candles":
            if args.years < 1:
                raise ConfigError("--years phải từ 1 trở lên.")
            symbols = load_watchlist(root)
            selected = select_symbols(symbols, tuple(args.symbols) if args.symbols else None)
            destination = args.output if args.output.is_absolute() else root / args.output
            count = crawl_daily_csv(selected, args.years, destination)
            print(f"{count} nến → {destination}")
            return 0
        if args.command == "import-candles":
            load_env_file(root)
            source = args.input if args.input.is_absolute() else root / args.input
            candles, replaced = load_candle_csv(source)
            if replaced:
                print(f"Bỏ {replaced} nến trùng phiên, giữ nến muộn hơn trong ngày.")
            accepted = 0
            ingest = ApiIngest()
            for batch in iter_candle_batches(candles):
                accepted += ingest.accept_candles("dnse", batch)
                print(f"{accepted} nến", flush=True)
            print(f"{accepted} nến đã vào DB.")
            return 0
        load_env_file(root)
        services = wire(root)
        if args.command == "brief":
            tickers = tuple(args.symbols) if args.symbols else None
            services.run_board(tickers, language=args.lang)
        elif args.command == "slack":
            bot_token, app_token = require_slack_tokens()
            channel = require_slack_channel()
            serve(lambda text: brief_reply(services, text), bot_token, app_token, channel)
        return 0
    except (ConfigError, MarketDataError, IngestError) as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
