# Dashboard Live-Steuerung Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verbindungsstatus (grün/rot) und Strategie-Toggle (sofort wirksam, ~30s) ins Dashboard integrieren — via SQLite als IPC-Brücke zwischen Bot und Dashboard.

**Architecture:** Zwei neue SQLite-Tabellen (`bot_status`, `strategy_overrides`) in der bestehenden `portfolio.db`. Der Bot schreibt alle 10s einen Heartbeat und liest alle 30s die Overrides. Das Dashboard schreibt Toggles und zeigt den Status per HTMX-Partials.

**Tech Stack:** Python 3.12, aiosqlite, FastAPI, HTMX, Jinja2

---

## Dateiübersicht

| Datei | Aktion | Was ändert sich |
|---|---|---|
| `src/portfolio/tracker.py` | Modify | 2 neue `CREATE TABLE IF NOT EXISTS` in `_SCHEMA` |
| `src/data/feed.py` | Modify | `_connected: bool` Attribut + `connected` Property |
| `src/main.py` | Modify | `import aiosqlite`, 3 neue Hilfsfunktionen, Background-Tasks, `_dispatch_candle` prüft enabled |
| `src/monitoring/dashboard.py` | Modify | `from datetime import datetime, timezone`, 3 neue Endpoints, `strategies_summary()` liest aus `strategy_overrides` |
| `src/monitoring/templates/partials/status.html` | Create | Verbindungsanzeige (grün/rot) |
| `src/monitoring/templates/partials/strategy_row.html` | Create | Einzelne Strategie-Zeile mit Toggle-Button |
| `src/monitoring/templates/partials/strategies.html` | Modify | Toggle-Button pro Zeile, neue Spalte |
| `src/monitoring/templates/index.html` | Modify | Status-Bereich im Header |
| `tests/unit/test_portfolio_tracker.py` | Modify | 2 neue Tests für neue Tabellen |
| `tests/unit/test_feed.py` | Create | 1 Test für `connected` Property |
| `tests/unit/test_main_helpers.py` | Create | 4 Tests für Hilfsfunktionen in main.py |
| `tests/unit/test_dashboard.py` | Modify | `temp_db_full` Fixture + 5 neue Tests |

---

### Task 1: DB-Schema — neue Tabellen in tracker.py

**Files:**
- Modify: `src/portfolio/tracker.py:14-35`
- Test: `tests/unit/test_portfolio_tracker.py`

- [ ] **Schritt 1: Zwei neue Tests schreiben (FAIL erwartet)**

Ans Ende von `tests/unit/test_portfolio_tracker.py` anhängen:

```python
async def test_creates_bot_status_table(tracker):
    cursor = await tracker._db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='bot_status'"
    )
    row = await cursor.fetchone()
    assert row is not None


async def test_creates_strategy_overrides_table(tracker):
    cursor = await tracker._db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='strategy_overrides'"
    )
    row = await cursor.fetchone()
    assert row is not None
```

- [ ] **Schritt 2: Tests ausführen — FAIL bestätigen**

```
pytest tests/unit/test_portfolio_tracker.py::test_creates_bot_status_table tests/unit/test_portfolio_tracker.py::test_creates_strategy_overrides_table -v
```

Erwartet: 2× FAILED (Tabellen existieren noch nicht)

- [ ] **Schritt 3: `_SCHEMA` in tracker.py erweitern**

`src/portfolio/tracker.py`, Zeile 35 — nach dem letzten `"""` der `_SCHEMA`-Konstante, aber VOR dem schließenden `"""`:

