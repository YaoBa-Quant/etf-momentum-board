from __future__ import annotations

from datetime import datetime
import logging
import ssl
from typing import Any
import urllib.request
from urllib.error import URLError

from api.realtime_types import RealtimeQuote


logger = logging.getLogger(__name__)
TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q="


def _build_opener(verify_ssl: bool) -> urllib.request.OpenerDirector:
    context = ssl.create_default_context() if verify_ssl else ssl._create_unverified_context()
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context),
        urllib.request.HTTPHandler(),
    )


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    clean_value = value.strip()
    if not clean_value:
        return None
    try:
        return float(clean_value)
    except ValueError:
        return None


def _to_prefixed_symbol(code: str) -> str:
    return f"sh{code}" if code.startswith(("5", "6", "9")) else f"sz{code}"


def _normalize_quote_time(time_value: str | None, now: datetime) -> str:
    if time_value:
        clean_value = time_value.strip()
        if len(clean_value) == 14 and clean_value.isdigit():
            return f"{clean_value[:4]}-{clean_value[4:6]}-{clean_value[6:8]} {clean_value[8:10]}:{clean_value[10:12]}:{clean_value[12:14]}"
    return now.strftime("%Y-%m-%d %H:%M:%S")


def _parse_line(line: str, now: datetime) -> RealtimeQuote | None:
    first_quote = line.find('"')
    last_quote = line.rfind('"')
    if first_quote < 0 or last_quote <= first_quote:
        return None

    fields = line[first_quote + 1 : last_quote].split("~")
    if len(fields) < 38:
        return None

    code = fields[2].strip()
    last_price = _to_float(fields[3])
    if not code or last_price is None or last_price <= 0:
        return None

    pre_close = _to_float(fields[4])
    pct_chg = _to_float(fields[32])
    return RealtimeQuote(
        code=code,
        trade_date=now.strftime("%Y%m%d"),
        last_price=last_price,
        open=_to_float(fields[5]),
        high=_to_float(fields[33]) if len(fields) > 33 else None,
        low=_to_float(fields[34]) if len(fields) > 34 else None,
        pre_close=pre_close,
        pct_chg=pct_chg,
        vol=None,
        amount=_to_float(fields[37]),
        quote_time=_normalize_quote_time(fields[30] if len(fields) > 30 else None, now),
        source="tencent",
    )


def _fetch_raw_quotes(codes: list[str]) -> str:
    prefixed_symbols = [_to_prefixed_symbol(code) for code in codes]
    request = urllib.request.Request(
        f"{TENCENT_QUOTE_URL}{','.join(prefixed_symbols)}",
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://gu.qq.com/",
        },
    )
    try:
        with _build_opener(verify_ssl=True).open(request, timeout=10) as response:
            return response.read().decode("gbk", errors="replace")
    except URLError as exc:
        if isinstance(exc.reason, ssl.SSLCertVerificationError):
            logger.warning("腾讯行情 HTTPS 证书校验失败，已降级为不校验证书: %s", exc)
            with _build_opener(verify_ssl=False).open(request, timeout=10) as response:
                return response.read().decode("gbk", errors="replace")
        raise


def fetch_realtime_quotes(codes: list[str]) -> list[RealtimeQuote]:
    normalized_codes = [code.strip() for code in codes if code and code.strip()]
    if not normalized_codes:
        return []

    raw_text = _fetch_raw_quotes(normalized_codes)
    now = datetime.now()
    quotes: list[RealtimeQuote] = []
    seen_codes: set[str] = set()
    for line in raw_text.split(";"):
        quote = _parse_line(line, now)
        if quote is None or quote.code in seen_codes:
            continue
        seen_codes.add(quote.code)
        quotes.append(quote)
    return quotes
