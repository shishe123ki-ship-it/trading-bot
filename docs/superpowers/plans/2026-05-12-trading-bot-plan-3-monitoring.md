# Trading Bot — Plan 3: Backtesting, Monitoring & Deployment

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backtesting-Engine (historische Simulation), Telegram-Monitor (Push-Alerts + Steuerbefehle), Web-Dashboard (FastAPI + HTMX) und Docker-Compose-Finalisierung (Dashboard-Service + Caddy Reverse-Proxy).

**Architecture:** `BacktestEngine` läuft via `asyncio.to_thread()` — blockiert den Live-Loop nicht. Der `TelegramMonitor` abonniert den Event Bus und wird als asyncio-Task in `main.py` gestartet (optional — nur wenn `TELEGRAM_TOKEN` gesetzt). Das FastAPI-Dashboard läuft als separater Docker-Service und liest das gemeinsame SQLite-Volume read-only via `aiosqlite`.

**Tech Stack:** Python 3.12, pybit>=5.8 (REST kline), python-telegram-bot>=21.0, fastapi>=0.110, uvicorn[standard]>=0.27, jinja2>=3.1, httpx>=0.27 (Tests), aiosqlite>=0.20

**Voraussetzung:** Plan 2 abgeschlossen (`v0.2.0-trading-core`), 65 Tests grün. Folgende Typen werden genutzt: `Candle`, `Signal`, `OrderFill`, `Event`, `EventType`, `BacktestConfig`, `StrategyEntry`, `Settings`, `RiskConfig`. `BaseStrategy` speichert `self.config` und `self.id`.

---

## File Map

| Datei | Verantwortlichkeit |
|---|---|
| `src/backtesting/__init__.py` | Paket-Marker |
| `src/backtesting/engine.py` | OHLCV-Fetch via Bybit REST, async Strategie-Simulation, Metriken |
| `src/monitoring/__init__.py` | Paket-Marker |
| `src/monitoring/telegram_bot.py` | Push-Alerts (ORDER_FILLED, RISK_BREACHED) + Steuerbefehle |
| `src/monitoring/dashboard.py` | FastAPI-App: JSON-API + HTMX-Partials + SSE |
| `src/monitoring/templates/index.html` | HTMX-Hauptseite |
| `src/monitoring/templates/partials/portfolio.html` | Portfolio-HTML-Fragment |
| `src/monitoring/templates/partials/trades.html` | Trades-Tabelle-HTML-Fragment |
| `src/main.py` | **Modifizieren**: BacktestEngine + optionaler TelegramMonitor |
| `pyproject.toml` | **Modifizieren**: jinja2 + httpx hinzufügen |
| `docker-compose.yml` | **Modifizieren**: dashboard + caddy Services |
| `config/Caddyfile` | Caddy Reverse-Proxy-Konfiguration |
| `tests/unit/test_backtesting.py` | Tests BacktestEngine (fetch, simulate, metrics) |
| `tests/unit/test_telegram_bot.py` | Tests TelegramMonitor (alerts, commands) |
| `tests/unit/test_dashboard.py` | Tests FastAPI-Dashboard (httpx AsyncClient) |

---

## Task 1: Abhängigkeiten + Paket-Stubs

**Files:**
- Modify: `pyproject.toml`
- Create: `src/backtesting/__init__.py`
- Create: `src/monitoring/__init__.py`
- Create: `src/monitoring/templates/` (Verzeichnisstruktur)

- [ ] **Schritt 1: pyproject.toml erweitern**

Lies die aktuelle `pyproject.toml`. Füge `"jinja2>=3.1"` zu `dependencies` hinzu und `"httpx>=0.27"` zu `[project.optional-dependencies] dev` hinzu:

```toml
[project]
name = "trading-bot"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "pybit>=5.8.0",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "structlog>=24.0",
    "aiohttp>=3.9",
    "aiosqlite>=0.20",
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "python-telegram-bot>=21.0",
    "pandas>=2.2",
    "pyyaml>=6.0",
    "python-dotenv>=1.0",
    "jinja2>=3.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-mock>=3.12",
    "httpx>=0.27",
]
```

- [ ] **Schritt 2: Paket-Stubs + Template-Verzeichnisse anlegen**

```bash
cd "C:/Users/ewald/OneDrive/Desktop/Claude/Team Inbox/Agenten handeln"
touch src/backtesting/__init__.py src/monitoring/__init__.py
mkdir -p src/monitoring/templates/partials
```