```python
_SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    side        TEXT NOT NULL,
    qty         REAL NOT NULL,
    avg_price   REAL NOT NULL,
    fee         REAL NOT NULL,
    strategy_id TEXT NOT NULL,
    timestamp   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
    symbol      TEXT PRIMARY KEY,
    side        TEXT NOT NULL,
    qty         REAL NOT NULL,
    entry_price REAL NOT NULL,
    strategy_id TEXT NOT NULL,
    opened_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bot_status (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    timestamp    TEXT    NOT NULL,
    ws_connected INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS strategy_overrides (
    strategy_id TEXT    PRIMARY KEY,
    enabled     INTEGER NOT NULL DEFAULT 1,
    updated_at  TEXT    NOT NULL
);
"""
```

- [ ] **Schritt 4: Tests ausführen — alle PASS**

```
pytest tests/unit/test_portfolio_tracker.py -v
```

Erwartet: 10 passed

- [ ] **Schritt 5: Commit**

```bash
git add src/portfolio/tracker.py tests/unit/test_portfolio_tracker.py
git commit -m "feat: add bot_status and strategy_overrides tables to portfolio DB"
```

---

### Task 2: `connected` Property auf BybitFeed

**Files:**
- Modify: `src/data/feed.py`
- Create: `tests/unit/test_feed.py`

- [ ] **Schritt 1: Test schreiben (FAIL erwartet)**

Neue Datei `tests/unit/test_feed.py`:

```python
from src.data.feed import BybitFeed
from src.core.event_bus import EventBus


def test_feed_initially_not_connected():
    feed = BybitFeed(EventBus(), testnet=True)
    assert feed.connected is False
```

- [ ] **Schritt 2: Test ausführen — FAIL bestätigen**

```
pytest tests/unit/test_feed.py -v
```

Erwartet: FAILED (AttributeError: 'BybitFeed' has no attribute 'connected')

- [ ] **Schritt 3: `_connected` Attribut und Property zu BybitFeed hinzufügen**

`src/data/feed.py` — vollständige neue Version:

```python
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog
from pybit.unified_trading import WebSocket

from src.core.event_bus import EventBus
from src.core.types import Candle, Event, EventType

log = structlog.get_logger(__name__)


class BybitFeed:
    def __init__(self, event_bus: EventBus, testnet: bool = True) -> None:
        self._bus = event_bus
        self._testnet = testnet
        self._ws: WebSocket | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscriptions: list[tuple[str, str]] = []
        self._connected: bool = False

    @property
    def connected(self) -> bool:
        return self._connected

    def subscribe(self, symbol: str, interval: str) -> None:
        self._subscriptions.append((symbol, interval))

    def _handle_kline(self, message: dict) -> None:
        """Synchroner WebSocket-Callback — Thread-safe Weiterleitung an asyncio."""
        topic: str = message.get("topic", "")
        data_list: list[dict] = message.get("data", [])

        for item in data_list:
            if not item.get("confirm", False):
                continue

            parts = topic.split(".")
            interval = parts[1] if len(parts) == 3 else "1"
            symbol = parts[2] if len(parts) == 3 else "UNKNOWN"

            candle = Candle(
                symbol=symbol,
                interval=interval,
                open_time=datetime.fromtimestamp(
                    item["start"] / 1000, tz=timezone.utc
                ),
                open=float(item["open"]),
                high=float(item["high"]),
                low=float(item["low"]),
                close=float(item["close"]),
                volume=float(item["volume"]),
                is_closed=True,
            )

            if self._loop and not self._loop.is_closed():
                asyncio.run_coroutine_threadsafe(
                    self._bus.publish(
                        Event(type=EventType.CANDLE_CLOSED, data=candle)
                    ),
                    self._loop,
                )

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._ws = WebSocket(
            testnet=self._testnet,
            channel_type="linear",
        )
        for symbol, interval in self._subscriptions:
            self._ws.kline_stream(
                interval=int(interval),
                symbol=symbol,
                callback=self._handle_kline,
            )
            log.info("feed_subscribed", symbol=symbol, interval=interval)
        self._connected = True
        log.info("feed_started", testnet=self._testnet)

    async def stop(self) -> None:
        if self._ws:
            self._ws.exit()
        self._connected = False
        log.info("feed_stopped")
```

