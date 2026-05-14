from __future__ import annotations

from datetime import date
from pathlib import Path

import aiosqlite
import structlog

from src.core.event_bus import EventBus
from src.core.types import Event, EventType, OrderFill

log = structlog.get_logger(__name__)

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


class PortfolioTracker:
    def __init__(
        self,
        event_bus: EventBus,
        initial_capital: float = 250.0,
        db_path: str = "data/portfolio.db",
    ) -> None:
        self._bus = event_bus
        self._initial_capital = initial_capital
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None
        self._peak_balance: float = initial_capital

    async def initialize(self) -> None:
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.executescript(_SCHEMA)
        await self._db.commit()
        self._bus.subscribe(EventType.ORDER_FILLED, self._on_fill)
        log.info("portfolio_tracker_initialized", db=self._db_path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    async def _on_fill(self, event: Event) -> None:
        fill: OrderFill = event.data
        await self._record_trade(fill)
        await self._update_position(fill)

    async def _record_trade(self, fill: OrderFill) -> None:
        assert self._db
        await self._db.execute(
            """INSERT INTO trades
               (order_id, symbol, side, qty, avg_price, fee, strategy_id, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fill.order_id, fill.symbol, fill.side, fill.qty,
                fill.avg_price, fill.fee, fill.strategy_id,
                fill.timestamp.isoformat(),
            ),
        )
        await self._db.commit()

    async def _update_position(self, fill: OrderFill) -> None:
        assert self._db
        cursor = await self._db.execute(
            "SELECT side, qty FROM positions WHERE symbol = ?", (fill.symbol,)
        )
        row = await cursor.fetchone()

        if row is None:
            await self._db.execute(
                """INSERT INTO positions
                   (symbol, side, qty, entry_price, strategy_id, opened_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    fill.symbol, fill.side, fill.qty, fill.avg_price,
                    fill.strategy_id, fill.timestamp.isoformat(),
                ),
            )
        else:
            existing_side, existing_qty = row
            if existing_side == fill.side:
                await self._db.execute(
                    "UPDATE positions SET qty = ? WHERE symbol = ?",
                    (existing_qty + fill.qty, fill.symbol),
                )
            else:
                new_qty = existing_qty - fill.qty
                if new_qty <= 0:
                    await self._db.execute(
                        "DELETE FROM positions WHERE symbol = ?", (fill.symbol,)
                    )
                else:
                    await self._db.execute(
                        "UPDATE positions SET qty = ? WHERE symbol = ?",
                        (new_qty, fill.symbol),
                    )
        await self._db.commit()

    async def get_open_position_count(self) -> int:
        assert self._db
        cursor = await self._db.execute("SELECT COUNT(*) FROM positions")
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def get_realized_pnl(self) -> float:
        """Realisierter PnL = negative Summe aller Fees (vereinfachtes Modell)."""
        assert self._db
        cursor = await self._db.execute("SELECT COALESCE(SUM(fee), 0.0) FROM trades")
        row = await cursor.fetchone()
        return -(row[0] if row else 0.0)

    async def get_daily_pnl_pct(self) -> float:
        """Heutiger PnL (Fees) als Prozentsatz des Startkapitals."""
        assert self._db
        today = date.today().isoformat()
        cursor = await self._db.execute(
            "SELECT COALESCE(SUM(fee), 0.0) FROM trades WHERE timestamp LIKE ?",
            (f"{today}%",),
        )
        row = await cursor.fetchone()
        daily_fees = row[0] if row else 0.0
        return -(daily_fees / self._initial_capital) * 100

    async def get_drawdown_pct(self) -> float:
        """Maximaler Drawdown vom Peak als Prozentzahl."""
        current = self._initial_capital + await self.get_realized_pnl()
        self._peak_balance = max(self._peak_balance, current)
        if self._peak_balance == 0:
            return 0.0
        return max(0.0, (self._peak_balance - current) / self._peak_balance * 100)

    async def get_trades(self, limit: int = 100) -> list[dict]:
        assert self._db
        cursor = await self._db.execute(
            "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in rows]
