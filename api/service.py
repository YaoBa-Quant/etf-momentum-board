from __future__ import annotations

from datetime import datetime, timedelta
from io import BytesIO
import math
import time
from typing import Any

import pandas as pd
import tushare as ts

from api.config import settings
from api.db import get_connection, init_db
from api.etf_pool import ETF_POOL
from api.metrics import calc_slope_momentum_from_closes
from api.realtime_service import get_realtime_dashboard_context, is_market_session_time

TRADE_CALENDAR_SYNC_DAYS = 1080
AVAILABLE_TRADE_DATE_LIMIT = 480
SEARCH_ENTRY_GROUP_NAME = "临时搜索"
SLOPE_LOOKBACK_DAYS = 20
_TRADE_CALENDAR_REFRESHED_DATES: set[str] = set()

def _get_tushare_client():
    if not settings.tushare_token:
        raise RuntimeError("未配置 TUSHARE_TOKEN")
    return ts.pro_api(settings.tushare_token)

def _today_str() -> str:
    return datetime.now().strftime("%Y%m%d")

def _date_to_api(date_str: str) -> str:
    return date_str.replace("-", "")

def _date_to_ui(date_str: str) -> str:
    return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

def _shift_date(date_str: str, days: int) -> str:
    return (datetime.strptime(date_str, "%Y%m%d") + timedelta(days=days)).strftime("%Y%m%d")

def _normalize_etf_code(code: str) -> str:
    clean_code = code.strip()
    if not clean_code.isdigit() or len(clean_code) != 6:
        raise ValueError("请输入6位ETF代码")
    return clean_code

def _parse_percent_value(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "--":
        return None
    text = text.replace("%", "").replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None

def _build_full_code_from_ts_code(ts_code: str) -> tuple[str, str]:
    if ts_code.endswith(".SH"):
        return ts_code.replace(".SH", ".XSHG"), "XSHG"
    if ts_code.endswith(".SZ"):
        return ts_code.replace(".SZ", ".XSHE"), "XSHE"
    raise ValueError(f"无法识别交易所代码: {ts_code}")

def _upsert_etf_items(items: list[dict[str, Any]]) -> None:
    with get_connection() as connection:
        connection.executemany(
            """
            INSERT INTO etf_pool (code, name, ts_code, full_code, group_name, market, is_visible, entry_type)
            VALUES (:code, :name, :ts_code, :full_code, :group_name, :market, :is_visible, :entry_type)
            ON CONFLICT(code) DO UPDATE SET
                name = excluded.name,
                ts_code = excluded.ts_code,
                full_code = excluded.full_code,
                group_name = excluded.group_name,
                market = excluded.market,
                is_visible = excluded.is_visible,
                entry_type = excluded.entry_type
            """,
            items,
        )

def _upsert_etf_pool() -> None:
    visible_items = [{**item, "is_visible": 1, "entry_type": "default"} for item in ETF_POOL]
    _upsert_etf_items(visible_items)

def _get_visible_etf_items() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT code, name, ts_code, full_code, group_name, market, is_visible, entry_type
            FROM etf_pool
            WHERE is_visible = 1
            ORDER BY code ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]

