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
