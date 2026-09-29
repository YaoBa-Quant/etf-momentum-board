from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RealtimeQuote:
    code: str
    trade_date: str
    last_price: float
    open: float | None
    high: float | None
    low: float | None
    pre_close: float | None
    pct_chg: float | None
    vol: float | None
    amount: float | None
    quote_time: str
    source: str