def _get_etf_item(code: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT code, name, ts_code, full_code, group_name, market, is_visible, entry_type
            FROM etf_pool
            WHERE code = ?
            """,
            (code,),
        ).fetchone()
    return dict(row) if row else None

def _fetch_remote_etf_item(pro, code: str) -> dict[str, Any]:
    normalized_code = _normalize_etf_code(code)
    for suffix in ("SH", "SZ"):
        ts_code = f"{normalized_code}.{suffix}"
        frame = pro.fund_basic(ts_code=ts_code, fields="ts_code,name,status")
        if frame.empty:
            continue

        row = frame.iloc[0].to_dict()
        full_code, market = _build_full_code_from_ts_code(str(row["ts_code"]))
        return {
            "code": normalized_code,
            "name": str(row["name"]),
            "ts_code": str(row["ts_code"]),
            "full_code": full_code,
            "group_name": SEARCH_ENTRY_GROUP_NAME,
            "market": market,
            "is_visible": 0,
            "entry_type": "searched",
        }
    raise RuntimeError(f"未找到 ETF 代码 {normalized_code} 对应的基金信息")

def _resolve_etf_item(code: str) -> dict[str, Any]:
    normalized_code = _normalize_etf_code(code)
    existing_item = _get_etf_item(normalized_code)
    if existing_item:
        return existing_item

    pro = _get_tushare_client()
    remote_item = _fetch_remote_etf_item(pro, normalized_code)
    _upsert_etf_items([remote_item])
    return remote_item

def _sync_trade_calendar(pro, start_date: str, end_date: str) -> list[str]:
    calendar = pro.trade_cal(exchange="SSE", start_date=start_date, end_date=end_date, fields="cal_date,is_open")
    if calendar.empty:
        raise RuntimeError("未获取到交易日历")

    rows = calendar.to_dict("records")
    with get_connection() as connection:
        connection.executemany(
            """
            INSERT INTO trade_calendar (trade_date, is_open)
            VALUES (:cal_date, :is_open)
            ON CONFLICT(trade_date) DO UPDATE SET is_open = excluded.is_open
            """,
            rows,
        )

    open_dates = sorted(row["cal_date"] for row in rows if int(row["is_open"]) == 1)
    return open_dates

def _build_qfq_fund_records(
    raw_frame: pd.DataFrame,
    adj_frame: pd.DataFrame,
    item: dict[str, Any],
    qfq_base_factor: float,
) -> list[dict[str, Any]]:
    frame = raw_frame.merge(adj_frame[["trade_date", "adj_factor"]], on="trade_date", how="left")
    if frame["adj_factor"].isna().all():
        return []

    frame = frame.sort_values("trade_date", ascending=True).reset_index(drop=True)
    frame["adj_factor"] = frame["adj_factor"].ffill().bfill()
    if frame["adj_factor"].isna().any():
        return []

    scale = frame["adj_factor"].astype(float) / float(qfq_base_factor)
    for field in ("open", "high", "low", "close", "pre_close", "change"):
        frame[field] = frame[field].astype(float) * scale
    frame["pct_chg"] = frame["pct_chg"].astype(float)
    frame = frame.fillna(0.0)

    return [
        {
            "trade_date": row["trade_date"],
            "code": item["code"],
            "ts_code": item["ts_code"],
            "full_code": item["full_code"],
            "open": float(row.get("open", 0.0)),
            "high": float(row.get("high", 0.0)),
            "low": float(row.get("low", 0.0)),
            "close": float(row.get("close", 0.0)),
            "pre_close": float(row.get("pre_close", 0.0)),
            "change": float(row.get("change", 0.0)),
            "pct_chg": float(row.get("pct_chg", 0.0)),
            "adj_factor": float(row.get("adj_factor", 0.0)),
            "vol": float(row.get("vol", 0.0)),
            "amount": float(row.get("amount", 0.0)),
        }
        for row in frame.to_dict("records")
    ]

def _upsert_qfq_fund_records(connection, records: list[dict[str, Any]]) -> None:
    connection.executemany(
        """
        INSERT INTO etf_daily_bar (
            trade_date, code, ts_code, full_code, open, high, low, close, pre_close, change, pct_chg, adj_factor, vol, amount
        )
        VALUES (
            :trade_date, :code, :ts_code, :full_code, :open, :high, :low, :close, :pre_close, :change, :pct_chg, :adj_factor, :vol, :amount
        )
        ON CONFLICT(trade_date, code) DO UPDATE SET
            ts_code = excluded.ts_code,
            full_code = excluded.full_code,
            open = excluded.open,
            high = excluded.high,
            low = excluded.low,
            close = excluded.close,
            pre_close = excluded.pre_close,
            change = excluded.change,
            pct_chg = excluded.pct_chg,
            adj_factor = excluded.adj_factor,
            vol = excluded.vol,
            amount = excluded.amount
        """,
        records,
    )

def _sync_fund_daily(pro, start_date: str, end_date: str, items: list[dict[str, Any]] | None = None) -> tuple[int, list[str]]:
    total_rows = 0
    failed_codes: list[str] = []
    sync_items = items if items is not None else _get_visible_etf_items()

    with get_connection() as connection:
        for item in sync_items:
            connection.execute("SAVEPOINT etf_item_sync")
            try:
                raw_frame = pro.fund_daily(ts_code=item["ts_code"], start_date=start_date, end_date=end_date)
                adj_frame = pro.fund_adj(ts_code=item["ts_code"], start_date=start_date, end_date=end_date)
                if raw_frame.empty or adj_frame.empty or adj_frame["adj_factor"].dropna().empty:
                    raise RuntimeError(f"ETF {item['code']} 缺少日线或复权因子")

                observed_base_factor = float(
                    adj_frame.sort_values("trade_date")["adj_factor"].dropna().iloc[-1]
                )
                state = connection.execute(
                    "SELECT qfq_base_factor, latest_trade_date FROM etf_adjustment_state WHERE code = ?",
                    (item["code"],),
                ).fetchone()
                stored_base_factor = float(state["qfq_base_factor"]) if state is not None else None
                stored_latest_trade_date = str(state["latest_trade_date"]) if state is not None else None
                is_historical_backfill = stored_latest_trade_date is not None and end_date < stored_latest_trade_date
                qfq_base_factor = (
                    float(stored_base_factor)
                    if is_historical_backfill and stored_base_factor is not None
                    else observed_base_factor
                )
                requires_full_rebase = not is_historical_backfill and (
                    stored_base_factor is None
                    or not math.isclose(
                        stored_base_factor,
                        qfq_base_factor,
                        rel_tol=1e-12,
                        abs_tol=1e-12,
                    )
                )

                sync_start_date = start_date
                if requires_full_rebase:
                    earliest_row = connection.execute(
                        "SELECT MIN(trade_date) AS first_trade_date FROM etf_daily_bar WHERE code = ?",
                        (item["code"],),
                    ).fetchone()
                    first_trade_date = earliest_row["first_trade_date"] if earliest_row is not None else None
                    if first_trade_date and first_trade_date < sync_start_date:
                        sync_start_date = str(first_trade_date)
                        raw_frame = pro.fund_daily(
                            ts_code=item["ts_code"],
                            start_date=sync_start_date,
                            end_date=end_date,
                        )
                        adj_frame = pro.fund_adj(
                            ts_code=item["ts_code"],
                            start_date=sync_start_date,
                            end_date=end_date,
                        )

                records = _build_qfq_fund_records(raw_frame, adj_frame, item, qfq_base_factor)
                if not records:
                    raise RuntimeError(f"ETF {item['code']} 无法构造前复权记录")

                if requires_full_rebase:
                    connection.execute("DELETE FROM etf_daily_bar WHERE code = ?", (item["code"],))
                _upsert_qfq_fund_records(connection, records)
                connection.execute(
                    """
                    INSERT INTO etf_adjustment_state (code, qfq_base_factor, latest_trade_date, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(code) DO UPDATE SET
                        qfq_base_factor = excluded.qfq_base_factor,
                        latest_trade_date = excluded.latest_trade_date,
                        updated_at = excluded.updated_at
                    """,
                    (
                        item["code"],
                        qfq_base_factor,
                        max(
                            max(record["trade_date"] for record in records),
                            stored_latest_trade_date or "",
                        ),
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                )
                connection.execute("RELEASE SAVEPOINT etf_item_sync")
                total_rows += len(records)
            except Exception:
                connection.execute("ROLLBACK TO SAVEPOINT etf_item_sync")
                connection.execute("RELEASE SAVEPOINT etf_item_sync")
                failed_codes.append(item["code"])

    return total_rows, failed_codes

def _insert_job_log(job_name: str, status: str, duration_ms: int, message: str) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO etl_job_log (job_name, run_time, status, duration_ms, message)
            VALUES (?, ?, ?, ?, ?)
            """,
            (job_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), status, duration_ms, message),
        )

