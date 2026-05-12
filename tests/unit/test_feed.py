import asyncio
import pytest
from src.data.feed import BybitFeed
from src.core.event_bus import EventBus
from src.core.types import EventType


def _make_kline_message(
    symbol: str = "BTCUSDT",
    interval: str = "5",
    confirm: bool = True,
) -> dict:
    return {
        "topic": f"kline.{interval}.{symbol}",
        "data": [{
            "confirm": confirm,
            "start": 1704067200000,  # 2024-01-01 00:00:00 UTC ms
            "open": "50000",
            "high": "51000",
            "low": "49000",
            "close": "50500",
            "volume": "10.5",
        }],
    }


async def test_handle_kline_publishes_candle_on_closed_candle():
    bus = EventBus()
    received = []

    async def capture(event):
        received.append(event)

    bus.subscribe(EventType.CANDLE_CLOSED, capture)
    feed = BybitFeed(event_bus=bus, testnet=True)
    feed._loop = asyncio.get_running_loop()

    feed._handle_kline(_make_kline_message(confirm=True))
    await asyncio.sleep(0.05)

    assert len(received) == 1
    candle = received[0].data
    assert candle.symbol == "BTCUSDT"
    assert candle.interval == "5"
    assert candle.close == 50500.0
    assert candle.volume == 10.5
    assert candle.is_closed is True


async def test_handle_kline_ignores_open_candle():
    bus = EventBus()
    received = []

    async def capture(event):
        received.append(event)

    bus.subscribe(EventType.CANDLE_CLOSED, capture)
    feed = BybitFeed(event_bus=bus, testnet=True)
    feed._loop = asyncio.get_running_loop()

    feed._handle_kline(_make_kline_message(confirm=False))
    await asyncio.sleep(0.05)

    assert len(received) == 0


async def test_handle_kline_parses_symbol_and_interval_from_topic():
    bus = EventBus()
    received = []

    async def capture(event):
        received.append(event)

    bus.subscribe(EventType.CANDLE_CLOSED, capture)
    feed = BybitFeed(event_bus=bus, testnet=True)
    feed._loop = asyncio.get_running_loop()

    feed._handle_kline(_make_kline_message(symbol="ETHUSDT", interval="15", confirm=True))
    await asyncio.sleep(0.05)

    assert received[0].data.symbol == "ETHUSDT"
    assert received[0].data.interval == "15"


def test_feed_subscribe_stores_subscription():
    bus = EventBus()
    feed = BybitFeed(event_bus=bus, testnet=True)
    feed.subscribe("BTCUSDT", "5")
    feed.subscribe("ETHUSDT", "15")
    assert ("BTCUSDT", "5") in feed._subscriptions
    assert ("ETHUSDT", "15") in feed._subscriptions