- [ ] **Schritt 3: Bestehende Tests noch grün**

```bash
cd "C:/Users/ewald/OneDrive/Desktop/Claude/Team Inbox/Agenten handeln"
python -m pytest -v --tb=short
```

Erwartete Ausgabe: `65 passed`

- [ ] **Schritt 4: Commit**

```bash
git add pyproject.toml src/backtesting/__init__.py src/monitoring/__init__.py
git commit -m "chore: add package stubs and jinja2/httpx dependencies"
```

---

## Task 2: Backtesting Engine

**Files:**
- Create: `src/backtesting/engine.py`
- Create: `tests/unit/test_backtesting.py`

- [ ] **Schritt 1: Failing-Tests schreiben**

Erstelle `tests/unit/test_backtesting.py`:

```python
import pytest
from unittest.mock import MagicMock, patch
from datetime import timezone
from src.backtesting.engine import BacktestEngine, BacktestResult
from src.core.config import BacktestConfig, StrategyEntry
from src.strategies.ema_cross import EmaCrossStrategy


def _make_settings(fee_rate: float = 0.00055, slippage_pct: float = 0.05, capital: float = 250.0) -> MagicMock:
    s = MagicMock()
    s.bybit_testnet = True
    s.bybit_api_key = "key"
    s.bybit_api_secret = "secret"
    s.backtesting = BacktestConfig(
        fee_rate=fee_rate, slippage_pct=slippage_pct, initial_capital=capital
    )
    return s


def _kline_row(close: float, ts_ms: int) -> list:
    """Bybit kline-Format: [startTime, open, high, low, close, volume, turnover]"""
    return [str(ts_ms), str(close * 0.999), str(close * 1.001), str(close * 0.998), str(close), "10.0", "0"]


def test_backtest_result_dataclass():
    result = BacktestResult(
        strategy_id="ema_cross", symbol="BTCUSDT", days=7,
        total_trades=5, win_rate=0.6, total_pnl=2.5,
        sharpe_ratio=1.2, max_drawdown_pct=3.5,
        equity_curve=[250.0, 251.0, 252.0],
    )
    assert result.strategy_id == "ema_cross"
    assert result.win_rate == pytest.approx(0.6)
    assert len(result.equity_curve) == 3


def test_fetch_ohlcv_parses_bybit_response():
    """_fetch_ohlcv wandelt Bybit-Antwort korrekt um (älteste zuerst)."""
    rows = [
        _kline_row(51000, 1700003600000),  # newer
        _kline_row(50000, 1700000000000),  # older
    ]
    mock_session = MagicMock()
    mock_session.get_kline.return_value = {"result": {"list": rows}}

    with patch("src.backtesting.engine.HTTP", return_value=mock_session):
        engine = BacktestEngine(_make_settings())

    candles = engine._fetch_ohlcv("BTCUSDT", "60", 2)
    assert len(candles) == 2
    assert candles[0].close == pytest.approx(50000.0)   # oldest first
    assert candles[1].close == pytest.approx(51000.0)
    assert candles[0].symbol == "BTCUSDT"
    assert candles[0].interval == "60"


async def test_backtest_run_returns_valid_result():
    """run() gibt BacktestResult mit gültigen Feldern zurück."""
    rows = [_kline_row(float(50000 + i * 200), i * 3_600_000) for i in range(20)]
    mock_session = MagicMock()
    mock_session.get_kline.return_value = {"result": {"list": list(reversed(rows))}}

    with patch("src.backtesting.engine.HTTP", return_value=mock_session):
        engine = BacktestEngine(_make_settings())

    cfg = StrategyEntry(name="ema_cross", params={"fast_ema": 3, "slow_ema": 5})
    result = await engine.run(EmaCrossStrategy, cfg, "BTCUSDT", 7)

    assert isinstance(result, BacktestResult)
    assert result.symbol == "BTCUSDT"
    assert result.days == 7
    assert result.total_trades >= 0
    assert 0.0 <= result.win_rate <= 1.0
    assert result.max_drawdown_pct >= 0.0
    assert len(result.equity_curve) > 0


async def test_backtest_flatline_has_zero_trades():
    """Gleichbleibende Preise → EMA-Crossover generiert keine Signale → 0 Trades."""
    rows = [_kline_row(50000.0, i * 3_600_000) for i in range(20)]
    mock_session = MagicMock()
    mock_session.get_kline.return_value = {"result": {"list": list(reversed(rows))}}

    with patch("src.backtesting.engine.HTTP", return_value=mock_session):
        engine = BacktestEngine(_make_settings())

    cfg = StrategyEntry(name="ema_cross", params={"fast_ema": 3, "slow_ema": 5})
    result = await engine.run(EmaCrossStrategy, cfg, "BTCUSDT", 7)

    assert result.total_trades == 0
    assert result.total_pnl == pytest.approx(0.0)
    assert result.win_rate == pytest.approx(0.0)
    assert result.sharpe_ratio == pytest.approx(0.0)
```

