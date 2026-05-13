# Trading Bot — Plan 2: Trading Core

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vollständiger Trading-Kern: Portfolio Tracker (SQLite), Risk Manager, Order Manager (Bybit REST) sowie drei einsatzbereite Strategien (EMA-Crossover, Grid, Bollinger-Band) — fertig verdrahtet in main.py.

**Architecture:** Alle neuen Komponenten kommunizieren ausschließlich über den bestehenden Event Bus. PortfolioTracker speichert Fills in SQLite (aiosqlite). RiskManager prüft jeden Signal vor dem Order-Placement. OrderManager übersetzt validierte Signale in Bybit REST-Calls. Strategien sind über eine Registry als Plugins austauschbar.

**Tech Stack:** Python 3.12, pybit>=5.8 (HTTP), aiosqlite>=0.20, pytest-asyncio, unittest.mock

**Voraussetzung:** Plan 1 abgeschlossen (`v0.1.0-foundation`). Folgende Typen aus `src/core/types.py` werden verwendet: `Candle`, `Signal`, `OrderFill`, `Event`, `EventType`.

---

## File Map

| Datei | Verantwortlichkeit |
|---|---|
| `src/portfolio/__init__.py` | Paket-Marker |
| `src/portfolio/tracker.py` | SQLite-Persistenz: Fills, Positionen, PnL, Drawdown |
| `src/risk/__init__.py` | Paket-Marker |
| `src/risk/manager.py` | Gatekeeper: validiert Signals gegen Risk-Limits |
| `src/execution/__init__.py` | Paket-Marker |
| `src/execution/order_manager.py` | Bybit REST Order-Placement, Positions-Sizing |
| `src/strategies/registry.py` | Strategie-Factory: Name → Klasse |
| `src/strategies/ema_cross.py` | EMA-Crossover (Golden/Death Cross) |
| `src/strategies/grid.py` | Grid-Trading (Preisraster-Signale) |
| `src/strategies/bb_reversion.py` | Bollinger-Band Mean-Reversion |
| `src/main.py` | **Modifizieren**: alle neuen Komponenten verdrahten |
| `tests/unit/test_portfolio_tracker.py` | Tests Portfolio Tracker |
| `tests/unit/test_risk_manager.py` | Tests Risk Manager |
| `tests/unit/test_order_manager.py` | Tests Order Manager |
| `tests/unit/test_strategies.py` | Tests alle drei Strategien + Registry |

---

## Task 1: Paket-Stubs anlegen

**Files:**
- Create: `src/portfolio/__init__.py`
- Create: `src/risk/__init__.py`
- Create: `src/execution/__init__.py`

- [ ] **Schritt 1: Leere __init__.py-Dateien anlegen**

```bash
cd "C:/Users/ewald/OneDrive/Desktop/Claude/Team Inbox/Agenten handeln"
touch src/portfolio/__init__.py src/risk/__init__.py src/execution/__init__.py
```

- [ ] **Schritt 2: Bestehende Tests noch grün**

```bash
pytest -v --tb=short
```

Erwartete Ausgabe: `26 passed`

- [ ] **Schritt 3: Commit**

```bash
git add src/portfolio/__init__.py src/risk/__init__.py src/execution/__init__.py
git commit -m "chore: add package stubs for portfolio, risk, execution"
```

---

## Task 2: Portfolio Tracker

**Files:**
- Create: `src/portfolio/tracker.py`
- Create: `tests/unit/test_portfolio_tracker.py`

- [ ] **Schritt 1: Failing-Test schreiben**

Datei `tests/unit/test_portfolio_tracker.py`:

```python
import pytest
from datetime import datetime, timezone
from src.portfolio.tracker import PortfolioTracker
from src.core.event_bus import EventBus
from src.core.types import Event, EventType, OrderFill


def _fill(
    order_id: str = "ORD001",
    symbol: str = "BTCUSDT",
    side: str = "Buy",
    qty: float = 0.001,
    avg_price: float = 50000.0,
    fee: float = 0.027,
    strategy_id: str = "ema_cross",
) -> OrderFill:
    return OrderFill(
        order_id=order_id,
        symbol=symbol,
        side=side,
        qty=qty,
        avg_price=avg_price,
        fee=fee,
        timestamp=datetime.now(tz=timezone.utc),
        strategy_id=strategy_id,
    )


@pytest.fixture
async def tracker():
    bus = EventBus()
    t = PortfolioTracker(event_bus=bus, initial_capital=250.0, db_path=":memory:")
    await t.initialize()
    yield t
    await t.close()


async def test_initial_position_count_is_zero(tracker):
    count = await tracker.get_open_position_count()
    assert count == 0


async def test_records_trade_on_fill(tracker):
    await tracker._on_fill(Event(type=EventType.ORDER_FILLED, data=_fill()))
    trades = await tracker.get_trades()
    assert len(trades) == 1
    assert trades[0]["order_id"] == "ORD001"


async def test_position_count_increases_after_buy(tracker):
    await tracker._on_fill(Event(type=EventType.ORDER_FILLED, data=_fill(side="Buy")))
    assert await tracker.get_open_position_count() == 1


async def test_position_closed_after_opposite_sell(tracker):
    await tracker._on_fill(Event(type=EventType.ORDER_FILLED, data=_fill(order_id="O1", side="Buy", qty=0.001)))
    await tracker._on_fill(Event(type=EventType.ORDER_FILLED, data=_fill(order_id="O2", side="Sell", qty=0.001)))
    assert await tracker.get_open_position_count() == 0


async def test_daily_pnl_pct_negative_from_fees(tracker):
    # fee=25.0 on 250 capital = -10% daily PnL
    await tracker._on_fill(Event(type=EventType.ORDER_FILLED, data=_fill(fee=25.0)))
    pnl = await tracker.get_daily_pnl_pct()
    assert pnl < 0


async def test_drawdown_zero_at_start(tracker):
    assert await tracker.get_drawdown_pct() == 0.0


async def test_realized_pnl_negative_from_fees(tracker):
    await tracker._on_fill(Event(type=EventType.ORDER_FILLED, data=_fill(fee=1.0)))
    pnl = await tracker.get_realized_pnl()
    assert pnl == pytest.approx(-1.0)


async def test_get_trades_returns_list(tracker):
    await tracker._on_fill(Event(type=EventType.ORDER_FILLED, data=_fill(order_id="O1")))
    await tracker._on_fill(Event(type=EventType.ORDER_FILLED, data=_fill(order_id="O2")))
    trades = await tracker.get_trades(limit=10)
    assert len(trades) == 2
```

