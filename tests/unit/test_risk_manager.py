import pytest
from unittest.mock import AsyncMock, MagicMock
from src.risk.manager import RiskManager
from src.core.config import RiskConfig
from src.core.types import Signal


@pytest.fixture
def mock_portfolio():
    p = MagicMock()
    p.get_daily_pnl_pct = AsyncMock(return_value=0.0)
    p.get_drawdown_pct = AsyncMock(return_value=0.0)
    p.get_open_position_count = AsyncMock(return_value=0)
    return p


@pytest.fixture
def risk(mock_portfolio):
    config = RiskConfig(
        max_drawdown_pct=20.0,
        max_position_size_pct=10.0,
        max_open_positions=3,
        daily_loss_limit_pct=5.0,
        leverage=3,
    )
    return RiskManager(config=config, portfolio=mock_portfolio)


def _signal(side: str = "long", size_pct: float = 0.05) -> Signal:
    return Signal(symbol="BTCUSDT", side=side, size_pct=size_pct, strategy_id="test")


async def test_valid_signal_passes(risk):
    result = await risk.validate(_signal())
    assert result is not None
    assert result.symbol == "BTCUSDT"


async def test_paused_manager_rejects_all_signals(risk):
    risk.pause()
    assert await risk.validate(_signal()) is None


async def test_resume_allows_signals_again(risk):
    risk.pause()
    risk.resume()
    assert await risk.validate(_signal()) is not None


async def test_daily_loss_limit_rejects_and_pauses(risk, mock_portfolio):
    mock_portfolio.get_daily_pnl_pct.return_value = -6.0  # Überschreitet 5%-Limit
    result = await risk.validate(_signal())
    assert result is None
    assert risk.is_paused is True


async def test_max_drawdown_rejects_and_pauses(risk, mock_portfolio):
    mock_portfolio.get_drawdown_pct.return_value = 25.0  # Überschreitet 20%-Limit
    result = await risk.validate(_signal())
    assert result is None
    assert risk.is_paused is True


async def test_max_positions_rejects_new_signals(risk, mock_portfolio):
    mock_portfolio.get_open_position_count.return_value = 3  # Am Limit
    result = await risk.validate(_signal())
    assert result is None


async def test_close_signal_not_blocked_by_max_positions(risk, mock_portfolio):
    mock_portfolio.get_open_position_count.return_value = 3  # Am Limit
    close_sig = _signal(side="close", size_pct=1.0)
    result = await risk.validate(close_sig)
    assert result is not None  # Close-Signals immer erlaubt


async def test_oversized_signal_is_capped_to_max(risk):
    big = _signal(size_pct=0.50)  # 50% — weit über 10%-Limit
    result = await risk.validate(big)
    assert result is not None
    assert result.size_pct == pytest.approx(0.10)


async def test_signal_within_limits_unchanged(risk):
    sig = _signal(size_pct=0.05)  # 5% — unter 10%-Limit
    result = await risk.validate(sig)
    assert result is not None
    assert result.size_pct == pytest.approx(0.05)