def _get_open_trade_dates_before(selected_trade_api: str, limit: int) -> list[str]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT trade_date
            FROM trade_calendar
            WHERE is_open = 1 AND trade_date <= ?
            ORDER BY trade_date DESC
            LIMIT ?
            """,
            (selected_trade_api, limit),
        ).fetchall()
    return [row["trade_date"] for row in reversed(rows)]

def _is_trade_date_cached(selected_trade_date: str, codes: list[str] | None = None) -> bool:
    selected_trade_api = _date_to_api(selected_trade_date)
    open_dates = _get_open_trade_dates_before(selected_trade_api, 49)
    if len(open_dates) < 49:
        return False

    target_codes = codes if codes is not None else [item["code"] for item in _get_visible_etf_items()]
    if not target_codes:
        return False

    placeholders = ",".join("?" for _ in target_codes)
    params: list[Any] = [open_dates[0], selected_trade_api, *target_codes]
    with get_connection() as connection:
        row = connection.execute(
            f"""
            SELECT COUNT(*) AS row_count
            FROM etf_daily_bar
            WHERE trade_date BETWEEN ? AND ?
              AND code IN ({placeholders})
            """,
            params,
        ).fetchone()

    expected_rows = len(open_dates) * len(target_codes)
    return int(row["row_count"]) >= expected_rows

def ensure_trade_date_data(trade_date: str) -> dict[str, Any]:
    init_db()
    _upsert_etf_pool()

    selected_trade_api = _date_to_api(trade_date)
    visible_codes = [item["code"] for item in _get_visible_etf_items()]
    if _is_trade_date_cached(trade_date, codes=visible_codes):
        return {
            "trade_date": trade_date,
            "cache_hit": True,
            "written_rows": 0,
            "duration_ms": 0,
        }

    started = time.perf_counter()
    pro = _get_tushare_client()
    calendar_start = _shift_date(selected_trade_api, -420)
    open_dates = _sync_trade_calendar(pro, start_date=calendar_start, end_date=selected_trade_api)
    open_dates = [date for date in open_dates if date <= selected_trade_api]
    if len(open_dates) < 49:
        raise RuntimeError("所选交易日前可用交易日不足 49 个，无法计算 20 日斜率动量")

    data_start = open_dates[-80] if len(open_dates) >= 80 else open_dates[0]
    total_rows, failed_codes = _sync_fund_daily(pro, start_date=data_start, end_date=selected_trade_api)
    duration_ms = int((time.perf_counter() - started) * 1000)
    message = f"补齐 {trade_date} 所需数据，写入 {total_rows} 条日线数据"
    if failed_codes:
        message += f"，失败代码 {','.join(failed_codes)}"
    _insert_job_log("ensure_trade_date_data", "success", duration_ms, message)
    return {
        "trade_date": trade_date,
        "cache_hit": False,
        "written_rows": total_rows,
        "failed_codes": failed_codes,
        "duration_ms": duration_ms,
    }

def get_trade_date_status(trade_date: str) -> dict[str, Any]:
    init_db()
    visible_codes = [item["code"] for item in _get_visible_etf_items()]
    return {
        "trade_date": trade_date,
        "ready": _is_trade_date_cached(trade_date, codes=visible_codes),
    }

def get_etf_status(code: str, trade_date: str | None = None) -> dict[str, Any]:
    init_db()
    normalized_code = _normalize_etf_code(code)
    available_trade_dates = _get_display_available_trade_dates(AVAILABLE_TRADE_DATE_LIMIT)
    selected_trade_date = _resolve_selected_trade_date(trade_date, available_trade_dates)
    item = _get_etf_item(normalized_code)
    return {
        "code": normalized_code,
        "trade_date": selected_trade_date,
        "exists": item is not None,
        "ready": _is_trade_date_cached(selected_trade_date, codes=[normalized_code]) if item is not None else False,
    }

def ensure_etf_data(code: str, trade_date: str | None = None) -> dict[str, Any]:
    init_db()
    _upsert_etf_pool()

    normalized_code = _normalize_etf_code(code)
    available_trade_dates = _get_display_available_trade_dates(AVAILABLE_TRADE_DATE_LIMIT)
    selected_trade_date = _resolve_selected_trade_date(trade_date, available_trade_dates)
    item = _resolve_etf_item(normalized_code)
    if _is_trade_date_cached(selected_trade_date, codes=[normalized_code]):
        return {
            "code": normalized_code,
            "trade_date": selected_trade_date,
            "cache_hit": True,
            "written_rows": 0,
            "duration_ms": 0,
        }

    started = time.perf_counter()
    pro = _get_tushare_client()
    selected_trade_api = _date_to_api(selected_trade_date)
    calendar_start = _shift_date(selected_trade_api, -420)
    open_dates = _sync_trade_calendar(pro, start_date=calendar_start, end_date=selected_trade_api)
    open_dates = [date for date in open_dates if date <= selected_trade_api]
    if len(open_dates) < 49:
        raise RuntimeError("所选交易日前可用交易日不足 49 个，无法计算 20 日斜率动量")

    data_start = open_dates[-80] if len(open_dates) >= 80 else open_dates[0]
    total_rows, failed_codes = _sync_fund_daily(pro, start_date=data_start, end_date=selected_trade_api, items=[item])
    duration_ms = int((time.perf_counter() - started) * 1000)
    message = f"补齐 ETF {normalized_code} 在 {selected_trade_date} 所需数据，写入 {total_rows} 条日线数据"
    if failed_codes:
        message += f"，失败代码 {','.join(failed_codes)}"
    _insert_job_log("ensure_etf_data", "success", duration_ms, message)
    return {
        "code": normalized_code,
        "trade_date": selected_trade_date,
        "cache_hit": False,
        "written_rows": total_rows,
        "failed_codes": failed_codes,
        "duration_ms": duration_ms,
    }

def sync_dashboard_data() -> dict[str, Any]:
    init_db()
    _upsert_etf_pool()

    started = time.perf_counter()
    pro = _get_tushare_client()
    end_date = _today_str()
    start_date = (datetime.now() - timedelta(days=TRADE_CALENDAR_SYNC_DAYS)).strftime("%Y%m%d")

    try:
        open_dates = _sync_trade_calendar(pro, start_date=start_date, end_date=end_date)
        if len(open_dates) < 49:
            raise RuntimeError("交易日数量不足，无法生成 20 日斜率动量矩阵")

        latest_trade_date = open_dates[-1]
        latest_ui = _date_to_ui(latest_trade_date)
        if _is_trade_date_cached(latest_ui):
            duration_ms = int((time.perf_counter() - started) * 1000)
            message = f"最新交易日 {latest_ui} 数据已就绪，跳过日线拉取"
            _insert_job_log("sync_dashboard_data", "success", duration_ms, message)
            return {
                "latest_trade_date": latest_ui,
                "matrix_start_date": _date_to_ui(open_dates[-30]),
                "written_rows": 0,
                "failed_codes": [],
                "duration_ms": duration_ms,
                "cache_hit": True,
            }

        matrix_start = open_dates[-30]
        data_start = open_dates[-80] if len(open_dates) >= 80 else open_dates[0]
        total_rows, failed_codes = _sync_fund_daily(pro, start_date=data_start, end_date=open_dates[-1])
        duration_ms = int((time.perf_counter() - started) * 1000)
        message = f"同步完成，写入 {total_rows} 条日线数据"
        if failed_codes:
            message += f"，失败代码 {','.join(failed_codes)}"
        _insert_job_log("sync_dashboard_data", "success", duration_ms, message)
        return {
            "latest_trade_date": _date_to_ui(open_dates[-1]),
            "matrix_start_date": _date_to_ui(matrix_start),
            "written_rows": total_rows,
            "failed_codes": failed_codes,
            "duration_ms": duration_ms,
        }
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        _insert_job_log("sync_dashboard_data", "error", duration_ms, str(exc))
        raise

def _get_available_trade_dates(limit: int = 240) -> list[str]:
    _ensure_trade_calendar_date(_today_str())
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT trade_date
            FROM trade_calendar
            WHERE is_open = 1
            ORDER BY trade_date DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_date_to_ui(row["trade_date"]) for row in rows]

def _get_latest_official_trade_date() -> str | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT MAX(trade_date) AS latest_trade_date
            FROM etf_daily_bar
            """
        ).fetchone()
    if row is None or row["latest_trade_date"] is None:
        return None
    return _date_to_ui(row["latest_trade_date"])