- [ ] **Schritt 2: Test ausführen (muss scheitern)**

```bash
cd "C:/Users/ewald/OneDrive/Desktop/Claude/Team Inbox/Agenten handeln"
pytest tests/unit/test_portfolio_tracker.py -v
```

Erwartete Ausgabe: `ImportError: cannot import name 'PortfolioTracker'`

- [ ] **Schritt 3: `src/portfolio/tracker.py` implementieren**

```python
from __future__ import annotations

from datetime import date, timezone
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
```

- [ ] **Schritt 4: Tests bestätigen**

```bash
pytest tests/unit/test_portfolio_tracker.py -v
```

Erwartete Ausgabe: `8 passed`

- [ ] **Schritt 5: Commit**

```bash
git add src/portfolio/tracker.py tests/unit/test_portfolio_tracker.py
git commit -m "feat: add SQLite portfolio tracker with PnL and drawdown"
```

---

## Task 3: Risk Manager

**Files:**
- Create: `src/risk/manager.py`
- Create: `tests/unit/test_risk_manager.py`

- [ ] **Schritt 1: Failing-Test schreiben**

Datei `tests/unit/test_risk_manager.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.risk.manager import RiskManager
from src.core.config import RiskConfig
from src.core.types import Signal


@pytest.fixture
def mock_portfolio():
    p = MagicMock()
    p.get_daily_pnl_pct = AsyncMock(return_value=0.0)
    p.get_drawdown_pct = AsyncMock(return_value=0.0)
    p.get_open_position_count = AsyncMock(return_value=0)
    return p


@pytest.fixture
def risk(mock_portfolio):
    config = RiskConfig(
        max_drawdown_pct=20.0,
        max_position_size_pct=10.0,
        max_open_positions=3,
        daily_loss_limit_pct=5.0,
        leverage=3,
    )
    return RiskManager(config=config, portfolio=mock_portfolio)


def _signal(side: str = "long", size_pct: float = 0.05) -> Signal:
    return Signal(symbol="BTCUSDT", side=side, size_pct=size_pct, strategy_id="test")


async def test_valid_signal_passes(risk):
    result = await risk.validate(_signal())
    assert result is not None
    assert result.symbol == "BTCUSDT"


async def test_paused_manager_rejects_all_signals(risk):
    risk.pause()
    assert await risk.validate(_signal()) is None


async def test_resume_allows_signals_again(risk):
    risk.pause()
    risk.resume()
    assert await risk.validate(_signal()) is not None


async def test_daily_loss_limit_rejects_and_pauses(risk, mock_portfolio):
    mock_portfolio.get_daily_pnl_pct.return_value = -6.0  # Überschreitet 5%-Limit
    result = await risk.validate(_signal())
    assert result is None
    assert risk.is_paused is True


async def test_max_drawdown_rejects_and_pauses(risk, mock_portfolio):
    mock_portfolio.get_drawdown_pct.return_value = 25.0  # Überschreitet 20%-Limit
    result = await risk.validate(_signal())
    assert result is None
    assert risk.is_paused is True


async def test_max_positions_rejects_new_signals(risk, mock_portfolio):
    mock_portfolio.get_open_position_count.return_value = 3  # Am Limit
    result = await risk.validate(_signal())
    assert result is None


async def test_close_signal_not_blocked_by_max_positions(risk, mock_portfolio):
    mock_portfolio.get_open_position_count.return_value = 3  # Am Limit
    close_sig = _signal(side="close", size_pct=1.0)
    result = await risk.validate(close_sig)
    assert result is not None  # Close-Signals immer erlaubt


async def test_oversized_signal_is_capped_to_max(risk):
    big = _signal(size_pct=0.50)  # 50% — weit über 10%-Limit
    result = await risk.validate(big)
    assert result is not None
    assert result.size_pct == pytest.approx(0.10)


async def test_signal_within_limits_unchanged(risk):
    sig = _signal(size_pct=0.05)  # 5% — unter 10%-Limit
    result = await risk.validate(sig)
    assert result is not None
    assert result.size_pct == pytest.approx(0.05)
```

- [ ] **Schritt 2: Test ausführen (muss scheitern)**

```bash
cd "C:/Users/ewald/OneDrive/Desktop/Claude/Team Inbox/Agenten handeln"
pytest tests/unit/test_risk_manager.py -v
```

Erwartete Ausgabe: `ImportError: cannot import name 'RiskManager'`

- [ ] **Schritt 3: `src/risk/manager.py` implementieren**

```python
from __future__ import annotations

from dataclasses import replace

import structlog

from src.core.config import RiskConfig
from src.core.types import Signal
from src.portfolio.tracker import PortfolioTracker

log = structlog.get_logger(__name__)


class RiskManager:
    def __init__(self, config: RiskConfig, portfolio: PortfolioTracker) -> None:
        self._config = config
        self._portfolio = portfolio
        self._paused = False

    def pause(self) -> None:
        self._paused = True
        log.warning("risk_manager_paused")

    def resume(self) -> None:
        self._paused = False
        log.info("risk_manager_resumed")

    @property
    def is_paused(self) -> bool:
        return self._paused

    async def validate(self, signal: Signal) -> Signal | None:
        """Prüft Signal gegen Risk-Limits. Gibt None zurück wenn abgelehnt."""
        if self._paused:
            log.info("signal_rejected_paused", symbol=signal.symbol)
            return None

        # Tages-Verlustlimit
        daily_pnl = await self._portfolio.get_daily_pnl_pct()
        if daily_pnl <= -self._config.daily_loss_limit_pct:
            self.pause()
            log.warning("daily_loss_limit_reached", pnl_pct=round(daily_pnl, 2))
            return None

        # Max Drawdown
        drawdown = await self._portfolio.get_drawdown_pct()
        if drawdown >= self._config.max_drawdown_pct:
            self.pause()
            log.warning("max_drawdown_reached", drawdown_pct=round(drawdown, 2))
            return None

        # Max offene Positionen (Close-Signals ausgenommen)
        if signal.side != "close":
            open_positions = await self._portfolio.get_open_position_count()
            if open_positions >= self._config.max_open_positions:
                log.info("signal_rejected_max_positions", count=open_positions)
                return None

        # Positionsgröße begrenzen
        max_size = self._config.max_position_size_pct / 100
        if signal.size_pct > max_size:
            signal = replace(signal, size_pct=max_size)
            log.info("signal_size_capped", cap=max_size)

        return signal
```

