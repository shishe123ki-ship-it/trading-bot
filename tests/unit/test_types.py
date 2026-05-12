from datetime import datetime, timezone
from src.core.types import (
    Candle, Signal, OrderFill, Event, EventType,
)


def test_candle_creation():
    candle = Candle(
        symbol="BTCUSDT",
        interval="5",
        open_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        open=50000.0,
        high=51000.0,
        low=49000.0,
        close=50500.0,
        volume=10.5,
        is_closed=True,
    )
    assert candle.symbol == "BTCUSDT"
    assert candle.close == 50500.0
    assert candle.is_closed is True


def test_signal_defaults():
    signal = Signal(
        symbol="BTCUSDT",
        side="long",
        size_pct=0.05,
        strategy_id="ema_cross",
    )
    assert signal.entry_price is None
    assert signal.stop_loss is None
    assert signal.take_profit is None


def test_event_type_enum_values():
    assert EventType.CANDLE_CLOSED.value == "candle_closed"
    assert EventType.SIGNAL_GENERATED.value == "signal_generated"
    assert EventType.ORDER_FILLED.value == "order_filled"


def test_event_has_timestamp():
    event = Event(type=EventType.BALANCE_UPDATED, data={"balance": 250.0})
    assert event.timestamp is not None
