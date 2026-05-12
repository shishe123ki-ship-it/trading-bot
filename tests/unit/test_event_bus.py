import pytest
from datetime import datetime, timezone
from src.core.event_bus import EventBus
from src.core.types import Candle, Event, EventType


async def test_event_bus_delivers_to_single_subscriber():
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe(EventType.CANDLE_CLOSED, handler)

    candle = Candle(
        symbol="BTCUSDT", interval="5",
        open_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        open=50000.0, high=51000.0, low=49000.0,
        close=50500.0, volume=10.0, is_closed=True,
    )
    await bus.publish(Event(type=EventType.CANDLE_CLOSED, data=candle))

    assert len(received) == 1
    assert received[0].data.symbol == "BTCUSDT"


async def test_event_bus_delivers_to_multiple_subscribers():
    bus = EventBus()
    call_count = 0

    async def handler1(event: Event) -> None:
        nonlocal call_count
        call_count += 1

    async def handler2(event: Event) -> None:
        nonlocal call_count
        call_count += 1

    bus.subscribe(EventType.BALANCE_UPDATED, handler1)
    bus.subscribe(EventType.BALANCE_UPDATED, handler2)

    await bus.publish(Event(type=EventType.BALANCE_UPDATED, data={"balance": 250.0}))

    assert call_count == 2


async def test_event_bus_ignores_events_without_subscribers():
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe(EventType.ORDER_FILLED, handler)
    await bus.publish(Event(type=EventType.CANDLE_CLOSED, data={}))

    assert len(received) == 0


async def test_event_bus_multiple_event_types_isolated():
    bus = EventBus()
    candle_events: list[Event] = []
    order_events: list[Event] = []

    async def candle_handler(event: Event) -> None:
        candle_events.append(event)

    async def order_handler(event: Event) -> None:
        order_events.append(event)

    bus.subscribe(EventType.CANDLE_CLOSED, candle_handler)
    bus.subscribe(EventType.ORDER_FILLED, order_handler)

    await bus.publish(Event(type=EventType.CANDLE_CLOSED, data={}))
    await bus.publish(Event(type=EventType.ORDER_FILLED, data={}))

    assert len(candle_events) == 1
    assert len(order_events) == 1
