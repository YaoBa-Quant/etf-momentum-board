from __future__ import annotations

from datetime import datetime
import importlib
import json
import sys
from typing import Any
import urllib.request
from api.realtime_types import RealtimeQuote



def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result


def _normalize_quote_time(time_value: Any, now: datetime) -> str:
    if isinstance(time_value, str):
        clean_value = time_value.strip()
        if clean_value:
            if len(clean_value) >= 8 and clean_value[2] == ":" and clean_value[5] == ":":
                return f"{now.strftime('%Y-%m-%d')} {clean_value[:8]}"
            try:
                parsed = datetime.fromisoformat(clean_value)
                return parsed.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
    return now.strftime("%Y-%m-%d %H:%M:%S")


def _debug_post(hypothesis_id: str, location: str, msg: str, data: dict[str, Any]) -> None:
    # #region debug-point dbg:post
    try:
        with open(".dbg/mootdx-empty-quotes.env", "r", encoding="utf-8") as env_file:
            env_lines = env_file.read().splitlines()
        debug_url = next(
            (line.split("=", 1)[1] for line in env_lines if line.startswith("DEBUG_SERVER_URL=")),
            "http://127.0.0.1:7777/event",
        )
        session_id = next(
            (line.split("=", 1)[1] for line in env_lines if line.startswith("DEBUG_SESSION_ID=")),
            "mootdx-empty-quotes",
        )
        payload = {
            "sessionId": session_id,
            "runId": "pre-fix",
            "hypothesisId": hypothesis_id,
            "location": location,
            "msg": f"[DEBUG] {msg}",
            "data": data,
            "ts": int(datetime.now().timestamp() * 1000),
        }
        urllib.request.urlopen(
            urllib.request.Request(
                debug_url,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            ),
            timeout=2,
        ).read()
    except Exception:
        pass
    # #endregion


def _build_quote(record: dict[str, Any], now: datetime) -> RealtimeQuote | None:
    code = str(record.get("code", "")).strip()
    last_price = _to_float(record.get("price"))
    if not code or last_price is None or last_price <= 0:
        return None

    pre_close = _to_float(record.get("last_close"))
    pct_chg = _to_float(record.get("pct_chg"))
    if pct_chg is None and pre_close and pre_close > 0:
        pct_chg = (last_price / pre_close - 1.0) * 100.0

    return RealtimeQuote(
        code=code,
        trade_date=now.strftime("%Y%m%d"),
        last_price=last_price,
        open=_to_float(record.get("open")),
        high=_to_float(record.get("high")),
        low=_to_float(record.get("low")),
        pre_close=pre_close,
        pct_chg=pct_chg,
        vol=_to_float(record.get("vol")),
        amount=_to_float(record.get("amount")),
        quote_time=_normalize_quote_time(record.get("servertime"), now),
        source="mootdx",
    )


def fetch_realtime_quotes(codes: list[str]) -> list[RealtimeQuote]:
    if not codes:
        return []

    try:
        config_module = importlib.import_module("mootdx.config")
        quotes_module = importlib.import_module("mootdx.quotes")
    except ModuleNotFoundError:
        return []

    setup = getattr(config_module, "setup", None)
    get_config = getattr(config_module, "get", None)
    if callable(setup):
        setup()

    quotes_factory = getattr(quotes_module, "Quotes", None)
    if quotes_factory is None:
        return []

    server = None
    if callable(get_config):
        bestip_config = get_config("BESTIP") or {}
        if isinstance(bestip_config, dict):
            configured_server = bestip_config.get("HQ")
            if isinstance(configured_server, (list, tuple)) and len(configured_server) == 2:
                server = tuple(configured_server)
        if server is None:
            server_config = get_config("SERVER") or {}
            if isinstance(server_config, dict):
                hq_servers = server_config.get("HQ") or []
                if hq_servers and isinstance(hq_servers[0], (list, tuple)) and len(hq_servers[0]) >= 3:
                    server = (hq_servers[0][1], hq_servers[0][2])

    # #region debug-point A:config-and-server
    _debug_post(
        "A",
        "api/realtime_source_mootdx.py:fetch_realtime_quotes",
        "mootdx config resolved",
        {
            "python_version": sys.version,
            "codes_count": len(codes),
            "sample_codes": codes[:3],
            "server": list(server) if isinstance(server, tuple) else server,
        },
    )
    # #endregion

    try:
        client = quotes_factory.factory(market="std", server=server, timeout=5)
        feed = client.quotes(symbol=codes)
    except Exception as exc:
        # #region debug-point B:factory-or-quotes-error
        _debug_post(
            "B",
            "api/realtime_source_mootdx.py:factory-or-quotes",
            "mootdx factory or quotes raised",
            {
                "error_type": type(exc).__name__,
                "error": str(exc),
                "server": list(server) if isinstance(server, tuple) else server,
            },
        )
        # #endregion
        raise

    # #region debug-point C:feed-shape
    _debug_post(
        "C",
        "api/realtime_source_mootdx.py:feed-shape",
        "mootdx feed received",
        {
            "feed_type": type(feed).__name__ if feed is not None else None,
            "is_none": feed is None,
            "has_to_dict": hasattr(feed, "to_dict") if feed is not None else False,
        },
    )
    # #endregion
    if feed is None:
        return []

    if hasattr(feed, "to_dict"):
        records = feed.to_dict("records")
    elif isinstance(feed, list):
        records = feed
    else:
        return []

    # #region debug-point D:records-shape
    sample_record = records[0] if records and isinstance(records[0], dict) else None
    _debug_post(
        "D",
        "api/realtime_source_mootdx.py:records-shape",
        "mootdx records normalized",
        {
            "records_count": len(records),
            "sample_keys": sorted(sample_record.keys())[:12] if isinstance(sample_record, dict) else [],
            "sample_record": sample_record,
        },
    )
    # #endregion

    now = datetime.now()
    quotes: list[RealtimeQuote] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        quote = _build_quote(record, now)
        if quote is not None:
            quotes.append(quote)

    # #region debug-point E:filter-result
    _debug_post(
        "E",
        "api/realtime_source_mootdx.py:filter-result",
        "mootdx records filtered into quotes",
        {
            "records_count": len(records),
            "quotes_count": len(quotes),
            "sample_quote_codes": [quote.code for quote in quotes[:3]],
        },
    )
    # #endregion
    return quotes
