from __future__ import annotations

import asyncio
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

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