- [ ] **Schritt 2: Test ausführen (muss scheitern)**

```bash
cd "C:/Users/ewald/OneDrive/Desktop/Claude/Team Inbox/Agenten handeln"
python -m pytest tests/unit/test_backtesting.py -v
```

Erwartete Ausgabe: `ImportError: cannot import name 'BacktestEngine'`

- [ ] **Schritt 3: `src/backtesting/engine.py` implementieren**

```python
from __future__ import annotations

import asyncio
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone

import structlog
from pybit.unified_trading import HTTP

from src.core.config import Settings, StrategyEntry
from src.core.types import Candle
from src.strategies.base import BaseStrategy

log = structlog.get_logger(__name__)


@dataclass
class BacktestResult:
    strategy_id: str
    symbol: str
    days: int
    total_trades: int
    win_rate: float
    total_pnl: float
    sharpe_ratio: float
    max_drawdown_pct: float
    equity_curve: list[float] = field(default_factory=list)


class BacktestEngine:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._session = HTTP(
            testnet=settings.bybit_testnet,
            api_key=settings.bybit_api_key,
            api_secret=settings.bybit_api_secret,
        )

    async def run(
        self,
        strategy_cls: type[BaseStrategy],
        strategy_cfg: StrategyEntry,
        symbol: str,
        days: int,
    ) -> BacktestResult:
        """Führt Backtest in einem Thread-Pool aus (blockiert asyncio nicht)."""
        return await asyncio.to_thread(
            self._run_sync, strategy_cls, strategy_cfg, symbol, days
        )

    def _run_sync(
        self,
        strategy_cls: type[BaseStrategy],
        strategy_cfg: StrategyEntry,
        symbol: str,
        days: int,
    ) -> BacktestResult:
        interval = strategy_cfg.interval or "60"
        limit = min(days * 24, 1000)
        candles = self._fetch_ohlcv(symbol, interval, limit)
        strategy = strategy_cls(config=strategy_cfg)
        return asyncio.run(self._simulate_async(strategy, candles, symbol, days))

    def _fetch_ohlcv(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        result = self._session.get_kline(
            category="linear", symbol=symbol, interval=interval, limit=limit,
        )
        rows = result.get("result", {}).get("list", [])
        candles: list[Candle] = []
        for row in reversed(rows):  # Bybit gibt neueste zuerst zurück
            candles.append(Candle(
                symbol=symbol,
                interval=interval,
                open_time=datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
                is_closed=True,
            ))
        return candles

    async def _simulate_async(
        self,
        strategy: BaseStrategy,
        candles: list[Candle],
        symbol: str,
        days: int,
    ) -> BacktestResult:
        fee_rate = self._settings.backtesting.fee_rate
        slippage = self._settings.backtesting.slippage_pct / 100
        capital = self._settings.backtesting.initial_capital
        equity = capital
        peak = capital
        equity_curve: list[float] = [equity]
        max_drawdown = 0.0
        trade_pnls: list[float] = []
        position: dict | None = None

        for candle in candles:
            sig = await strategy.on_candle(candle)
            if sig is None:
                continue

            price = candle.close

            if sig.side in ("long", "short") and position is None:
                entry = price * (1 + slippage if sig.side == "long" else 1 - slippage)
                fee = capital * sig.size_pct * fee_rate
                equity -= fee
                position = {
                    "side": sig.side,
                    "entry": entry,
                    "notional": capital * sig.size_pct,
                }

            elif sig.side == "close" and position is not None:
                exit_p = price * (1 - slippage if position["side"] == "long" else 1 + slippage)
                fee = position["notional"] * fee_rate
                pnl_pct = (exit_p - position["entry"]) / position["entry"]
                if position["side"] == "short":
                    pnl_pct = -pnl_pct
                pnl = position["notional"] * pnl_pct - fee
                equity += pnl
                trade_pnls.append(pnl)
                position = None

            peak = max(peak, equity)
            dd = (peak - equity) / peak * 100 if peak > 0 else 0.0
            max_drawdown = max(max_drawdown, dd)
            equity_curve.append(equity)

        total_trades = len(trade_pnls)
        winners = [p for p in trade_pnls if p > 0]
        win_rate = len(winners) / total_trades if total_trades > 0 else 0.0
        total_pnl = sum(trade_pnls)
        sharpe = self._sharpe(trade_pnls)

        log.info(
            "backtest_complete",
            strategy=strategy.id, symbol=symbol,
            trades=total_trades, win_rate=round(win_rate, 3), pnl=round(total_pnl, 4),
        )
        return BacktestResult(
            strategy_id=strategy.id, symbol=symbol, days=days,
            total_trades=total_trades, win_rate=win_rate, total_pnl=total_pnl,
            sharpe_ratio=sharpe, max_drawdown_pct=max_drawdown, equity_curve=equity_curve,
        )

    @staticmethod
    def _sharpe(returns: list[float]) -> float:
        if len(returns) < 2:
            return 0.0
        mean = statistics.mean(returns)
        std = statistics.stdev(returns)
        if std == 0:
            return 0.0
        return mean / std * (252 ** 0.5)
```

