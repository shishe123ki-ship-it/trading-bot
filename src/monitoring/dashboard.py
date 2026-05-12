from __future__ import annotations

import os
from pathlib import Path

import aiosqlite
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

DB_PATH = Path(os.environ.get("DASHBOARD_DB_PATH", "data/portfolio.db"))
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


@app.get("/stream")
async def log_stream() -> StreamingResponse:
    async def generator():
        yield "data: Dashboard verbunden\n\n"
    return StreamingResponse(generator(), media_type="text/event-stream")