- [ ] **Schritt 4: Tests bestätigen**

```bash
pytest tests/unit/test_risk_manager.py -v
```

Erwartete Ausgabe: `9 passed`

- [ ] **Schritt 5: Commit**

```bash
git add src/risk/manager.py tests/unit/test_risk_manager.py
git commit -m "feat: add risk manager with drawdown, daily-loss and position-count gates"
```

---

## Task 4: Order Manager

**Files:**
- Create: `src/execution/order_manager.py`
- Create: `tests/unit/test_order_manager.py`

- [ ] **Schritt 1: Failing-Test schreiben**

Datei `tests/unit/test_order_manager.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.execution.order_manager import OrderManager
from src.core.event_bus import EventBus
from src.core.types import Event, EventType, Signal


def _make_settings(leverage: int = 3, capital: float = 250.0) -> MagicMock:
    s = MagicMock()
    s.bybit_testnet = True
    s.bybit_api_key = "test_key"
    s.bybit_api_secret = "test_secret"
    s.risk.leverage = leverage
    s.backtesting.initial_capital = capital
    return s


def _make_risk(approved: bool = True) -> MagicMock:
    r = MagicMock()
    sig = Signal(symbol="BTCUSDT", side="long", size_pct=0.05, strategy_id="test")
    r.validate = AsyncMock(return_value=sig if approved else None)
    return r


async def test_rejected_signal_does_not_place_order():
    bus = EventBus()
    with patch("src.execution.order_manager.HTTP"):
        om = OrderManager(bus, _make_settings(), _make_risk(approved=False), MagicMock())
        om.initialize()

    order_placed = []
    bus.subscribe(EventType.ORDER_PLACED, lambda e: order_placed.append(e))

    signal = Signal(symbol="BTCUSDT", side="long", size_pct=0.05, strategy_id="test")
    await om._on_signal(Event(type=EventType.SIGNAL_GENERATED, data=signal))
    assert len(order_placed) == 0


async def test_approved_signal_publishes_order_placed():
    bus = EventBus()
    mock_http = MagicMock()
    mock_http.get_tickers.return_value = {
        "result": {"list": [{"lastPrice": "50000"}]}
    }
    mock_http.place_order.return_value = {"result": {"orderId": "ORD999"}}

    with patch("src.execution.order_manager.HTTP", return_value=mock_http):
        om = OrderManager(bus, _make_settings(), _make_risk(approved=True), MagicMock())
        om.initialize()

    order_placed = []
    order_filled = []
    bus.subscribe(EventType.ORDER_PLACED, lambda e: order_placed.append(e))
    bus.subscribe(EventType.ORDER_FILLED, lambda e: order_filled.append(e))

    signal = Signal(symbol="BTCUSDT", side="long", size_pct=0.05, strategy_id="test")
    await om._on_signal(Event(type=EventType.SIGNAL_GENERATED, data=signal))

    assert len(order_placed) == 1
    assert len(order_filled) == 1
    assert order_placed[0].data["order_id"] == "ORD999"


def test_calc_qty_market_order():
    with patch("src.execution.order_manager.HTTP"):
        om = OrderManager(EventBus(), _make_settings(leverage=3, capital=250.0), MagicMock(), MagicMock())
    # 250 * 0.05 * 3 / 50000 = 0.00075 → "0.001" (3 dp)
    qty = om._calc_qty(size_pct=0.05, balance=250.0, price=50000.0)
    assert float(qty) == pytest.approx(0.00075, rel=1e-3)


def test_calc_qty_scales_with_leverage():
    with patch("src.execution.order_manager.HTTP"):
        om = OrderManager(EventBus(), _make_settings(leverage=10, capital=250.0), MagicMock(), MagicMock())
    qty = om._calc_qty(size_pct=0.10, balance=250.0, price=25000.0)
    # 250 * 0.1 * 10 / 25000 = 0.01
    assert float(qty) == pytest.approx(0.01, rel=1e-3)
```

- [ ] **Schritt 2: Test ausführen (muss scheitern)**

```bash
cd "C:/Users/ewald/OneDrive/Desktop/Claude/Team Inbox/Agenten handeln"
pytest tests/unit/test_order_manager.py -v
```

Erwartete Ausgabe: `ImportError: cannot import name 'OrderManager'`

- [ ] **Schritt 3: `src/execution/order_manager.py` implementieren**

