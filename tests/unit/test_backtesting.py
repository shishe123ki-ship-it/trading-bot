import pytest
from unittest.mock import MagicMock, patch
from datetime import timezone
from src.backtesting.engine import BacktestEngine, BacktestResult
from src.core.config import BacktestConfig, StrategyEntry
from src.strategies.ema_cross import EmaCrossStrategy


def _make_settings(fee_rate: float = 0.00055, slippage_pct: float = 0.05, capital: float = 250.0) -> MagicMock:
    s = MagicMock()
    s.bybit_testnet = True
    s.bybit_api_key = "key"
    s.bybit_api_secret = "secret"
    s.backtesting = BacktestConfig(
        fee_rate=fee_rate, slippage_pct=slippage_pct, initial_capital=capital
    )
    return s


def _kline_row(close: float, ts_ms: int) -> list:
    """Bybit kline-Format: [startTime, open, high, low, close, volume, turnover]"""
    return [str(ts_ms), str(close * 0.999), str(close * 1.001), str(close * 0.998), str(close), "10.0", "0"]


def test_backtest_result_dataclass():
    result = BacktestResult(
        strategy_id="ema_cross", symbol="BTCUSDT", days=7,
        total_trades=5, win_rate=0.6, total_pnl=2.5,
        sharpe_ratio=1.2, max_drawdown_pct=3.5,
        equity_curve=[250.0, 251.0, 252.0],
    )
    assert result.strategy_id == "ema_cross"
    assert result.win_rate == pytest.approx(0.6)
    assert len(result.equity_curve) == 3


def test_fetch_ohlcv_parses_bybit_response():
    """_fetch_ohlcv wandelt Bybit-Antwort korrekt um (älteste zuerst)."""
    rows = [
        _kline_row(51000, 1700003600000),  # newer
        _kline_row(50000, 1700000000000),  # older
    ]
    mock_session = MagicMock()
    mock_session.get_kline.return_value = {"result": {"list": rows}}

    with patch("src.backtesting.engine.HTTP", return_value=mock_session):
        engine = BacktestEngine(_make_settings())

    candles = engine._fetch_ohlcv("BTCUSDT", "60", 2)
    assert len(candles) == 2
    assert candles[0].close == pytest.approx(50000.0)   # oldest first
    assert candles[1].close == pytest.approx(51000.0)
    assert candles[0].symbol == "BTCUSDT"
    assert candles[0].interval == "60"


async def test_backtest_run_returns_valid_result():
    """run() gibt BacktestResult mit gültigen Feldern zurück."""
    rows = [_kline_row(float(50000 + i * 200), i * 3_600_000) for i in range(20)]
    mock_session = MagicMock()
    mock_session.get_kline.return_value = {"result": {"list": list(reversed(rows))}}

    with patch("src.backtesting.engine.HTTP", return_value=mock_session):
        engine = BacktestEngine(_make_settings())

    cfg = StrategyEntry(name="ema_cross", params={"fast_ema": 3, "slow_ema": 5})
    result = await engine.run(EmaCrossStrategy, cfg, "BTCUSDT", 7)

    assert isinstance(result, BacktestResult)
    assert result.symbol == "BTCUSDT"
    assert result.days == 7
    assert result.total_trades >= 0
    assert 0.0 <= result.win_rate <= 1.0
    assert result.max_drawdown_pct >= 0.0
    assert len(result.equity_curve) > 0


async def test_backtest_flatline_has_zero_trades():
    """Gleichbleibende Preise → EMA-Crossover generiert keine Signale → 0 Trades."""
    rows = [_kline_row(50000.0, i * 3_600_000) for i in range(20)]
    mock_session = MagicMock()
    mock_session.get_kline.return_value = {"result": {"list": list(reversed(rows))}}

    with patch("src.backtesting.engine.HTTP", return_value=mock_session):
        engine = BacktestEngine(_make_settings())

    cfg = StrategyEntry(name="ema_cross", params={"fast_ema": 3, "slow_ema": 5})
    result = await engine.run(EmaCrossStrategy, cfg, "BTCUSDT", 7)

    assert result.total_trades == 0
    assert result.total_pnl == pytest.approx(0.0)
    assert result.win_rate == pytest.approx(0.0)
    assert result.sharpe_ratio == pytest.approx(0.0)