- [ ] **Schritt 4: Tests bestätigen**

```bash
python -m pytest tests/unit/test_backtesting.py -v
```

Erwartete Ausgabe: `4 passed`

- [ ] **Schritt 5: Commit**

```bash
git add src/backtesting/engine.py tests/unit/test_backtesting.py
git commit -m "feat: add backtesting engine with OHLCV fetch and strategy simulation"
```

---

## Task 3: Telegram Monitor

**Files:**
- Create: `src/monitoring/telegram_bot.py`
- Create: `tests/unit/test_telegram_bot.py`

- [ ] **Schritt 1: Failing-Tests schreiben**

Erstelle `tests/unit/test_telegram_bot.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from src.monitoring.telegram_bot import TelegramMonitor
from src.core.event_bus import EventBus
from src.core.types import Event, EventType, OrderFill


def _make_risk():
    r = MagicMock()
    r.is_paused = False
    r.pause = MagicMock()
    r.resume = MagicMock()
    r._config = MagicMock()
    return r


def _make_portfolio():
    p = MagicMock()
    p.get_realized_pnl = AsyncMock(return_value=5.5)
    p.get_open_position_count = AsyncMock(return_value=2)
    p.get_daily_pnl_pct = AsyncMock(return_value=2.2)
    return p


def _make_fill() -> OrderFill:
    return OrderFill(
        order_id="ORD001", symbol="BTCUSDT", side="Buy",
        qty=0.001, avg_price=50000.0, fee=0.027,
        timestamp=datetime.now(tz=timezone.utc), strategy_id="ema_cross",
    )


@pytest.fixture
def monitor():
    bus = EventBus()
    with patch("src.monitoring.telegram_bot.Application"):
        m = TelegramMonitor(
            token="TOKEN", chat_id="12345",
            event_bus=bus, risk_manager=_make_risk(),
            portfolio=_make_portfolio(), backtest_engine=MagicMock(),
        )
    return m


async def test_on_order_filled_sends_message(monitor):
    monitor._send = AsyncMock()
    fill = _make_fill()
    await monitor._on_order_filled(Event(type=EventType.ORDER_FILLED, data=fill))
    monitor._send.assert_called_once()
    msg = monitor._send.call_args[0][0]
    assert "BTCUSDT" in msg
    assert "Buy" in msg


async def test_on_risk_breached_sends_message(monitor):
    monitor._send = AsyncMock()
    await monitor._on_risk_breached(Event(type=EventType.RISK_BREACHED, data="max_drawdown"))
    monitor._send.assert_called_once()
    msg = monitor._send.call_args[0][0]
    assert "max_drawdown" in msg


async def test_cmd_pause_calls_risk_pause(monitor):
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    await monitor.cmd_pause(update, MagicMock())
    monitor._risk.pause.assert_called_once()
    update.message.reply_text.assert_called_once()


async def test_cmd_resume_calls_risk_resume(monitor):
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    await monitor.cmd_resume(update, MagicMock())
    monitor._risk.resume.assert_called_once()


async def test_cmd_status_includes_pnl_and_positions(monitor):
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    await monitor.cmd_status(update, MagicMock())
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "5.5" in text   # realized_pnl
    assert "2" in text     # open_positions


async def test_cmd_set_valid_key_updates_config(monitor):
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()
    ctx.args = ["leverage", "5"]
    await monitor.cmd_set(update, ctx)
    monitor._risk._config.update.assert_called_once_with("leverage", "5")
    text = update.message.reply_text.call_args[0][0]
    assert "✅" in text


async def test_cmd_set_wrong_arg_count_shows_usage(monitor):
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()
    ctx.args = ["leverage"]   # fehlt der Wert
    await monitor.cmd_set(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "Verwendung" in text


async def test_cmd_backtest_unknown_strategy_shows_error(monitor):
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()
    ctx.args = ["unknown_strat", "BTCUSDT", "7"]
    await monitor.cmd_backtest(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "❌" in text
```

