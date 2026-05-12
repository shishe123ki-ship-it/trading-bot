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

    def subscribe(self, symbol: str, interval: str) -> None:
        self._subscriptions.append((symbol, interval))

    def _handle_kline(self, message: dict) -> None:
        """Synchroner WebSocket-Callback — Thread-safe Weiterleitung an asyncio."""
        topic: str = message.get("topic", "")
        data_list: list[dict] = message.get("data", [])

        for item in data_list:
            if not item.get("confirm", False):
                continue  # Nur geschlossene Kerzen verarbeiten

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
        log.info("feed_started", testnet=self._testnet)

    async def stop(self) -> None:
        if self._ws:
            self._ws.exit()
        log.info("feed_stopped")