def _ensure_trade_calendar_date(trade_date_api: str) -> None:
    if trade_date_api in _TRADE_CALENDAR_REFRESHED_DATES:
        return
    if not settings.tushare_token:
        return

    pro = _get_tushare_client()
    calendar = pro.trade_cal(exchange="SSE", start_date=trade_date_api, end_date=trade_date_api, fields="cal_date,is_open")
    if calendar.empty:
        return

    rows = calendar.to_dict("records")
    with get_connection() as connection:
        connection.executemany(
            """
            INSERT INTO trade_calendar (trade_date, is_open)
            VALUES (:cal_date, :is_open)
            ON CONFLICT(trade_date) DO UPDATE SET is_open = excluded.is_open
            """,
            rows,
        )
    _TRADE_CALENDAR_REFRESHED_DATES.add(trade_date_api)

def _should_show_sync_today_button(available_trade_dates: list[str] | None = None) -> bool:
    raw_available_trade_dates = available_trade_dates or _get_available_trade_dates(AVAILABLE_TRADE_DATE_LIMIT)
    if is_market_session_time():
        return False
    if not raw_available_trade_dates:
        return False

    today_trade_date = _date_to_ui(_today_str())
    if today_trade_date not in raw_available_trade_dates:
        return False

    latest_official_trade_date = _get_latest_official_trade_date()
    if latest_official_trade_date is None:
        return True

    return latest_official_trade_date < today_trade_date

