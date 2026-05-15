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