```python
from __future__ import annotations

from datetime import datetime, timezone

import structlog
from pybit.unified_trading import HTTP

from src.core.config import Settings
from src.core.event_bus import EventBus
from src.core.types import Event, EventType, OrderFill, Signal
from src.portfolio.tracker import PortfolioTracker
from src.risk.manager import RiskManager

log = structlog.get_logger(__name__)


class OrderManager:
    def __init__(
        self,
        event_bus: EventBus,
        settings: Settings,
        risk_manager: RiskManager,
        portfolio: PortfolioTracker,
    ) -> None:
        self._bus = event_bus
        self._settings = settings
        self._risk = risk_manager
        self._portfolio = portfolio
        self._session = HTTP(
            testnet=settings.bybit_testnet,
            api_key=settings.bybit_api_key,
            api_secret=settings.bybit_api_secret,
        )

    def initialize(self) -> None:
        self._bus.subscribe(EventType.SIGNAL_GENERATED, self._on_signal)
        log.info("order_manager_initialized")

    async def _on_signal(self, event: Event) -> None:
        signal: Signal = event.data
        validated = await self._risk.validate(signal)
        if validated is None:
            return
        await self._place_order(validated)

    async def _place_order(self, signal: Signal) -> None:
        try:
            side = "Buy" if signal.side == "long" else "Sell"
            balance = self._settings.backtesting.initial_capital

            if signal.entry_price:
                price = signal.entry_price
                order_type = "Limit"
            else:
                ticker = self._session.get_tickers(
                    category="linear", symbol=signal.symbol
                )
                price = float(ticker["result"]["list"][0]["lastPrice"])
                order_type = "Market"

            qty = self._calc_qty(signal.size_pct, balance, price)

            order_params: dict = {
                "category": "linear",
                "symbol": signal.symbol,
                "side": side,
                "orderType": order_type,
                "qty": qty,
                "timeInForce": "GTC",
                "leverage": str(self._settings.risk.leverage),
            }
            if signal.entry_price:
                order_params["price"] = str(signal.entry_price)
            if signal.stop_loss:
                order_params["stopLoss"] = str(signal.stop_loss)
            if signal.take_profit:
                order_params["takeProfit"] = str(signal.take_profit)

            result = self._session.place_order(**order_params)
            order_id: str = result["result"]["orderId"]

            await self._bus.publish(Event(
                type=EventType.ORDER_PLACED,
                data={"order_id": order_id, "signal": signal},
            ))

            fill = OrderFill(
                order_id=order_id,
                symbol=signal.symbol,
                side=side,
                qty=float(qty),
                avg_price=price,
                fee=float(qty) * price * 0.00055,
                timestamp=datetime.now(tz=timezone.utc),
                strategy_id=signal.strategy_id,
            )
            await self._bus.publish(Event(type=EventType.ORDER_FILLED, data=fill))
            log.info("order_placed", order_id=order_id, symbol=signal.symbol, side=side)

        except Exception as exc:
            log.error("order_placement_failed", error=str(exc), symbol=signal.symbol)

    def _calc_qty(self, size_pct: float, balance: float, price: float) -> str:
        """Berechnet Order-Größe in Base Asset (3 Dezimalstellen)."""
        usdt_amount = balance * size_pct * self._settings.risk.leverage
        qty = usdt_amount / price
        return f"{qty:.3f}"
```

- [ ] **Schritt 4: Tests bestätigen**

```bash
pytest tests/unit/test_order_manager.py -v
```

Erwartete Ausgabe: `4 passed`

- [ ] **Schritt 5: Commit**

```bash
git add src/execution/order_manager.py tests/unit/test_order_manager.py
git commit -m "feat: add order manager with Bybit REST and position sizing"
```

---

## Task 5: Strategy Registry + EMA-Crossover

**Files:**
- Create: `src/strategies/registry.py`
- Create: `src/strategies/ema_cross.py`
- Create: `tests/unit/test_strategies.py` (Teilweise — Registry + EMA)

- [ ] **Schritt 1: Failing-Test schreiben**

Datei `tests/unit/test_strategies.py`:

```python
import pytest
from datetime import datetime, timezone
from src.strategies.ema_cross import EmaCrossStrategy
from src.strategies.registry import load_strategies, STRATEGY_REGISTRY
from src.core.config import StrategyEntry
from src.core.types import Candle


def _candle(close: float, symbol: str = "BTCUSDT") -> Candle:
    return Candle(
        symbol=symbol, interval="5",
        open_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        open=close * 0.999, high=close * 1.001,
        low=close * 0.998, close=close,
        volume=10.0, is_closed=True,
    )


# --- Registry ---

def test_registry_contains_all_strategies():
    assert "ema_cross" in STRATEGY_REGISTRY
    assert "grid" in STRATEGY_REGISTRY
    assert "bb_reversion" in STRATEGY_REGISTRY


def test_load_strategies_skips_disabled():
    configs = [
        StrategyEntry(name="ema_cross", enabled=True),
        StrategyEntry(name="grid", enabled=False),
    ]
    strategies = load_strategies(configs)
    assert len(strategies) == 1
    assert strategies[0].id == "ema_cross"


def test_load_strategies_raises_for_unknown():
    with pytest.raises(ValueError, match="Unknown strategy"):
        load_strategies([StrategyEntry(name="mystery_strategy", enabled=True)])


def test_load_strategies_empty_list():
    assert load_strategies([]) == []


# --- EMA Cross ---

async def test_ema_cross_returns_none_before_slow_period_warmup():
    cfg = StrategyEntry(name="ema_cross", params={"fast_ema": 3, "slow_ema": 5})
    s = EmaCrossStrategy(config=cfg)
    # Only 4 candles — not enough for slow_ema=5
    for _ in range(4):
        result = await s.on_candle(_candle(100.0))
    assert result is None


async def test_ema_cross_state_has_expected_keys():
    cfg = StrategyEntry(name="ema_cross", params={"fast_ema": 3, "slow_ema": 5})
    s = EmaCrossStrategy(config=cfg)
    state = s.get_state()
    assert "fast_ema" in state
    assert "slow_ema" in state
    assert "in_position" in state
    assert "position_side" in state


async def test_ema_cross_generates_long_signal_on_golden_cross():
    cfg = StrategyEntry(name="ema_cross", params={"fast_ema": 3, "slow_ema": 5, "size_pct": 0.05})
    s = EmaCrossStrategy(config=cfg)

    # Downtrend (fast < slow): 100, 99, 98, 97, 96
    downtrend = [100.0, 99.0, 98.0, 97.0, 96.0]
    # Sharp uptrend (fast crosses above slow): 97, 100, 105, 112
    uptrend = [97.0, 100.0, 105.0, 112.0]

    signals = []
    for p in downtrend + uptrend:
        sig = await s.on_candle(_candle(p))
        if sig:
            signals.append(sig)

    long_signals = [s for s in signals if s.side == "long"]
    assert len(long_signals) >= 1
    assert long_signals[0].strategy_id == "ema_cross"


async def test_ema_cross_generates_short_signal_on_death_cross():
    cfg = StrategyEntry(name="ema_cross", params={"fast_ema": 3, "slow_ema": 5})
    s = EmaCrossStrategy(config=cfg)

    # Uptrend then sharp drop
    uptrend = [100.0, 101.0, 102.0, 103.0, 104.0]
    downtrend = [103.0, 100.0, 95.0, 88.0]

    signals = []
    for p in uptrend + downtrend:
        sig = await s.on_candle(_candle(p))
        if sig:
            signals.append(sig)

    short_signals = [s for s in signals if s.side == "short"]
    assert len(short_signals) >= 1
```

- [ ] **Schritt 2: Test ausführen (muss scheitern)**