def _should_hide_today_trade_date(available_trade_dates: list[str]) -> bool:
    if is_market_session_time():
        return False
    if not available_trade_dates:
        return False

    today_trade_date = _date_to_ui(_today_str())
    if today_trade_date not in available_trade_dates:
        return False

    latest_official_trade_date = _get_latest_official_trade_date()
    if latest_official_trade_date is None:
        return True

    return latest_official_trade_date < today_trade_date

def _get_display_available_trade_dates(limit: int = AVAILABLE_TRADE_DATE_LIMIT) -> list[str]:
    available_trade_dates = _get_available_trade_dates(limit)
    if _should_hide_today_trade_date(available_trade_dates):
        return available_trade_dates[1:]
    return available_trade_dates

def _resolve_selected_trade_date(
    trade_date: str | None,
    available_trade_dates: list[str] | None = None,
) -> str:
    candidate_trade_dates = available_trade_dates or _get_display_available_trade_dates(AVAILABLE_TRADE_DATE_LIMIT)
    if not candidate_trade_dates:
        raise RuntimeError("本地数据库暂无 ETF 数据，请先执行同步")
    return trade_date if trade_date in candidate_trade_dates else candidate_trade_dates[0]

def get_latest_job() -> dict[str, Any]:
    init_db()
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT job_name, run_time, status, duration_ms, message
            FROM etl_job_log
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    if row is None:
        return {"job_name": "sync_dashboard_data", "status": "idle", "run_time": None, "duration_ms": 0, "message": "尚未执行同步"}

    return dict(row)


