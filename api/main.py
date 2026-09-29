from __future__ import annotations

from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from api.config import settings
from api.service import (
    build_dashboard_payload,
    build_export_file,
    ensure_etf_data,
    ensure_trade_date_data,
    get_etf_status,
    get_trade_date_status,
    get_latest_job,
    sync_dashboard_data,
)


def _ensure_token() -> None:
    if not settings.tushare_token:
        raise HTTPException(status_code=500, detail="未配置 TUSHARE_TOKEN")


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        _ensure_token()
        sync_dashboard_data()
    except Exception:
        # 启动时允许失败，前端可通过健康检查与手动同步感知状态。
        pass
    yield


app = FastAPI(title="ETF 主流看板 API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    latest_job = get_latest_job()
    status = "ok" if latest_job["status"] in {"success", "idle"} else "error"
    latest_trade_date = None
    try:
        latest_trade_date = build_dashboard_payload()["tradeDate"]
    except Exception:
        latest_trade_date = None

    return {
        "status": status,
        "latest_trade_date": latest_trade_date,
        "latest_job_status": latest_job["status"],
        "latest_job_time": latest_job["run_time"],
        "message": latest_job["message"],
    }


@app.post("/api/admin/sync")
def sync_dashboard():
    _ensure_token()
    try:
        return sync_dashboard_data()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/jobs/latest")
def latest_job():
    return get_latest_job()


@app.get("/api/trade-date-status")
def trade_date_status(
    trade_date: str = Query(...),
):
    try:
        return get_trade_date_status(trade_date)
    except Exception:
        return {
            "trade_date": trade_date,
            "ready": False,
        }


@app.post("/api/admin/ensure-trade-date")
def ensure_trade_date(
    trade_date: str = Query(...),
):
    _ensure_token()
    try:
        return ensure_trade_date_data(trade_date)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/etf-status")
def etf_status(
    code: str = Query(...),
    trade_date: str | None = Query(default=None),
):
    try:
        return get_etf_status(code, trade_date)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/admin/ensure-etf")
def ensure_etf(
    code: str = Query(...),
    trade_date: str | None = Query(default=None),
):
    _ensure_token()
    try:
        return ensure_etf_data(code, trade_date)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/dashboard")
def dashboard(
    trade_date: str | None = Query(default=None),
    group_name: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    code: str | None = Query(default=None),
):
    try:
        return build_dashboard_payload(trade_date=trade_date, group_name=group_name, keyword=keyword, code=code)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/export")
def export_dashboard(
    trade_date: str | None = Query(default=None),
    group_name: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    code: str | None = Query(default=None),
):
    try:
        file_name, buffer = build_export_file(trade_date=trade_date, group_name=group_name, keyword=keyword, code=code)
        quoted_file_name = quote(file_name)
        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename=etf_dashboard.xlsx; filename*=UTF-8''{quoted_file_name}"
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