```bash
cd "C:/Users/ewald/OneDrive/Desktop/Claude/Team Inbox/Agenten handeln"
pytest tests/unit/test_strategies.py -v
```

Erwartete Ausgabe: `ImportError: cannot import name 'EmaCrossStrategy'`

- [ ] **Schritt 3: `src/strategies/ema_cross.py` implementieren**

```python
from __future__ import annotations

from collections import deque

from src.core.config import StrategyEntry
from src.core.types import Candle, OrderFill, Signal
from src.strategies.base import BaseStrategy


class EmaCrossStrategy(BaseStrategy):
    def __init__(self, config: StrategyEntry) -> None:
        super().__init__(config)
        self._fast_period: int = int(config.params.get("fast_ema", 9))
        self._slow_period: int = int(config.params.get("slow_ema", 21))
        self._size_pct: float = float(config.params.get("size_pct", 0.05))
        self._prices: deque[float] = deque(maxlen=self._slow_period * 3)
        self._fast_ema: float | None = None
        self._slow_ema: float | None = None
        self._in_position = False
        self._position_side: str | None = None

    def _calc_ema(self, period: int, prev_ema: float | None) -> float | None:
        if len(self._prices) < period:
            return None
        if prev_ema is None:
            return sum(list(self._prices)[-period:]) / period
        k = 2.0 / (period + 1)
        return float(self._prices[-1]) * k + prev_ema * (1.0 - k)

    async def on_candle(self, candle: Candle) -> Signal | None:
        self._prices.append(candle.close)

        prev_fast = self._fast_ema
        prev_slow = self._slow_ema

        self._fast_ema = self._calc_ema(self._fast_period, self._fast_ema)
        self._slow_ema = self._calc_ema(self._slow_period, self._slow_ema)

        if None in (self._fast_ema, self._slow_ema, prev_fast, prev_slow):
            return None

        # Golden Cross: fast kreuzt slow von unten → Long
        if prev_fast <= prev_slow and self._fast_ema > self._slow_ema:  # type: ignore[operator]
            if not self._in_position or self._position_side == "short":
                self._in_position = True
                self._position_side = "long"
                return Signal(
                    symbol=candle.symbol, side="long",
                    size_pct=self._size_pct, strategy_id=self.id,
                )

        # Death Cross: fast kreuzt slow von oben → Short
        if prev_fast >= prev_slow and self._fast_ema < self._slow_ema:  # type: ignore[operator]
            if not self._in_position or self._position_side == "long":
                self._in_position = True
                self._position_side = "short"
                return Signal(
                    symbol=candle.symbol, side="short",
                    size_pct=self._size_pct, strategy_id=self.id,
                )

        return None

    async def on_fill(self, fill: OrderFill) -> None:
        pass

    def get_state(self) -> dict:
        return {
            "fast_ema": self._fast_ema,
            "slow_ema": self._slow_ema,
            "in_position": self._in_position,
            "position_side": self._position_side,
        }
```

- [ ] **Schritt 4: `src/strategies/registry.py` implementieren**

```python
from __future__ import annotations

from src.core.config import StrategyEntry
from src.strategies.base import BaseStrategy
from src.strategies.ema_cross import EmaCrossStrategy

# Grid und BB werden in späteren Tasks hinzugefügt.
# Platzhalter — wird in Task 6 + 7 erweitert.
STRATEGY_REGISTRY: dict[str, type[BaseStrategy]] = {
    "ema_cross": EmaCrossStrategy,
    "grid": EmaCrossStrategy,        # temporärer Platzhalter — wird in Task 6 ersetzt
    "bb_reversion": EmaCrossStrategy, # temporärer Platzhalter — wird in Task 7 ersetzt
}


def load_strategies(configs: list[StrategyEntry]) -> list[BaseStrategy]:
    strategies: list[BaseStrategy] = []
    for cfg in configs:
        if not cfg.enabled:
            continue
        cls = STRATEGY_REGISTRY.get(cfg.name)
        if cls is None:
            raise ValueError(
                f"Unknown strategy: '{cfg.name}'. Available: {list(STRATEGY_REGISTRY)}"
            )
        strategies.append(cls(config=cfg))
    return strategies
```

- [ ] **Schritt 5: Tests bestätigen**

```bash
pytest tests/unit/test_strategies.py -v
```

Erwartete Ausgabe: `9 passed`

- [ ] **Schritt 6: Commit**

```bash
git add src/strategies/ema_cross.py src/strategies/registry.py tests/unit/test_strategies.py
git commit -m "feat: add EMA-crossover strategy and strategy registry"
```

---

## Task 6: Grid-Strategie

**Files:**
- Create: `src/strategies/grid.py`
- Modify: `src/strategies/registry.py` (Platzhalter ersetzen)
- Modify: `tests/unit/test_strategies.py` (Grid-Tests ergänzen)

- [ ] **Schritt 1: Grid-Tests an `test_strategies.py` anhängen**

Öffne `tests/unit/test_strategies.py` und füge am Ende hinzu:

```python
# --- Grid ---
from src.strategies.grid import GridStrategy


async def test_grid_returns_none_on_first_candle():
    cfg = StrategyEntry(name="grid", params={"grid_count": 4, "grid_spacing_pct": 1.0})
    s = GridStrategy(config=cfg)
    result = await s.on_candle(_candle(100.0))
    assert result is None


async def test_grid_state_initialized_after_first_candle():
    cfg = StrategyEntry(name="grid", params={"grid_count": 4, "grid_spacing_pct": 1.0})
    s = GridStrategy(config=cfg)
    await s.on_candle(_candle(100.0))
    state = s.get_state()
    assert state["initialized"] is True
    assert len(state["grid_levels"]) > 0
    assert state["center_price"] == pytest.approx(100.0)


async def test_grid_generates_buy_signal_on_drop_through_level():
    cfg = StrategyEntry(name="grid", params={"grid_count": 6, "grid_spacing_pct": 1.0})
    s = GridStrategy(config=cfg)

    await s.on_candle(_candle(100.0))  # Initialize at 100.0
    # Grid levels below ~100: 99.0, 98.0, 97.0
    # Drop from 100 to 98.5 should cross the 99.0 level
    result = await s.on_candle(_candle(98.5))
    assert result is not None
    assert result.side == "long"
    assert result.strategy_id == "grid"


async def test_grid_generates_sell_signal_on_rise_through_level():
    cfg = StrategyEntry(name="grid", params={"grid_count": 6, "grid_spacing_pct": 1.0})
    s = GridStrategy(config=cfg)

    await s.on_candle(_candle(100.0))  # Initialize at 100.0
    # Grid levels above ~100: 101.0, 102.0, 103.0
    # Rise from 100 to 101.5 should cross the 101.0 level
    result = await s.on_candle(_candle(101.5))
    assert result is not None
    assert result.side == "short"


async def test_grid_no_signal_if_price_stays_between_levels():
    cfg = StrategyEntry(name="grid", params={"grid_count": 4, "grid_spacing_pct": 2.0})
    s = GridStrategy(config=cfg)
    await s.on_candle(_candle(100.0))  # Initialize
    # Small move that doesn't cross any level (±2% spacing → levels at 98, 102)
    result = await s.on_candle(_candle(100.5))
    assert result is None
```