def _compute_pool_ranks(rows: list[dict[str, Any]]) -> None:
    """对全池（过滤前）每个交易日按 20 日斜率动量降序计算名次与 P1–P10 档位。

    名次 rank=1 表示当日动量最强；档位 tier 由 rank 在横截面中等分为 10 档，
    最强动量归入 P10、最弱归入 P1，与策略口径一致。排名必须在分组/关键词过滤之前完成，
    保证名次反映全市场位置（过滤只在展示层生效）。单只检索或样本不足(n<2)时置 null。
    """
    if not rows:
        return

    all_dates: set[str] = set()
    for row in rows:
        all_dates.update(row.get("dailyMatrix", {}).keys())

    for trade_date in sorted(all_dates):
        entries = [
            (row, row["dailyMatrix"].get(trade_date))
            for row in rows
            if isinstance(row.get("dailyMatrix", {}).get(trade_date), (int, float))
            and math.isfinite(row["dailyMatrix"][trade_date])
        ]
        n = len(entries)
        for row in rows:
            row.setdefault("dailyRank", {})[trade_date] = None
            row.setdefault("dailyTier", {})[trade_date] = None
        if n < 2:
            continue
        entries.sort(key=lambda item: (-item[1], item[0]["fullCode"]))
        for idx, (row, _value) in enumerate(entries):
            rank = idx + 1
            tier_index = 10 - min(9, (rank - 1) * 10 // n)
            row["dailyRank"][trade_date] = rank
            row["dailyTier"][trade_date] = f"P{tier_index}"


def build_dashboard_payload(
    trade_date: str | None = None,
    group_name: str | None = None,
    keyword: str | None = None,
    code: str | None = None,
) -> dict[str, Any]:
    init_db()
    raw_available_trade_dates = _get_available_trade_dates(AVAILABLE_TRADE_DATE_LIMIT)
    available_trade_dates = _get_display_available_trade_dates(AVAILABLE_TRADE_DATE_LIMIT)
    if not raw_available_trade_dates or not available_trade_dates:
        raise RuntimeError("本地数据库暂无 ETF 数据，请先执行同步")

    explicit_trade_date = trade_date is not None
    selected_trade_date = trade_date if trade_date in available_trade_dates else available_trade_dates[0]
    selected_trade_api = _date_to_api(selected_trade_date)
    intraday_trade_date = _date_to_ui(_today_str())

    selected_code = _normalize_etf_code(code) if code else None

    with get_connection() as connection:
        display_window_rows = connection.execute(
            """
            SELECT trade_date
            FROM trade_calendar
            WHERE is_open = 1 AND trade_date <= ?
            ORDER BY trade_date DESC
            LIMIT 30
            """,
            (selected_trade_api,),
        ).fetchall()
        trade_dates = [_date_to_ui(row["trade_date"]) for row in reversed(display_window_rows)]
        if len(trade_dates) < 30:
            raise RuntimeError("交易日窗口不足 30 个，无法生成看板")

        slope_window_rows = connection.execute(
            """
            SELECT trade_date
            FROM trade_calendar
            WHERE is_open = 1 AND trade_date <= ?
            ORDER BY trade_date DESC
            LIMIT 49
            """,
            (selected_trade_api,),
        ).fetchall()
        slope_trade_dates = [_date_to_ui(row["trade_date"]) for row in reversed(slope_window_rows)]
        if len(slope_trade_dates) < 49:
            raise RuntimeError("交易日窗口不足 49 个，无法计算 20 日斜率动量")

        if selected_code:
            bars = connection.execute(
                """
                SELECT
                    p.name,
                    p.code,
                    p.full_code,
                    p.group_name,
                    p.market,
                    b.trade_date,
                    b.close
                FROM etf_pool p
                LEFT JOIN etf_daily_bar b
                    ON p.code = b.code
                    AND b.trade_date BETWEEN ? AND ?
                WHERE p.code = ?
                ORDER BY p.code ASC, b.trade_date ASC
                """,
                (_date_to_api(slope_trade_dates[0]), selected_trade_api, selected_code),
            ).fetchall()
        else:
            bars = connection.execute(
                """
                SELECT
                    p.name,
                    p.code,
                    p.full_code,
                    p.group_name,
                    p.market,
                    b.trade_date,
                    b.close
                FROM etf_pool p
                LEFT JOIN etf_daily_bar b
                    ON p.code = b.code
                    AND b.trade_date BETWEEN ? AND ?
                WHERE p.is_visible = 1
                ORDER BY p.code ASC, b.trade_date ASC
                """,
                (_date_to_api(slope_trade_dates[0]), selected_trade_api),
            ).fetchall()

    grouped: dict[str, dict[str, Any]] = {}
    for row in bars:
        code = row["code"]
        if code not in grouped:
            grouped[code] = {
                "name": row["name"],
                "code": row["code"],
                "fullCode": row["full_code"],
                "group": row["group_name"],
                "market": row["market"],
                "latestClose": None,
                "dailyMatrix": {date: None for date in trade_dates},
                "closeMap": {},
                "status": "success",
                "latestPriceSource": "official",
                "latestPriceTime": None,
            }

        if row["trade_date"]:
            ui_trade_date = _date_to_ui(row["trade_date"])
            grouped[code]["closeMap"][ui_trade_date] = float(row["close"])
            if ui_trade_date == selected_trade_date:
                grouped[code]["latestClose"] = float(row["close"])

    realtime_snapshot_map, realtime_status = get_realtime_dashboard_context(
        list(grouped.keys()),
        selected_trade_date,
        explicit_trade_date,
    )
    display_trade_dates = trade_dates
    payload_trade_date = selected_trade_date
    if realtime_status["active"] and trade_dates:
        if trade_dates[-1] == intraday_trade_date:
            display_trade_dates = trade_dates
        else:
            display_trade_dates = [*trade_dates[1:], intraday_trade_date]
        payload_trade_date = intraday_trade_date

    rows: list[dict[str, Any]] = []
    for item in grouped.values():
        ordered_closes = [item["closeMap"].get(trade_date_item) for trade_date_item in slope_trade_dates]
        for end_index in range(19, len(slope_trade_dates)):
            metric_trade_date = slope_trade_dates[end_index]
            if metric_trade_date not in item["dailyMatrix"]:
                continue

            window_closes = ordered_closes[end_index - 19 : end_index + 1]
            if any(close is None for close in window_closes):
                item["dailyMatrix"][metric_trade_date] = None
                continue

            item["dailyMatrix"][metric_trade_date] = calc_slope_momentum_from_closes(window_closes)  # type: ignore[arg-type]

        if realtime_status["active"] and trade_dates:
            if trade_dates[-1] != intraday_trade_date:
                item["dailyMatrix"].pop(trade_dates[0], None)
            item["dailyMatrix"][intraday_trade_date] = None
            realtime_snapshot = realtime_snapshot_map.get(item["code"])
            if realtime_snapshot is not None:
                history_closes = [close for trade_date_item, close in zip(slope_trade_dates, ordered_closes) if trade_date_item < intraday_trade_date]
                realtime_window_closes = history_closes[-19:] + [realtime_snapshot.last_price]
                if len(realtime_window_closes) == 20 and all(close is not None for close in realtime_window_closes):
                    item["dailyMatrix"][intraday_trade_date] = calc_slope_momentum_from_closes(realtime_window_closes)  # type: ignore[arg-type]
                item["latestClose"] = realtime_snapshot.last_price
                item["latestPriceSource"] = "realtime"
                item["latestPriceTime"] = realtime_snapshot.quote_time

        item.pop("closeMap", None)
        if item["latestClose"] is None:
            item["status"] = "missing"
            item["latestClose"] = 0.0
        rows.append(item)

    _compute_pool_ranks(rows)
    pool_size = len(rows)

    if selected_code and not rows:
        raise RuntimeError(f"未找到 ETF 代码 {selected_code} 对应的数据，请先执行补数")

    if group_name and group_name != "全部":
        rows = [row for row in rows if row["group"] == group_name]

    if keyword:
        clean_keyword = keyword.strip()
        if clean_keyword:
            rows = [
                row
                for row in rows
                if clean_keyword in row["name"] or clean_keyword in row["code"] or clean_keyword in row["fullCode"]
            ]

    updated_at = get_latest_job()["run_time"]
    latest_official_trade_date = _get_latest_official_trade_date()
    return {
        "tradeDate": payload_trade_date,
        "tradeDates": display_trade_dates,
        "availableTradeDates": available_trade_dates,
        "latestOfficialTradeDate": latest_official_trade_date,
        "showSyncTodayButton": _should_show_sync_today_button(raw_available_trade_dates),
        "updatedAt": updated_at,
        "metricName": "20日斜率动量",
        "selectedCode": selected_code,
        "realtime": realtime_status,
        "poolSize": pool_size,
        "rows": rows,
    }

def build_export_file(
    trade_date: str | None = None,
    group_name: str | None = None,
    keyword: str | None = None,
    code: str | None = None,
) -> tuple[str, BytesIO]:
    payload = build_dashboard_payload(trade_date=trade_date, group_name=group_name, keyword=keyword, code=code)
    rows = []
    for row in payload["rows"]:
        export_row: dict[str, Any] = {
            "名称": row["name"],
            "代码": row["code"],
            "聚宽代码": row["fullCode"],
        }
        for trade_date_item in payload["tradeDates"]:
            export_row[trade_date_item] = row["dailyMatrix"][trade_date_item]
        export_row["名次"] = row.get("dailyRank", {}).get(payload["tradeDate"])
        export_row["档位"] = row.get("dailyTier", {}).get(payload["tradeDate"])
        rows.append(export_row)

    frame = pd.DataFrame(rows)
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        frame.to_excel(writer, index=False, sheet_name="ETF主看板")
    buffer.seek(0)
    file_name = f"ETF主流看板_{payload['tradeDate']}.xlsx"
    return file_name, buffer