- [ ] **Schritt 4: Test ausführen — PASS**

```
pytest tests/unit/test_feed.py -v
```

Erwartet: 1 passed

- [ ] **Schritt 5: Commit**

```bash
git add src/data/feed.py tests/unit/test_feed.py
git commit -m "feat: add connected property to BybitFeed"
```

---

### Task 3: Hilfsfunktionen und Background-Tasks in main.py

**Files:**
- Modify: `src/main.py`
- Create: `tests/unit/test_main_helpers.py`

- [ ] **Schritt 1: Tests schreiben (FAIL erwartet)**

Neue Datei `tests/unit/test_main_helpers.py`:

```python
import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock

import aiosqlite
import pytest


@pytest.fixture
async def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    async with aiosqlite.connect(path) as db:
        await db.executescript("""
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
        await db.commit()
    return path


async def test_init_strategy_overrides_inserts_rows(db_path):
    from src.main import _init_strategy_overrides

    strategy = MagicMock()
    strategy.id = "ema_cross"
    strategy.config.enabled = True

    await _init_strategy_overrides(db_path, [strategy])

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT strategy_id, enabled FROM strategy_overrides"
        )
        rows = await cursor.fetchall()

    assert len(rows) == 1
    assert rows[0][0] == "ema_cross"
    assert rows[0][1] == 1


async def test_init_strategy_overrides_idempotent(db_path):
    from src.main import _init_strategy_overrides

    strategy = MagicMock()
    strategy.id = "ema_cross"
    strategy.config.enabled = True

    await _init_strategy_overrides(db_path, [strategy])
    await _init_strategy_overrides(db_path, [strategy])

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM strategy_overrides")
        row = await cursor.fetchone()
    assert row[0] == 1


async def test_heartbeat_loop_writes_status(db_path):
    from src.main import _heartbeat_loop

    feed = MagicMock()
    feed.connected = True
    stop = asyncio.Event()

    task = asyncio.create_task(_heartbeat_loop(db_path, feed, stop))
    await asyncio.sleep(0.1)
    stop.set()
    await task

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT ws_connected FROM bot_status WHERE id=1"
        )
        row = await cursor.fetchone()

    assert row is not None
    assert row[0] == 1


async def test_strategy_watcher_updates_dict(db_path):
    from src.main import _strategy_watcher_loop

    async with aiosqlite.connect(db_path) as db:
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO strategy_overrides VALUES ('ema_cross', 0, ?)", (now,)
        )
        await db.commit()

    enabled: dict[str, bool] = {"ema_cross": True}
    stop = asyncio.Event()

    task = asyncio.create_task(_strategy_watcher_loop(db_path, enabled, stop))
    await asyncio.sleep(0.1)
    stop.set()
    await task

    assert enabled["ema_cross"] is False
```

- [ ] **Schritt 2: Tests ausführen — FAIL bestätigen**

```
pytest tests/unit/test_main_helpers.py -v
```

Erwartet: 4× FAILED (ImportError: cannot import name '_init_strategy_overrides')

- [ ] **Schritt 3: main.py aktualisieren**

`src/main.py` — vollständige neue Version:

