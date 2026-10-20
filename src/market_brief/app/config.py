"""Load the two config files. runtime.yaml names the ingest target and publishers."""

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from market_brief.app.errors import ConfigError
from market_brief.domain.models import Asset, PriceUnit, Symbol

ASSET_PRICE_UNIT = {
    Asset.EQUITY: PriceUnit.VND,
    Asset.INDEX: PriceUnit.POINT,
}


@dataclass(frozen=True)
class RuntimeConfig:
    sources: tuple[str, ...] | None
    ingest: str
    publish: tuple[str, ...]


def find_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "config" / "runtime.yaml").is_file():
            return candidate
    raise ConfigError(f"Không thấy config/runtime.yaml từ {start}. Chạy lệnh trong thư mục market-brief.")


def load_runtime(root: Path) -> RuntimeConfig:
    data = _mapping(_read_yaml(root / "config" / "runtime.yaml"), "runtime.yaml")
    publish_raw = data.get("publish")
    if not isinstance(publish_raw, list) or not publish_raw:
        raise ConfigError("runtime.yaml: publish phải là danh sách có ít nhất một tên.")
    publish = tuple(_item_text(item, "publish") for item in publish_raw)
    if len(set(publish)) != len(publish):
        raise ConfigError("runtime.yaml: publish có tên bị lặp.")
    return RuntimeConfig(
        sources=_sources(data.get("sources")),
        ingest=_text(data, "ingest", "runtime.yaml"),
        publish=publish,
    )


def load_watchlist(root: Path) -> tuple[Symbol, ...]:
    data = _mapping(_read_yaml(root / "config" / "watchlist.yaml"), "watchlist.yaml")
    raw_symbols = data.get("symbols")
    if not isinstance(raw_symbols, list) or not raw_symbols:
        raise ConfigError("watchlist.yaml: symbols phải là danh sách có ít nhất một mã.")
    symbols: list[Symbol] = []
    seen: set[str] = set()
    for item in raw_symbols:
        if not isinstance(item, dict):
            raise ConfigError("watchlist.yaml: mỗi mã phải là một mapping.")
        ticker = _text(item, "ticker", "watchlist.yaml").upper()
        if ticker in seen:
            raise ConfigError(f"watchlist.yaml: mã {ticker} bị lặp.")
        seen.add(ticker)
        asset = _asset(_text(item, "asset", "watchlist.yaml"))
        symbols.append(
            Symbol(
                ticker=ticker,
                name=_text(item, "name", "watchlist.yaml"),
                exchange=_text(item, "exchange", "watchlist.yaml"),
                asset=asset,
                price_unit=ASSET_PRICE_UNIT[asset],
            )
        )
    return tuple(symbols)


def _asset(value: str) -> Asset:
    try:
        return Asset(value)
    except ValueError as exc:
        allowed = ", ".join(asset.value for asset in Asset)
        raise ConfigError(f"watchlist.yaml: asset '{value}' không hợp lệ. Hợp lệ: {allowed}.") from exc


def _read_yaml(path: Path) -> object:
    if not path.is_file():
        raise ConfigError(f"Thiếu file {path}.")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if loaded is None:
        raise ConfigError(f"{path.name} đang trống.")
    return loaded


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ConfigError(f"{label} phải là một mapping YAML.")
    return value


def _text(data: dict[str, object], key: str, label: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{label}: thiếu '{key}'.")
    return value.strip()


def _sources(value: object) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list) or not value:
        raise ConfigError("runtime.yaml: sources phải là danh sách có ít nhất một tên.")
    names = tuple(_item_text(item, "sources") for item in value)
    if len(set(names)) != len(names):
        raise ConfigError("runtime.yaml: sources có tên bị lặp.")
    return names


def _item_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"runtime.yaml: mỗi phần tử của {label} phải là một tên.")
    return value.strip()


def load_env_file(root: Path) -> None:
    """Fill missing environment variables from a project .env file."""
    path = root / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")
