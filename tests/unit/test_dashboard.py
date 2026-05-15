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


@pytest.fixture
def temp_db_multi(tmp_path) -> Path:
    """DB mit 2 Trades fuer Equity-Kumulations-Test."""
    db_path = tmp_path / "test_multi.db"
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
    conn.execute("INSERT INTO trades VALUES (1,'O1','BTCUSDT','Buy',0.001,50000,0.027,'ema_cross','2024-01-01T10:00:00')")
    conn.execute("INSERT INTO trades VALUES (2,'O2','ETHUSDT','Buy',0.01,3000,0.054,'rsi','2024-01-01T11:00:00')")
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
async def client_multi(temp_db_multi):
    original = dashboard_module.DB_PATH
    dashboard_module.DB_PATH = temp_db_multi
    from src.monitoring.dashboard import app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
    dashboard_module.DB_PATH = original


async def test_equity_api_returns_list(client):
    resp = await client.get("/api/equity")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert "timestamp" in data[0]
    assert "equity" in data[0]


async def test_equity_api_empty_db(tmp_path):
    original = dashboard_module.DB_PATH
    dashboard_module.DB_PATH = tmp_path / "nonexistent.db"
    from src.monitoring.dashboard import app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        resp = await c.get("/api/equity")
    dashboard_module.DB_PATH = original
    assert resp.status_code == 200
    assert resp.json() == []


async def test_equity_cumulative_sum(client_multi):
    resp = await client_multi.get("/api/equity")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["equity"] == pytest.approx(250.0 - 0.027, abs=0.001)
    assert data[1]["equity"] == pytest.approx(250.0 - 0.027 - 0.054, abs=0.001)


async def test_strategies_api_returns_list(client):
    resp = await client.get("/api/strategies")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["strategy_id"] == "ema_cross"
    assert data[0]["trade_count"] == 1


async def test_strategies_api_groups_by_strategy(client_multi):
    resp = await client_multi.get("/api/strategies")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    ids = {d["strategy_id"] for d in data}
    assert ids == {"ema_cross", "rsi"}


async def test_strategies_partial_returns_html(client):
    resp = await client.get("/partials/strategies")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


import sqlite3 as _sqlite3


@pytest.fixture
def temp_db_full(tmp_path) -> Path:
    """DB mit allen 4 Tabellen inkl. bot_status und strategy_overrides."""
    db_path = tmp_path / "test_full.db"
    conn = _sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT, symbol TEXT, side TEXT,
            qty REAL, avg_price REAL, fee REAL,
            strategy_id TEXT, timestamp TEXT
        );
        CREATE TABLE positions (
            symbol TEXT PRIMARY KEY, side TEXT, qty REAL,
            entry_price REAL, strategy_id TEXT, opened_at TEXT
        );
        CREATE TABLE bot_status (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            timestamp TEXT NOT NULL,
            ws_connected INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE strategy_overrides (
            strategy_id TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL
        );
    """)
    conn.execute(
        "INSERT INTO trades VALUES "
        "(1,'O1','BTCUSDT','Buy',0.001,50000,0.027,'ema_cross','2024-01-01T10:00:00')"
    )
    conn.execute(
        "INSERT INTO strategy_overrides VALUES "
        "('ema_cross', 1, '2024-01-01T10:00:00')"
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
async def client_full(temp_db_full):
    original = dashboard_module.DB_PATH
    dashboard_module.DB_PATH = temp_db_full
    from src.monitoring.dashboard import app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
    dashboard_module.DB_PATH = original


async def test_status_api_no_db(tmp_path):
    original = dashboard_module.DB_PATH
    dashboard_module.DB_PATH = tmp_path / "nonexistent.db"
    from src.monitoring.dashboard import app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        resp = await c.get("/api/status")
    dashboard_module.DB_PATH = original
    assert resp.status_code == 200
    assert resp.json()["connected"] is False


async def test_status_api_connected(client_full, temp_db_full):
    from datetime import datetime, timezone as tz
    now = datetime.now(tz.utc).isoformat()
    conn = _sqlite3.connect(temp_db_full)
    conn.execute("INSERT OR REPLACE INTO bot_status VALUES (1, ?, 1)", (now,))
    conn.commit()
    conn.close()

    resp = await client_full.get("/api/status")
    assert resp.status_code == 200
    assert resp.json()["connected"] is True


async def test_status_api_stale(client_full, temp_db_full):
    conn = _sqlite3.connect(temp_db_full)
    conn.execute(
        "INSERT OR REPLACE INTO bot_status VALUES (1, ?, 1)",
        ("2020-01-01T00:00:00+00:00",),
    )
    conn.commit()
    conn.close()

    resp = await client_full.get("/api/status")
    assert resp.status_code == 200
    assert resp.json()["connected"] is False


async def test_toggle_strategy_disables(client_full):
    resp = await client_full.post("/api/strategies/ema_cross/toggle")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "⬜" in resp.text


async def test_toggle_strategy_twice_re_enables(client_full):
    await client_full.post("/api/strategies/ema_cross/toggle")
    resp = await client_full.post("/api/strategies/ema_cross/toggle")
    assert "✅" in resp.text