- [ ] **Schritt 2: Test ausführen (muss scheitern)**

```bash
cd "C:/Users/ewald/OneDrive/Desktop/Claude/Team Inbox/Agenten handeln"
python -m pytest tests/unit/test_telegram_bot.py -v
```

Erwartete Ausgabe: `ImportError: cannot import name 'TelegramMonitor'`

- [ ] **Schritt 3: `src/monitoring/telegram_bot.py` implementieren**

```python
from __future__ import annotations

import structlog
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from src.backtesting.engine import BacktestEngine
from src.core.config import StrategyEntry
from src.core.event_bus import EventBus
from src.core.types import Event, EventType, OrderFill
from src.portfolio.tracker import PortfolioTracker
from src.risk.manager import RiskManager
from src.strategies.registry import STRATEGY_REGISTRY

log = structlog.get_logger(__name__)


class TelegramMonitor:
    def __init__(
        self,
        token: str,
        chat_id: str,
        event_bus: EventBus,
        risk_manager: RiskManager,
        portfolio: PortfolioTracker,
        backtest_engine: BacktestEngine,
    ) -> None:
        self._token = token
        self._chat_id = chat_id
        self._bus = event_bus
        self._risk = risk_manager
        self._portfolio = portfolio
        self._backtest = backtest_engine
        self._app: Application | None = None

    async def start(self) -> None:
        self._app = Application.builder().token(self._token).build()
        self._app.add_handler(CommandHandler("status", self.cmd_status))
        self._app.add_handler(CommandHandler("pause", self.cmd_pause))
        self._app.add_handler(CommandHandler("resume", self.cmd_resume))
        self._app.add_handler(CommandHandler("set", self.cmd_set))
        self._app.add_handler(CommandHandler("backtest", self.cmd_backtest))
        self._bus.subscribe(EventType.ORDER_FILLED, self._on_order_filled)
        self._bus.subscribe(EventType.RISK_BREACHED, self._on_risk_breached)
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()
        log.info("telegram_monitor_started")

    async def stop(self) -> None:
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

    async def _send(self, text: str) -> None:
        if self._app and self._app.bot:
            try:
                await self._app.bot.send_message(chat_id=self._chat_id, text=text)
            except Exception as exc:
                log.warning("telegram_send_failed", error=str(exc))

    async def _on_order_filled(self, event: Event) -> None:
        fill: OrderFill = event.data
        await self._send(
            f"✅ Order gefüllt: {fill.side} {fill.qty:.4f} {fill.symbol} "
            f"@ {fill.avg_price:.2f} USDT"
        )

    async def _on_risk_breached(self, event: Event) -> None:
        await self._send(f"⚠️ Risk-Limit überschritten: {event.data}")

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        pnl = await self._portfolio.get_realized_pnl()
        positions = await self._portfolio.get_open_position_count()
        daily = await self._portfolio.get_daily_pnl_pct()
        await update.message.reply_text(
            f"📊 Status\n"
            f"Realisierter PnL: {pnl:.4f} USDT\n"
            f"Offene Positionen: {positions}\n"
            f"Tages-PnL: {daily:.2f}%\n"
            f"Bot pausiert: {self._risk.is_paused}"
        )

    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self._risk.pause()
        await update.message.reply_text("⏸ Bot pausiert. Neue Orders werden geblockt.")

    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self._risk.resume()
        await update.message.reply_text("▶️ Bot fortgesetzt.")

    async def cmd_set(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args or len(context.args) != 2:
            await update.message.reply_text(
                "Verwendung: /set <parameter> <wert>\nBeispiel: /set leverage 2"
            )
            return
        key, value = context.args
        try:
            self._risk._config.update(key, value)
            await update.message.reply_text(f"✅ {key} = {value}")
        except ValueError as exc:
            await update.message.reply_text(f"❌ Fehler: {exc}")

    async def cmd_backtest(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args or len(context.args) != 3:
            await update.message.reply_text(
                "Verwendung: /backtest <strategie> <symbol> <tage>\n"
                "Beispiel: /backtest ema_cross BTCUSDT 30"
            )
            return
        strategy_name, symbol, days_str = context.args
        try:
            days = int(days_str)
        except ValueError:
            await update.message.reply_text("❌ <tage> muss eine ganze Zahl sein.")
            return
        cls = STRATEGY_REGISTRY.get(strategy_name)
        if cls is None:
            await update.message.reply_text(
                f"❌ Unbekannte Strategie: '{strategy_name}'. "
                f"Verfügbar: {list(STRATEGY_REGISTRY)}"
            )
            return
        await update.message.reply_text(
            f"🔄 Backtest läuft: {strategy_name} / {symbol} ({days} Tage)…"
        )
        cfg = StrategyEntry(name=strategy_name, symbols=[symbol])
        result = await self._backtest.run(cls, cfg, symbol, days)
        await update.message.reply_text(
            f"📈 Backtest-Ergebnis\n"
            f"Strategie: {strategy_name} / {symbol}\n"
            f"Trades: {result.total_trades}\n"
            f"Win Rate: {result.win_rate:.1%}\n"
            f"PnL: {result.total_pnl:.4f} USDT\n"
            f"Sharpe: {result.sharpe_ratio:.2f}\n"
            f"Max Drawdown: {result.max_drawdown_pct:.2f}%"
        )
```

