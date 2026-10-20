"""JSON HTTP for market-data adapters."""

import json
import urllib.error
import urllib.request
from collections.abc import Mapping

from market_brief.ports.market_data import MarketDataError


def request_json(url: str, payload: Mapping[str, object] | None, source: str, headers: Mapping[str, str]) -> object:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=dict(headers), method="GET" if data is None else "POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise MarketDataError(f"{source} trả HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise MarketDataError(f"Không gọi được {source} ({exc.reason}).") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise MarketDataError(f"{source} trả JSON không đọc được.") from exc