```python
from __future__ import annotations

import asyncio
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
import structlog

from src.backtesting.engine import BacktestEngine
from src.core.config import Settings
from src.core.event_bus import EventBus
from src.core.logger import get_logger, setup_logging
from src.core.types import Event, EventType
from src.data.feed import BybitFeed
from src.execution.order_manager import OrderManager
from src.portfolio.tracker import PortfolioTracker
from src.risk.manager import RiskManager
from src.strategies.base import BaseStrategy
from src.strategies.registry import load_strategies

log = get_logger(__name__)


async def _init_strategy_overrides(
    db_path: str, strategies: list[BaseStrategy]
) -> None:
    """Fügt für jede Strategie eine Zeile in strategy_overrides ein, falls noch nicht vorhanden."""
    async with aiosqlite.connect(db_path) as db:
        now = datetime.now(timezone.utc).isoformat()
        for strategy in strategies:
            enabled = 1 if strategy.config.enabled else 0
            await db.execute(
                """INSERT OR IGNORE INTO strategy_overrides (strategy_id, enabled, updated_at)
                   VALUES (?, ?, ?)""",
                (strategy.id, enabled, now),
            )
        await db.commit()


async def _heartbeat_loop(
    db_path: str, feed: BybitFeed, stop_event: asyncio.Event
) -> None:
    """Schreibt alle 10s den Verbindungsstatus in bot_status."""
    while not stop_event.is_set():
        async with aiosqlite.connect(db_path) as db:
            now = datetime.now(timezone.utc).isoformat()
            ws_connected = 1 if feed.connected else 0
            await db.execute(
                """INSERT INTO bot_status (id, timestamp, ws_connected)
                   VALUES (1, ?, ?)
                   ON CONFLICT(id) DO UPDATE
                   SET timestamp=excluded.timestamp,
                       ws_connected=excluded.ws_connected""",
                (now, ws_connected),
            )
            await db.commit()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            pass


async def _strategy_watcher_loop(
    db_path: str,
    strategy_enabled: dict[str, bool],
    stop_event: asyncio.Event,
) -> None:
    """Liest alle 30s strategy_overrides und aktualisiert das enabled-Dict."""
    while not stop_event.is_set():
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT strategy_id, enabled FROM strategy_overrides"
            )
            rows = await cursor.fetchall()
            for row in rows:
                strategy_enabled[row["strategy_id"]] = bool(row["enabled"])
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            pass


async def main() -> None:
    settings = Settings.from_yaml(Path("config/config.yaml"))
    setup_logging()

    bus = EventBus()

    tracker = PortfolioTracker(
        event_bus=bus,
        initial_capital=settings.backtesting.initial_capital,
        db_path="data/portfolio.db",
    )
    await tracker.initialize()

    risk = RiskManager(config=settings.risk, portfolio=tracker)

    order_manager = OrderManager(
        event_bus=bus, settings=settings,
        risk_manager=risk, portfolio=tracker,
    )
    order_manager.initialize()

    backtest_engine = BacktestEngine(settings=settings)

    strategies = load_strategies(settings.strategies)
    for strategy in strategies:
        log.info("strategy_loaded", name=strategy.id, symbols=strategy.config.symbols)

    db_path = tracker._db_path
    await _init_strategy_overrides(db_path, strategies)
    strategy_enabled: dict[str, bool] = {s.id: s.config.enabled for s in strategies}

    feed = BybitFeed(event_bus=bus, testnet=settings.bybit_testnet)
    for strategy in strategies:
        for symbol in strategy.config.symbols:
            feed.subscribe(symbol=symbol, interval=strategy.config.interval)

    async def _dispatch_candle(event: Event) -> None:
        candle = event.data
        for strategy in strategies:
            if not strategy_enabled.get(strategy.id, True):
                continue
            if candle.symbol in strategy.config.symbols:
                sig = await strategy.on_candle(candle)
                if sig is not None:
                    await bus.publish(Event(type=EventType.SIGNAL_GENERATED, data=sig))

    async def _dispatch_fill(event: Event) -> None:
        fill = event.data
        for strategy in strategies:
            if fill.strategy_id == strategy.id:
                await strategy.on_fill(fill)

    bus.subscribe(EventType.CANDLE_CLOSED, _dispatch_candle)
    bus.subscribe(EventType.ORDER_FILLED, _dispatch_fill)

    monitor = None
    if settings.telegram_token and settings.telegram_chat_id:
        from src.monitoring.telegram_bot import TelegramMonitor
        monitor = TelegramMonitor(
            token=settings.telegram_token,
            chat_id=settings.telegram_chat_id,
            event_bus=bus,
            risk_manager=risk,
            portfolio=tracker,
            backtest_engine=backtest_engine,
        )
        await monitor.start()
        log.info("telegram_monitor_started")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)
    else:
        def _win_stop(*_: object) -> None:
            loop.call_soon_threadsafe(stop_event.set)
        signal.signal(signal.SIGINT, _win_stop)
        signal.signal(signal.SIGTERM, _win_stop)

    await feed.start()
    log.info(
        "bot_started",
        testnet=settings.bybit_testnet,
        strategies=len(strategies),
        telegram=monitor is not None,
    )

    heartbeat_task = asyncio.create_task(
        _heartbeat_loop(db_path, feed, stop_event)
    )
    watcher_task = asyncio.create_task(
        _strategy_watcher_loop(db_path, strategy_enabled, stop_event)
    )

    await stop_event.wait()

    heartbeat_task.cancel()
    watcher_task.cancel()
    await asyncio.gather(heartbeat_task, watcher_task, return_exceptions=True)

    await feed.stop()
    if monitor:
        await monitor.stop()
    await tracker.close()
    log.info("bot_stopped")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Schritt 4: Tests ausführen — PASS**

```
pytest tests/unit/test_main_helpers.py -v
```

Erwartet: 4 passed

- [ ] **Schritt 5: Gesamte Test-Suite — keine Regression**

```
pytest tests/ -v
```

Erwartet: alle bisherigen Tests + 4 neue = 99 passed

- [ ] **Schritt 6: Commit**

```bash
git add src/main.py tests/unit/test_main_helpers.py
git commit -m "feat: add heartbeat and strategy-watcher background tasks to bot"
```

---

### Task 4: Dashboard — neue Endpoints

**Files:**
- Modify: `src/monitoring/dashboard.py`
- Modify: `tests/unit/test_dashboard.py`

- [ ] **Schritt 1: Neue Tests schreiben (FAIL erwartet)**

Folgende Abschnitte ans Ende von `tests/unit/test_dashboard.py` anhängen:

```python
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
```

- [ ] **Schritt 2: Tests ausführen — FAIL bestätigen**

```
pytest tests/unit/test_dashboard.py::test_status_api_no_db tests/unit/test_dashboard.py::test_status_api_connected tests/unit/test_dashboard.py::test_status_api_stale tests/unit/test_dashboard.py::test_toggle_strategy_disables tests/unit/test_dashboard.py::test_toggle_strategy_twice_re_enables -v
```

Erwartet: 5× FAILED (404 oder AttributeError)

- [ ] **Schritt 3: dashboard.py aktualisieren**

`src/monitoring/dashboard.py` — vollständige neue Version:

```python
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
```

- [ ] **Schritt 4: Neue Tests ausführen — PASS**

```
pytest tests/unit/test_dashboard.py::test_status_api_no_db tests/unit/test_dashboard.py::test_status_api_connected tests/unit/test_dashboard.py::test_status_api_stale tests/unit/test_dashboard.py::test_toggle_strategy_disables tests/unit/test_dashboard.py::test_toggle_strategy_twice_re_enables -v
```

Erwartet: 5 passed

- [ ] **Schritt 5: Alle Dashboard-Tests — keine Regression**

```
pytest tests/unit/test_dashboard.py -v
```

Erwartet: 17 passed (12 alte + 5 neue)

- [ ] **Schritt 6: Commit**

```bash
git add src/monitoring/dashboard.py tests/unit/test_dashboard.py
git commit -m "feat: add status and strategy-toggle endpoints to dashboard"
```

---

### Task 5: Templates

**Files:**
- Create: `src/monitoring/templates/partials/status.html`
- Create: `src/monitoring/templates/partials/strategy_row.html`
- Modify: `src/monitoring/templates/partials/strategies.html`
- Modify: `src/monitoring/templates/index.html`

- [ ] **Schritt 1: `partials/status.html` erstellen**

Neue Datei `src/monitoring/templates/partials/status.html`:

```html
{% if connected %}
<span style="color:#3fb950;font-weight:bold">● Verbunden</span>
{% else %}
<span style="color:#f85149;font-weight:bold">● Offline</span>
{% endif %}
{% if last_seen %}
<span style="color:#8b949e;font-size:0.8rem"> · zuletzt: {{ last_seen[:19] }}</span>
{% endif %}
```

- [ ] **Schritt 2: `partials/strategy_row.html` erstellen**

Neue Datei `src/monitoring/templates/partials/strategy_row.html`:

```html
<tr id="strategy-{{ strategy_id }}">
  <td>{{ strategy_id }}</td>
  <td>{{ trade_count }}</td>
  <td>
    <button
      hx-post="/api/strategies/{{ strategy_id }}/toggle"
      hx-target="#strategy-{{ strategy_id }}"
      hx-swap="outerHTML"
      style="background:none;border:none;cursor:pointer;font-size:1.2rem;padding:0">
      {% if enabled %}✅{% else %}⬜{% endif %}
    </button>
  </td>
