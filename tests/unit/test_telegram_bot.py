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
