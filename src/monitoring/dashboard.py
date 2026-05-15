from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

DB_PATH = Path(os.environ.get("DASHBOARD_DB_PATH", "data/portfolio.db"))
INITIAL_CAPITAL = float(os.environ.get("DASHBOARD_INITIAL_CAPITAL", "250.0"))
_TEMPLATES_DIR = Path(__file__).parent / "templates"

app = FastAPI(title="Trading Bot Dashboard")
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


@app.get("/api/portfolio")
async def portfolio() -> dict:
    if not DB_PATH.exists():
        return {"open_positions": 0, "realized_pnl": 0.0}
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM positions")
        row = await cursor.fetchone()
        positions = row[0] if row else 0
        cursor = await db.execute("SELECT COALESCE(SUM(fee), 0.0) FROM trades")
        row = await cursor.fetchone()
        total_fees = row[0] if row else 0.0
    return {"open_positions": positions, "realized_pnl": round(-total_fees, 4)}


@app.get("/api/trades")
async def trades(limit: int = 50) -> list:
    if not DB_PATH.exists():
        return []
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


@app.get("/partials/portfolio", response_class=HTMLResponse)
async def portfolio_partial(request: Request) -> HTMLResponse:
    data = await portfolio()
    return templates.TemplateResponse(request, "partials/portfolio.html", data)


@app.get("/partials/trades", response_class=HTMLResponse)
async def trades_partial(request: Request) -> HTMLResponse:
    trade_list = await trades(limit=20)
    return templates.TemplateResponse(
        request, "partials/trades.html", {"trades": trade_list}
    )


@app.get("/api/equity")
async def equity() -> list[dict]:
    if not DB_PATH.exists():
        return []
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT timestamp, fee FROM trades ORDER BY timestamp ASC"
        )
        rows = await cursor.fetchall()
    result = []
    running_equity = INITIAL_CAPITAL
    for row in rows:
        running_equity -= row["fee"]
        result.append({"timestamp": row["timestamp"], "equity": round(running_equity, 4)})
    return result


@app.get("/api/strategies")
async def strategies_summary() -> list[dict]:
    if not DB_PATH.exists():
        return []
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT strategy_id, COUNT(*) as trade_count FROM trades GROUP BY strategy_id"
        )
        trade_rows = {row["strategy_id"]: row["trade_count"] for row in await cursor.fetchall()}

        try:
            cursor = await db.execute(
                "SELECT strategy_id, enabled FROM strategy_overrides"
            )
            override_rows = await cursor.fetchall()
        except Exception:
            override_rows = []

    result = [
        {
            "strategy_id": row["strategy_id"],
            "trade_count": trade_rows.get(row["strategy_id"], 0),
            "enabled": bool(row["enabled"]),
        }
        for row in override_rows
    ]

    if not result:
        result = [
            {"strategy_id": sid, "trade_count": count, "enabled": True}
            for sid, count in trade_rows.items()
        ]

    return result


@app.get("/api/status")
async def bot_status_api() -> dict:
    if not DB_PATH.exists():
        return {"connected": False, "last_seen": None}
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        try:
            cursor = await db.execute(
                "SELECT timestamp, ws_connected FROM bot_status WHERE id=1"
            )
            row = await cursor.fetchone()
        except Exception:
            return {"connected": False, "last_seen": None}
    if row is None:
        return {"connected": False, "last_seen": None}
    last_seen: str = row["timestamp"]
    try:
        dt = datetime.fromisoformat(last_seen)
        age = (datetime.now(timezone.utc) - dt).total_seconds()
        connected = row["ws_connected"] == 1 and age < 60
    except Exception:
        connected = False
    return {"connected": connected, "last_seen": last_seen}


@app.get("/partials/status", response_class=HTMLResponse)
async def status_partial(request: Request) -> HTMLResponse:
    data = await bot_status_api()
    return templates.TemplateResponse(request, "partials/status.html", data)


@app.post("/api/strategies/{strategy_id}/toggle", response_class=HTMLResponse)
async def toggle_strategy(request: Request, strategy_id: str) -> HTMLResponse:
    if not DB_PATH.exists():
        return HTMLResponse(
            f'<tr id="strategy-{strategy_id}"><td colspan="3">DB nicht gefunden</td></tr>'
        )
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT enabled FROM strategy_overrides WHERE strategy_id=?",
            (strategy_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return HTMLResponse(
                f'<tr id="strategy-{strategy_id}"><td colspan="3">Nicht gefunden</td></tr>'
            )
        new_enabled = 0 if row["enabled"] else 1
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "UPDATE strategy_overrides SET enabled=?, updated_at=? WHERE strategy_id=?",
            (new_enabled, now, strategy_id),
        )
        await db.commit()
        cursor = await db.execute(
            "SELECT COUNT(*) FROM trades WHERE strategy_id=?", (strategy_id,)
        )
        count_row = await cursor.fetchone()
        trade_count = count_row[0] if count_row else 0

    return templates.TemplateResponse(
        request,
        "partials/strategy_row.html",
        {
            "strategy_id": strategy_id,
            "enabled": bool(new_enabled),
            "trade_count": trade_count,
        },
    )


@app.get("/partials/strategies", response_class=HTMLResponse)
async def strategies_partial(request: Request) -> HTMLResponse:
    data = await strategies_summary()
    return templates.TemplateResponse(
        request, "partials/strategies.html", {"strategies": data}
    )


@app.get("/stream")
async def log_stream() -> StreamingResponse:
    async def generator():
        yield "data: Dashboard verbunden\n\n"
    return StreamingResponse(generator(), media_type="text/event-stream")