</tr>
```

- [ ] **Schritt 3: `partials/strategies.html` ersetzen**

`src/monitoring/templates/partials/strategies.html` — komplett ersetzen:

```html
{% if strategies %}
<table>
  <thead>
    <tr>
      <th>Strategie</th>
      <th>Trades</th>
      <th>An/Aus</th>
    </tr>
  </thead>
  <tbody>
    {% for s in strategies %}
    <tr id="strategy-{{ s.strategy_id }}">
      <td>{{ s.strategy_id }}</td>
      <td>{{ s.trade_count }}</td>
      <td>
        <button
          hx-post="/api/strategies/{{ s.strategy_id }}/toggle"
          hx-target="#strategy-{{ s.strategy_id }}"
          hx-swap="outerHTML"
          style="background:none;border:none;cursor:pointer;font-size:1.2rem;padding:0">
          {% if s.enabled %}✅{% else %}⬜{% endif %}
        </button>
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% else %}
<p style="color:#8b949e">Keine Strategie-Daten.</p>
{% endif %}
```

- [ ] **Schritt 4: `index.html` — Status-Bereich einfügen**

In `src/monitoring/templates/index.html` die Zeile `<h1>🤖 Trading Bot</h1>` durch folgendes ersetzen:

```html
  <h1>🤖 Trading Bot</h1>
  <div hx-get="/partials/status"
       hx-trigger="load, every 15s"
       hx-swap="innerHTML"
       style="margin-bottom:1.5rem;font-size:0.95rem">
    <span style="color:#8b949e">Verbindung wird geprüft&#8230;</span>
  </div>
```

- [ ] **Schritt 5: Alle Tests — keine Regression**

```
pytest tests/ -v
```

Erwartet: 103 passed (alle bisherigen + neue Tests)

- [ ] **Schritt 6: Commit**

```bash
git add src/monitoring/templates/
git commit -m "feat: add status indicator and strategy toggle buttons to dashboard"
```

---

### Task 6: Abschluss-Verifikation

- [ ] **Schritt 1: Komplette Test-Suite**

```
pytest tests/ -v --tb=short
```

Erwartet: 103 passed, 0 failed

- [ ] **Schritt 2: Dashboard starten und manuell prüfen**

```
uvicorn src.monitoring.dashboard:app --reload --port 8080
```

Browser öffnen: `http://localhost:8080`

Prüfen:
- [ ] Status-Anzeige erscheint (zeigt "Offline" da kein Bot läuft — das ist korrekt)
- [ ] Strategien-Tabelle zeigt Spalte "An/Aus" (leer wenn keine DB vorhanden — korrekt)
- [ ] Keine JavaScript-Fehler in der Browser-Konsole

- [ ] **Schritt 3: Abschluss-Commit (falls nötig)**

```bash
git add -A
git status  # sicherstellen dass alles committed ist
```