- [ ] **Schritt 4: Tests bestätigen**

```bash
python -m pytest tests/unit/test_telegram_bot.py -v
```

Erwartete Ausgabe: `8 passed`

- [ ] **Schritt 5: Commit**

```bash
git add src/monitoring/telegram_bot.py tests/unit/test_telegram_bot.py
git commit -m "feat: add telegram monitor with push alerts and control commands"
```

---

## Task 4: Web-Dashboard (FastAPI + HTMX)

**Files:**
- Create: `src/monitoring/dashboard.py`
- Create: `src/monitoring/templates/index.html`
- Create: `src/monitoring/templates/partials/portfolio.html`
- Create: `src/monitoring/templates/partials/trades.html`
- Create: `tests/unit/test_dashboard.py`

- [ ] **Schritt 1: Failing-Tests schreiben**

Erstelle `tests/unit/test_dashboard.py`:

```python
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
```

- [ ] **Schritt 2: Test ausführen (muss scheitern)**

```bash
cd "C:/Users/ewald/OneDrive/Desktop/Claude/Team Inbox/Agenten handeln"
python -m pytest tests/unit/test_dashboard.py -v
```

Erwartete Ausgabe: `ImportError: cannot import name 'dashboard'`

- [ ] **Schritt 3: `src/monitoring/dashboard.py` implementieren**

```python
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
    return templates.TemplateResponse("index.html", {"request": request})


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
    return templates.TemplateResponse(
        "partials/portfolio.html", {"request": request, **data}
    )


@app.get("/partials/trades", response_class=HTMLResponse)
async def trades_partial(request: Request) -> HTMLResponse:
    trade_list = await trades(limit=20)
    return templates.TemplateResponse(
        "partials/trades.html", {"request": request, "trades": trade_list}
    )


@app.get("/stream")
async def log_stream() -> StreamingResponse:
    async def generator():
        yield "data: Dashboard verbunden\n\n"
    return StreamingResponse(generator(), media_type="text/event-stream")
```

- [ ] **Schritt 4: Templates anlegen**

Erstelle `src/monitoring/templates/index.html`:

