import pytest
from datetime import datetime, timezone
from src.strategies.ema_cross import EmaCrossStrategy
from src.strategies.registry import load_strategies, STRATEGY_REGISTRY
from src.core.config import StrategyEntry
from src.core.types import Candle


def _candle(close: float, symbol: str = "BTCUSDT") -> Candle:
    return Candle(
        symbol=symbol, interval="5",
        open_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        open=close * 0.999, high=close * 1.001,
        low=close * 0.998, close=close,
        volume=10.0, is_closed=True,
    )


# --- Registry ---

def test_registry_contains_all_strategies():
    assert "ema_cross" in STRATEGY_REGISTRY
    assert "grid" in STRATEGY_REGISTRY
    assert "bb_reversion" in STRATEGY_REGISTRY


def test_load_strategies_skips_disabled():
    configs = [
        StrategyEntry(name="ema_cross", enabled=True),
        StrategyEntry(name="grid", enabled=False),
    ]
    strategies = load_strategies(configs)
    assert len(strategies) == 1
    assert strategies[0].id == "ema_cross"


def test_load_strategies_raises_for_unknown():
    with pytest.raises(ValueError, match="Unknown strategy"):
        load_strategies([StrategyEntry(name="mystery_strategy", enabled=True)])


def test_load_strategies_empty_list():
    assert load_strategies([]) == []


# --- EMA Cross ---

async def test_ema_cross_returns_none_before_slow_period_warmup():
    cfg = StrategyEntry(name="ema_cross", params={"fast_ema": 3, "slow_ema": 5})
    s = EmaCrossStrategy(config=cfg)
    # Only 4 candles — not enough for slow_ema=5
    for _ in range(4):
        result = await s.on_candle(_candle(100.0))
    assert result is None


async def test_ema_cross_state_has_expected_keys():
    cfg = StrategyEntry(name="ema_cross", params={"fast_ema": 3, "slow_ema": 5})
    s = EmaCrossStrategy(config=cfg)
    state = s.get_state()
    assert "fast_ema" in state
    assert "slow_ema" in state
    assert "in_position" in state
    assert "position_side" in state


async def test_ema_cross_generates_long_signal_on_golden_cross():
    cfg = StrategyEntry(name="ema_cross", params={"fast_ema": 3, "slow_ema": 5, "size_pct": 0.05})
    s = EmaCrossStrategy(config=cfg)

    # Downtrend (fast < slow): 100, 99, 98, 97, 96
    downtrend = [100.0, 99.0, 98.0, 97.0, 96.0]
    # Sharp uptrend (fast crosses above slow): 97, 100, 105, 112
    uptrend = [97.0, 100.0, 105.0, 112.0]

    signals = []
    for p in downtrend + uptrend:
        sig = await s.on_candle(_candle(p))
        if sig:
            signals.append(sig)

    long_signals = [s for s in signals if s.side == "long"]
    assert len(long_signals) >= 1
    assert long_signals[0].strategy_id == "ema_cross"


async def test_ema_cross_generates_short_signal_on_death_cross():
    cfg = StrategyEntry(name="ema_cross", params={"fast_ema": 3, "slow_ema": 5})
    s = EmaCrossStrategy(config=cfg)

    # Uptrend then sharp drop
    uptrend = [100.0, 101.0, 102.0, 103.0, 104.0]
    downtrend = [103.0, 100.0, 95.0, 88.0]

    signals = []
    for p in uptrend + downtrend:
        sig = await s.on_candle(_candle(p))
        if sig:
            signals.append(sig)

    short_signals = [s for s in signals if s.side == "short"]
    assert len(short_signals) >= 1
