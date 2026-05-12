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