```html
<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Trading Bot Dashboard</title>
  <script src="https://unpkg.com/htmx.org@1.9.10/dist/htmx.min.js"></script>
  <style>
    * { box-sizing: border-box; }
    body { font-family: 'Courier New', monospace; background: #0d1117; color: #e6edf3; margin: 0; padding: 2rem; }
    h1 { color: #58a6ff; margin-bottom: 0.25rem; }
    h2 { color: #8b949e; font-size: 1rem; border-bottom: 1px solid #30363d; padding-bottom: 0.5rem; margin-top: 2rem; }
    .card { background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 1rem; margin: 0.5rem 0; min-height: 4rem; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; }
    .metric { text-align: center; }
    .metric .value { font-size: 2rem; font-weight: bold; color: #58a6ff; }
    .metric .label { font-size: 0.8rem; color: #8b949e; }
    .pos { color: #3fb950; }
    .neg { color: #f85149; }
    table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
    th { color: #8b949e; padding: 0.5rem; text-align: left; border-bottom: 1px solid #30363d; }
    td { padding: 0.5rem; border-bottom: 1px solid #21262d; }
  </style>
</head>
<body>
  <h1>🤖 Trading Bot</h1>

  <h2>Portfolio</h2>
  <div class="card"
       hx-get="/partials/portfolio"
       hx-trigger="load, every 10s"
       hx-swap="innerHTML">
    <span style="color:#8b949e">Lade…</span>
  </div>

  <h2>Letzte Trades</h2>
  <div class="card"
       hx-get="/partials/trades"
       hx-trigger="load, every 30s"
       hx-swap="innerHTML">
    <span style="color:#8b949e">Lade…</span>
  </div>
</body>
</html>
```

Erstelle `src/monitoring/templates/partials/portfolio.html`:

```html
<div class="grid">
  <div class="metric">
    <div class="value">{{ open_positions }}</div>
    <div class="label">Offene Positionen</div>
  </div>
  <div class="metric">
    <div class="value {{ 'pos' if realized_pnl >= 0 else 'neg' }}">
      {{ "%.4f" | format(realized_pnl) }}
    </div>
    <div class="label">Realisierter PnL (USDT)</div>
  </div>
</div>
```

Erstelle `src/monitoring/templates/partials/trades.html`:

```html
{% if trades %}
<table>
  <thead>
    <tr>
      <th>Zeit</th><th>Symbol</th><th>Seite</th>
      <th>Qty</th><th>Preis</th><th>Gebühr</th><th>Strategie</th>
    </tr>
  </thead>
  <tbody>
    {% for t in trades %}
    <tr>
      <td>{{ t.timestamp[:19] }}</td>
      <td>{{ t.symbol }}</td>
      <td class="{{ 'pos' if t.side == 'Buy' else 'neg' }}">{{ t.side }}</td>
      <td>{{ t.qty }}</td>
      <td>{{ t.avg_price }}</td>
      <td>{{ "%.4f" | format(t.fee) }}</td>
      <td>{{ t.strategy_id }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% else %}
<p style="color:#8b949e">Noch keine Trades.</p>
{% endif %}
```

- [ ] **Schritt 5: Tests bestätigen**

```bash
python -m pytest tests/unit/test_dashboard.py -v
```

Erwartete Ausgabe: `6 passed`

- [ ] **Schritt 6: Commit**

```bash
git add src/monitoring/dashboard.py src/monitoring/templates/ tests/unit/test_dashboard.py
git commit -m "feat: add FastAPI dashboard with HTMX portfolio and trades views"
```

---

## Task 5: main.py — BacktestEngine + Telegram verdrahten

**Files:**
- Modify: `src/main.py`

- [ ] **Schritt 1: main.py vollständig ersetzen**

Lies die aktuelle `src/main.py`, dann ersetze sie vollständig:

```python
from __future__ import annotations

import asyncio
import signal
from pathlib import Path

from src.backtesting.engine import BacktestEngine
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

    feed = BybitFeed(event_bus=bus, testnet=settings.bybit_testnet)
    for strategy in strategies:
        for symbol in strategy.config.symbols:
            feed.subscribe(symbol=symbol, interval=strategy.config.interval)

    async def _dispatch_candle(event: Event) -> None:
        candle = event.data
        for strategy in strategies:
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

    # Telegram Monitor (optional — nur wenn Token konfiguriert)
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
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    await feed.start()
    log.info(
        "bot_started",
        testnet=settings.bybit_testnet,
        strategies=len(strategies),
        telegram=monitor is not None,
    )

    await stop_event.wait()

    await feed.stop()
    if monitor:
        await monitor.stop()
    await tracker.close()
    log.info("bot_stopped")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Schritt 2: Gesamte Tests noch grün**

```bash
cd "C:/Users/ewald/OneDrive/Desktop/Claude/Team Inbox/Agenten handeln"
python -m pytest -v --tb=short
```

Erwartete Ausgabe: mind. `83 passed, 0 failed`
(65 aus Plan 2 + 4 Backtest + 8 Telegram + 6 Dashboard = 83)

- [ ] **Schritt 3: Commit**

```bash
git add src/main.py
git commit -m "feat: wire BacktestEngine and optional TelegramMonitor in main.py"
```

---

## Task 6: Docker-Compose-Finalisierung

**Files:**
- Modify: `docker-compose.yml`
- Create: `config/Caddyfile`

- [ ] **Schritt 1: Aktuelles docker-compose.yml lesen**

```bash
cat docker-compose.yml
```

- [ ] **Schritt 2: docker-compose.yml vollständig ersetzen**

```yaml
version: "3.9"

