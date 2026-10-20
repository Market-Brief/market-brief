from pathlib import Path

import yaml

from market_brief.app.errors import UnknownAdapterError
from market_brief.app.wiring import wire
from market_brief.entrypoints.cli import main


def _write(root: Path, runtime: dict, watchlist: dict | None = None) -> None:
    config = root / "config"
    config.mkdir(parents=True)
    (config / "runtime.yaml").write_text(yaml.safe_dump(runtime), encoding="utf-8")
    symbols = watchlist or {
        "symbols": [
            {"ticker": "VCB", "name": "Vietcombank", "exchange": "HOSE", "asset": "equity"},
        ]
    }
    (config / "watchlist.yaml").write_text(yaml.safe_dump(symbols), encoding="utf-8")


def test_unknown_publisher_lists_valid_names(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "ingest": "api",
            "publish": ["telegram"],
        },
    )
    try:
        wire(tmp_path)
    except UnknownAdapterError as exc:
        assert exc.name == "telegram"
        assert "terminal" in exc.known
        assert "slack" in exc.known
    else:
        raise AssertionError("expected UnknownAdapterError")


def test_unknown_source_lists_vci_and_kbs(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "sources": ["tcbs"],
            "ingest": "api",
            "publish": ["terminal"],
        },
    )
    try:
        wire(tmp_path)
    except UnknownAdapterError as exc:
        assert exc.slot == "sources"
        assert exc.name == "tcbs"
        assert "vci" in exc.known
        assert "kbs" in exc.known
        assert "dnse" in exc.known
    else:
        raise AssertionError("expected UnknownAdapterError")


def test_omitted_sources_uses_every_registered_adapter(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "ingest": "api",
            "publish": ["terminal"],
        },
    )
    services = wire(tmp_path)
    assert tuple(services.sources) == ("dnse", "vci", "kbs")


def test_cli_unknown_adapter_exits_with_the_name(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "sources": ["bloomberg"],
            "ingest": "api",
            "publish": ["terminal"],
        },
    )
    code = main(["--root", str(tmp_path), "brief"])
    assert code == 1
