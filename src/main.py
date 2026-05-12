from __future__ import annotations

import asyncio
import signal
from pathlib import Path

from src.core.config import Settings
from src.core.event_bus import EventBus
from src.core.logger import get_logger, setup_logging
from src.data.feed import BybitFeed

log = get_logger(__name__)


async def main() -> None:
    settings = Settings.from_yaml(Path("config/config.yaml"))
    setup_logging()

    bus = EventBus()
    feed = BybitFeed(event_bus=bus, testnet=settings.bybit_testnet)

    for strategy_cfg in settings.strategies:
        if strategy_cfg.enabled:
            for symbol in strategy_cfg.symbols:
                feed.subscribe(symbol=symbol, interval=strategy_cfg.interval)

    # Graceful Shutdown bei SIGINT/SIGTERM
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    await feed.start()
    log.info("bot_started", testnet=settings.bybit_testnet)

    await stop_event.wait()

    await feed.stop()
    log.info("bot_stopped")


if __name__ == "__main__":
    asyncio.run(main())