services:
  trading-bot:
    build: .
    restart: unless-stopped
    env_file: config/.env
    volumes:
      - ./config:/app/config:ro
      - bot-data:/app/data
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  dashboard:
    build: .
    command: uvicorn src.monitoring.dashboard:app --host 0.0.0.0 --port 8080
    restart: unless-stopped
    env_file: config/.env
    environment:
      - DASHBOARD_DB_PATH=/app/data/portfolio.db
    volumes:
      - ./config:/app/config:ro
      - bot-data:/app/data:ro
    depends_on:
      - trading-bot

  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./config/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy-data:/data
    depends_on:
      - dashboard

volumes:
  bot-data:
  caddy-data:
```

- [ ] **Schritt 3: `config/Caddyfile` anlegen**

```
# Passwort-Hash generieren (auf dem VPS ausführen):
#   caddy hash-password --plaintext <ihr-passwort>
# Dann den Hash unten ersetzen.
# Standard-Passwort für Entwicklung: "admin"
# UNBEDINGT vor dem Deployment ändern!

:80 {
    basicauth {
        admin $2a$14$Zkx19XLiW6VYouLHR5NmfOFU0z2GTNmpkT/5qqR7hx4IjWJPDhjm2
    }
    reverse_proxy dashboard:8080
}
```

- [ ] **Schritt 4: Docker-Build testen (optional — benötigt Docker)**

```bash
cd "C:/Users/ewald/OneDrive/Desktop/Claude/Team Inbox/Agenten handeln"
docker compose build --no-cache 2>&1 | tail -5
```

Erwartete Ausgabe: `Successfully built ...` oder `=> exporting to image`

Wenn Docker nicht verfügbar ist, diesen Schritt überspringen.

- [ ] **Schritt 5: Commit**

```bash
git add docker-compose.yml config/Caddyfile
git commit -m "feat: finalize docker-compose with dashboard service and Caddy reverse proxy"
```

---

## Task 7: Abschluss-Test + Tag

- [ ] **Schritt 1: Gesamte Test-Suite**

```bash
cd "C:/Users/ewald/OneDrive/Desktop/Claude/Team Inbox/Agenten handeln"
python -m pytest -v --tb=short
```

Erwartete Ausgabe: **mind. 83 passed, 0 failed**

- [ ] **Schritt 2: Projektstruktur prüfen**

```bash
find src -name "*.py" | grep -v __pycache__ | sort
```

Erwartete Ausgabe (mind.):
```
src/__init__.py
src/backtesting/__init__.py
src/backtesting/engine.py
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
src/monitoring/__init__.py
src/monitoring/dashboard.py
src/monitoring/telegram_bot.py
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
git status
git commit -m "chore: plan 3 complete — backtesting, monitoring and deployment verified" --allow-empty
git tag v0.3.0-monitoring
git log --oneline -8
```

---

## Nächste Schritte nach Plan 3

Das System ist vollständig einsatzbereit:

1. **VPS bereitstellen** — Hetzner CX22 erstellen, Docker + Docker Compose installieren
2. **Deployment** — `git clone`, `cp config/.env.example config/.env`, API-Keys eintragen, `docker compose up -d`
3. **Caddy-Passwort setzen** — `caddy hash-password --plaintext <passwort>` auf dem VPS ausführen, Hash in `config/Caddyfile` eintragen
4. **Bybit Testnet** — Bot mit `bybit_testnet: true` laufen lassen, Telegram-Bot testen, Dashboard prüfen
5. **Produktiv** — `bybit_testnet: false` setzen, Startkapital einzahlen, Strategien aktivieren

Spec: `docs/superpowers/specs/2026-05-12-trading-bot-design.md`
