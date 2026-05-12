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