- [ ] **Schritt 2: Tests ausführen (Grid-Tests müssen scheitern)**

```bash
cd "C:/Users/ewald/OneDrive/Desktop/Claude/Team Inbox/Agenten handeln"
pytest tests/unit/test_strategies.py -v -k "grid"
```

Erwartete Ausgabe: `ImportError: cannot import name 'GridStrategy'`

- [ ] **Schritt 3: `src/strategies/grid.py` implementieren**

```python
from __future__ import annotations

from src.core.config import StrategyEntry
from src.core.types import Candle, OrderFill, Signal
from src.strategies.base import BaseStrategy


class GridStrategy(BaseStrategy):
    def __init__(self, config: StrategyEntry) -> None:
        super().__init__(config)
        self._grid_count: int = int(config.params.get("grid_count", 10))
        self._grid_spacing_pct: float = float(config.params.get("grid_spacing_pct", 0.5)) / 100
        self._size_pct: float = float(config.params.get("size_pct", 0.02))
        self._initialized = False
        self._center_price: float | None = None
        self._grid_levels: list[float] = []
        self._last_price: float | None = None

    def _build_grid(self, center: float) -> None:
        half = self._grid_count // 2
        self._grid_levels = [
            round(center * (1.0 + i * self._grid_spacing_pct), 8)
            for i in range(-half, half + 1)
            if i != 0
        ]
        self._center_price = center

    async def on_candle(self, candle: Candle) -> Signal | None:
        price = candle.close

        if not self._initialized:
            self._build_grid(price)
            self._initialized = True
            self._last_price = price
            return None

        if self._last_price is None:
            self._last_price = price
            return None

        signal: Signal | None = None

        for level in self._grid_levels:
            if level < self._center_price:  # type: ignore[operator]
                # Kauflevel: Preis fällt durch dieses Level
                if self._last_price > level >= price:
                    signal = Signal(
                        symbol=candle.symbol, side="long",
                        size_pct=self._size_pct, strategy_id=self.id,
                        entry_price=level,
                    )
                    break
            else:
                # Verkauflevel: Preis steigt durch dieses Level
                if self._last_price < level <= price:
                    signal = Signal(
                        symbol=candle.symbol, side="short",
                        size_pct=self._size_pct, strategy_id=self.id,
                        entry_price=level,
                    )
                    break

        self._last_price = price
        return signal

    async def on_fill(self, fill: OrderFill) -> None:
        pass

    def get_state(self) -> dict:
        return {
            "initialized": self._initialized,
            "center_price": self._center_price,
            "grid_levels": self._grid_levels,
            "last_price": self._last_price,
        }
```

- [ ] **Schritt 4: registry.py aktualisieren (Platzhalter ersetzen)**

Ersetze den Inhalt von `src/strategies/registry.py` mit:

```python
from __future__ import annotations

from src.core.config import StrategyEntry
from src.strategies.base import BaseStrategy
from src.strategies.ema_cross import EmaCrossStrategy
from src.strategies.grid import GridStrategy

# bb_reversion wird in Task 7 hinzugefügt — temporärer Platzhalter bleibt
STRATEGY_REGISTRY: dict[str, type[BaseStrategy]] = {
    "ema_cross": EmaCrossStrategy,
    "grid": GridStrategy,
    "bb_reversion": EmaCrossStrategy,  # temporärer Platzhalter — wird in Task 7 ersetzt
}


def load_strategies(configs: list[StrategyEntry]) -> list[BaseStrategy]:
    strategies: list[BaseStrategy] = []
    for cfg in configs:
        if not cfg.enabled:
            continue
        cls = STRATEGY_REGISTRY.get(cfg.name)
        if cls is None:
            raise ValueError(
                f"Unknown strategy: '{cfg.name}'. Available: {list(STRATEGY_REGISTRY)}"
            )
        strategies.append(cls(config=cfg))
    return strategies
```

- [ ] **Schritt 5: Tests bestätigen**

```bash
pytest tests/unit/test_strategies.py -v
```

Erwartete Ausgabe: `13 passed` (9 bisherige + 4 neue Grid-Tests)

- [ ] **Schritt 6: Commit**

```bash
git add src/strategies/grid.py src/strategies/registry.py tests/unit/test_strategies.py
git commit -m "feat: add grid trading strategy with price-level crossing detection"
```

---

## Task 7: Bollinger-Band Mean-Reversion Strategie

**Files:**
- Create: `src/strategies/bb_reversion.py`
- Modify: `src/strategies/registry.py` (finalen Platzhalter ersetzen)
- Modify: `tests/unit/test_strategies.py` (BB-Tests ergänzen)

- [ ] **Schritt 1: BB-Tests an `test_strategies.py` anhängen**

Öffne `tests/unit/test_strategies.py` und füge am Ende hinzu:

