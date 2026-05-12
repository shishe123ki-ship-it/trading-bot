import pytest
import sqlite3
import httpx
from pathlib import Path
import src.monitoring.dashboard as dashboard_module


@pytest.fixture
def temp_db(tmp_path) -> Path:
    """Legt eine temporäre SQLite-DB mit Schema + einem Testdatensatz an."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT, symbol TEXT, side TEXT,
            qty REAL, avg_price REAL, fee REAL,
            strategy_id TEXT, timestamp TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE positions (
            symbol TEXT PRIMARY KEY, side TEXT, qty REAL,
            entry_price REAL, strategy_id TEXT, opened_at TEXT
        )
    """)
    conn.execute(
        "INSERT INTO trades VALUES "
        "(1,'O1','BTCUSDT','Buy',0.001,50000,0.027,'ema_cross','2024-01-01T10:00:00')"
    )
    conn.execute(
        "INSERT INTO positions VALUES "
        "('BTCUSDT','Buy',0.001,50000,'ema_cross','2024-01-01T10:00:00')"
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
async def client(temp_db):
    """httpx.AsyncClient mit ASGI-Transport gegen das Dashboard."""
    original = dashboard_module.DB_PATH
    dashboard_module.DB_PATH = temp_db
    from src.monitoring.dashboard import app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
    dashboard_module.DB_PATH = original


async def test_index_returns_200(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "Trading Bot" in resp.text


async def test_portfolio_api_returns_json(client):
    resp = await client.get("/api/portfolio")
    assert resp.status_code == 200
    data = resp.json()
    assert "open_positions" in data
    assert "realized_pnl" in data
    assert data["open_positions"] == 1


async def test_trades_api_returns_list(client):
    resp = await client.get("/api/trades")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["symbol"] == "BTCUSDT"


async def test_trades_api_limit_param(client):
    resp = await client.get("/api/trades?limit=5")
    assert resp.status_code == 200
    assert len(resp.json()) <= 5


async def test_portfolio_partial_returns_html(client):
    resp = await client.get("/partials/portfolio")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


async def test_trades_partial_returns_html(client):
    resp = await client.get("/partials/trades")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