```python
# --- Bollinger-Band ---
from src.strategies.bb_reversion import BollingerReversionStrategy
import statistics


async def test_bb_returns_none_before_period_warmup():
    cfg = StrategyEntry(name="bb_reversion", params={"period": 5, "std_dev": 2.0})
    s = BollingerReversionStrategy(config=cfg)
    for _ in range(4):
        result = await s.on_candle(_candle(100.0))
    assert result is None


async def test_bb_state_has_expected_keys():
    cfg = StrategyEntry(name="bb_reversion", params={"period": 3})
    s = BollingerReversionStrategy(config=cfg)
    state = s.get_state()
    assert "sma" in state
    assert "lower_band" in state
    assert "upper_band" in state
    assert "in_position" in state


async def test_bb_generates_long_signal_below_lower_band():
    cfg = StrategyEntry(name="bb_reversion", params={"period": 5, "std_dev": 1.0, "size_pct": 0.05})
    s = BollingerReversionStrategy(config=cfg)

    # Prices with variation to create real bands
    base = [100.0, 101.0, 99.0, 102.0, 98.0]
    for p in base:
        await s.on_candle(_candle(p))

    # Calculate expected lower band
    prices_list = [100.0, 101.0, 99.0, 102.0, 98.0]
    sma = sum(prices_list) / 5
    std = statistics.stdev(prices_list)
    lower = sma - 1.0 * std

    # Drop well below lower band
    result = await s.on_candle(_candle(lower - 5.0))
    assert result is not None
    assert result.side == "long"
    assert result.size_pct == pytest.approx(0.05)


async def test_bb_generates_short_signal_above_upper_band():
    cfg = StrategyEntry(name="bb_reversion", params={"period": 5, "std_dev": 1.0})
    s = BollingerReversionStrategy(config=cfg)

    base = [100.0, 101.0, 99.0, 102.0, 98.0]
    for p in base:
        await s.on_candle(_candle(p))

    prices_list = [100.0, 101.0, 99.0, 102.0, 98.0]
    sma = sum(prices_list) / 5
    std = statistics.stdev(prices_list)
    upper = sma + 1.0 * std

    result = await s.on_candle(_candle(upper + 5.0))
    assert result is not None
    assert result.side == "short"


async def test_bb_generates_close_signal_when_price_returns_to_sma():
    cfg = StrategyEntry(name="bb_reversion", params={"period": 5, "std_dev": 1.0})
    s = BollingerReversionStrategy(config=cfg)

    base = [100.0, 101.0, 99.0, 102.0, 98.0]
    for p in base:
        await s.on_candle(_candle(p))

    # Enter long position
    prices_list = [100.0, 101.0, 99.0, 102.0, 98.0]
    sma = sum(prices_list) / 5
    std = statistics.stdev(prices_list)
    lower = sma - 1.0 * std

    await s.on_candle(_candle(lower - 5.0))
    assert s._in_position is True

    # Price returns to SMA
    result = await s.on_candle(_candle(sma + 0.5))
    assert result is not None
    assert result.side == "close"
    assert s._in_position is False
```

- [ ] **Schritt 2: Tests ausführen (BB-Tests müssen scheitern)**

```bash
cd "C:/Users/ewald/OneDrive/Desktop/Claude/Team Inbox/Agenten handeln"
pytest tests/unit/test_strategies.py -v -k "bb"
```

Erwartete Ausgabe: `ImportError: cannot import name 'BollingerReversionStrategy'`

- [ ] **Schritt 3: `src/strategies/bb_reversion.py` implementieren**

```python
from __future__ import annotations

import statistics
from collections import deque

from src.core.config import StrategyEntry
from src.core.types import Candle, OrderFill, Signal
from src.strategies.base import BaseStrategy


class BollingerReversionStrategy(BaseStrategy):
    def __init__(self, config: StrategyEntry) -> None:
        super().__init__(config)
        self._period: int = int(config.params.get("period", 20))
        self._std_dev: float = float(config.params.get("std_dev", 2.0))
        self._size_pct: float = float(config.params.get("size_pct", 0.05))
        self._prices: deque[float] = deque(maxlen=self._period)
        self._in_position = False
        self._position_side: str | None = None

    def _bands(self) -> tuple[float, float, float] | None:
        if len(self._prices) < self._period:
            return None
        prices = list(self._prices)
        sma = sum(prices) / self._period
        std = statistics.stdev(prices)
        return (
            sma - self._std_dev * std,
            sma,
            sma + self._std_dev * std,
        )

    async def on_candle(self, candle: Candle) -> Signal | None:
        self._prices.append(candle.close)
        bands = self._bands()
        if bands is None:
            return None

        lower, sma, upper = bands
        price = candle.close

        # Position schließen wenn Preis zur SMA zurückkehrt
        if self._in_position:
            if self._position_side == "long" and price >= sma:
                self._in_position = False
                self._position_side = None
                return Signal(
                    symbol=candle.symbol, side="close",
                    size_pct=1.0, strategy_id=self.id,
                )
            if self._position_side == "short" and price <= sma:
                self._in_position = False
                self._position_side = None
                return Signal(
                    symbol=candle.symbol, side="close",
                    size_pct=1.0, strategy_id=self.id,
                )

        # Neue Position eröffnen bei Banddurchbruch
        if not self._in_position:
            if price < lower:
                self._in_position = True
                self._position_side = "long"
                return Signal(
                    symbol=candle.symbol, side="long",
                    size_pct=self._size_pct, strategy_id=self.id,
                )
            if price > upper:
                self._in_position = True
                self._position_side = "short"
                return Signal(
                    symbol=candle.symbol, side="short",
                    size_pct=self._size_pct, strategy_id=self.id,
                )

        return None

    async def on_fill(self, fill: OrderFill) -> None:
        pass

    def get_state(self) -> dict:
        bands = self._bands()
        lower, sma, upper = bands if bands else (None, None, None)
        return {
            "lower_band": lower,
            "sma": sma,
            "upper_band": upper,
            "in_position": self._in_position,
            "position_side": self._position_side,
        }
```

- [ ] **Schritt 4: registry.py finalisieren (alle Platzhalter ersetzen)**

Ersetze den Inhalt von `src/strategies/registry.py` mit der finalen Version:

```python
from __future__ import annotations

from src.core.config import StrategyEntry
from src.strategies.base import BaseStrategy
from src.strategies.bb_reversion import BollingerReversionStrategy
from src.strategies.ema_cross import EmaCrossStrategy
from src.strategies.grid import GridStrategy

STRATEGY_REGISTRY: dict[str, type[BaseStrategy]] = {
    "ema_cross": EmaCrossStrategy,
    "grid": GridStrategy,
    "bb_reversion": BollingerReversionStrategy,
}


def load_strategies(configs: list[StrategyEntry]) -> list[BaseStrategy]:
    strategies: list[BaseStrategy] = []
    for cfg in configs:
        if not cfg.enabled:
            continue
        cls = STRATEGY_REGISTRY.get(cfg.name)
        if cls is None:
            raise ValueError(
                f"Unknown strategy: '{cfg.name}'. Available: {list(STRATEGY_REGISTRY)}"
            )
        strategies.append(cls(config=cfg))
    return strategies
```

- [ ] **Schritt 5: Alle Strategy-Tests bestätigen**

```bash
pytest tests/unit/test_strategies.py -v
```

Erwartete Ausgabe: `18 passed` (13 bisherige + 5 neue BB-Tests)

- [ ] **Schritt 6: Commit**

```bash
git add src/strategies/bb_reversion.py src/strategies/registry.py tests/unit/test_strategies.py
git commit -m "feat: add Bollinger-Band mean-reversion strategy and finalize registry"
```

---

## Task 8: main.py aktualisieren — alle Komponenten verdrahten

**Files:**
- Modify: `src/main.py`

- [ ] **Schritt 1: main.py vollständig ersetzen**

Lies die aktuelle `src/main.py`, dann ersetze sie vollständig:

```python
from __future__ import annotations

import asyncio
import signal
from pathlib import Path

from src.core.config import Settings
from src.core.event_bus import EventBus
from src.core.logger import get_logger, setup_logging
from src.core.types import Event, EventType
from src.data.feed import BybitFeed
from src.execution.order_manager import OrderManager
from src.portfolio.tracker import PortfolioTracker
from src.risk.manager import RiskManager
from src.strategies.registry import load_strategies

log = get_logger(__name__)


async def main() -> None:
    settings = Settings.from_yaml(Path("config/config.yaml"))
    setup_logging()

    bus = EventBus()

    # Portfolio Tracker (SQLite)
    tracker = PortfolioTracker(
        event_bus=bus,
        initial_capital=settings.backtesting.initial_capital,
        db_path="data/portfolio.db",
    )
    await tracker.initialize()

    # Risk Manager
    risk = RiskManager(config=settings.risk, portfolio=tracker)

    # Order Manager
    order_manager = OrderManager(
        event_bus=bus,
        settings=settings,
        risk_manager=risk,
        portfolio=tracker,
    )
    order_manager.initialize()

    # Strategien laden
    strategies = load_strategies(settings.strategies)
    for strategy in strategies:
        log.info("strategy_loaded", name=strategy.id, symbols=strategy.config.symbols)

    # Data Feed abonnieren
    feed = BybitFeed(event_bus=bus, testnet=settings.bybit_testnet)
    for strategy in strategies:
        for symbol in strategy.config.symbols:
            feed.subscribe(symbol=symbol, interval=strategy.config.interval)

    # Candle-Events an Strategien weiterleiten
    async def _dispatch_candle(event: Event) -> None:
        candle = event.data
        for strategy in strategies:
            if candle.symbol in strategy.config.symbols:
                sig = await strategy.on_candle(candle)
                if sig is not None:
                    await bus.publish(Event(type=EventType.SIGNAL_GENERATED, data=sig))

    # Fill-Events an zugehörige Strategie weiterleiten
    async def _dispatch_fill(event: Event) -> None:
        fill = event.data
        for strategy in strategies:
            if fill.strategy_id == strategy.id:
                await strategy.on_fill(fill)

    bus.subscribe(EventType.CANDLE_CLOSED, _dispatch_candle)
    bus.subscribe(EventType.ORDER_FILLED, _dispatch_fill)

    # Graceful Shutdown
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    await feed.start()
    log.info(
        "bot_started",
        testnet=settings.bybit_testnet,
        strategies=len(strategies),
    )

    await stop_event.wait()

    await feed.stop()
    await tracker.close()
    log.info("bot_stopped")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Schritt 2: Alle Tests noch grün**

```bash
cd "C:/Users/ewald/OneDrive/Desktop/Claude/Team Inbox/Agenten handeln"
pytest -v --tb=short
```

Erwartete Ausgabe: mind. `44 passed, 0 failed`

- [ ] **Schritt 3: Commit**

```bash
git add src/main.py
git commit -m "feat: wire all Plan-2 components in main.py"
```

---

## Task 9: Abschluss-Test + Tag

- [ ] **Schritt 1: Gesamte Test-Suite**

```bash
cd "C:/Users/ewald/OneDrive/Desktop/Claude/Team Inbox/Agenten handeln"
pytest -v --tb=short
```

Erwartete Ausgabe: **mind. 44 passed, 0 failed**

- [ ] **Schritt 2: Projektstruktur prüfen**

```bash
find src -name "*.py" | grep -v __pycache__ | sort
```

Erwartete Ausgabe (mind.):
```
src/__init__.py
src/core/__init__.py
src/core/config.py
src/core/event_bus.py
src/core/logger.py
src/core/types.py
src/data/__init__.py
src/data/feed.py
src/execution/__init__.py
src/execution/order_manager.py
src/main.py
src/portfolio/__init__.py
src/portfolio/tracker.py
src/risk/__init__.py
src/risk/manager.py
src/strategies/__init__.py
src/strategies/base.py
src/strategies/bb_reversion.py
src/strategies/ema_cross.py
src/strategies/grid.py
src/strategies/registry.py
```

- [ ] **Schritt 3: Finaler Commit + Tag**

```bash
git add -A
git status  # Sicherstellen dass nichts unstaged ist
git commit -m "chore: plan 2 complete — trading core verified" --allow-empty
git tag v0.2.0-trading-core
git log --oneline -5
```

---

## Nächste Schritte

Plan 3 baut auf dieser Basis auf:
- **Backtesting Engine** — Historische OHLCV-Daten von Bybit REST, gleiche Strategy-Klassen, ProcessPoolExecutor
- **Telegram Bot** — Push-Alerts + `/status`, `/pause`, `/resume`, `/set` Befehle
- **Web Dashboard** — FastAPI + HTMX: Portfolio, Trade-History, Log-Stream
- **Docker-Compose finalisieren** — Dashboard-Service + Caddy Reverse Proxy

Spec: `docs/superpowers/specs/2026-05-12-trading-bot-design.md`
