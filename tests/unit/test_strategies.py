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


# --- Grid ---
from src.strategies.grid import GridStrategy


async def test_grid_returns_none_on_first_candle():
    cfg = StrategyEntry(name="grid", params={"grid_count": 4, "grid_spacing_pct": 1.0})
    s = GridStrategy(config=cfg)
    result = await s.on_candle(_candle(100.0))
    assert result is None


async def test_grid_state_initialized_after_first_candle():
    cfg = StrategyEntry(name="grid", params={"grid_count": 4, "grid_spacing_pct": 1.0})
    s = GridStrategy(config=cfg)
    await s.on_candle(_candle(100.0))
    state = s.get_state()
    assert state["initialized"] is True
    assert len(state["grid_levels"]) > 0
    assert state["center_price"] == pytest.approx(100.0)


async def test_grid_generates_buy_signal_on_drop_through_level():
    cfg = StrategyEntry(name="grid", params={"grid_count": 6, "grid_spacing_pct": 1.0})
    s = GridStrategy(config=cfg)

    await s.on_candle(_candle(100.0))  # Initialize at 100.0
    # Grid levels below ~100: 99.0, 98.0, 97.0
    # Drop from 100 to 98.5 should cross the 99.0 level
    result = await s.on_candle(_candle(98.5))
    assert result is not None
    assert result.side == "long"
    assert result.strategy_id == "grid"


async def test_grid_generates_sell_signal_on_rise_through_level():
    cfg = StrategyEntry(name="grid", params={"grid_count": 6, "grid_spacing_pct": 1.0})
    s = GridStrategy(config=cfg)

    await s.on_candle(_candle(100.0))  # Initialize at 100.0
    # Grid levels above ~100: 101.0, 102.0, 103.0
    # Rise from 100 to 101.5 should cross the 101.0 level
    result = await s.on_candle(_candle(101.5))
    assert result is not None
    assert result.side == "short"


async def test_grid_no_signal_if_price_stays_between_levels():
    cfg = StrategyEntry(name="grid", params={"grid_count": 4, "grid_spacing_pct": 2.0})
    s = GridStrategy(config=cfg)
    await s.on_candle(_candle(100.0))  # Initialize
    # Small move that doesn't cross any level (±2% spacing → levels at 98, 102)
    result = await s.on_candle(_candle(100.5))
    assert result is None


# --- Bollinger-Band ---
from src.strategies.bb_reversion import BollingerReversionStrategy
import statistics


async def test_bb_returns_none_before_period_warmup():
    cfg = StrategyEntry(name="bb_reversion", params={"period": 5, "std_dev": 2.0})
    s = BollingerReversionStrategy(config=cfg)
    for _ in range(4):
        result = await s.on_candle(_candle(100.0))
    assert result is None


async def test_bb_state_has_expected_keys():
    cfg = StrategyEntry(name="bb_reversion", params={"period": 3})
    s = BollingerReversionStrategy(config=cfg)
    state = s.get_state()
    assert "sma" in state
    assert "lower_band" in state
    assert "upper_band" in state
    assert "in_position" in state


async def test_bb_generates_long_signal_below_lower_band():
    cfg = StrategyEntry(name="bb_reversion", params={"period": 5, "std_dev": 1.0, "size_pct": 0.05})
    s = BollingerReversionStrategy(config=cfg)

    # Prices with variation to create real bands
    base = [100.0, 101.0, 99.0, 102.0, 98.0]
    for p in base:
        await s.on_candle(_candle(p))

    # Calculate expected lower band
    prices_list = [100.0, 101.0, 99.0, 102.0, 98.0]
    sma = sum(prices_list) / 5
    std = statistics.stdev(prices_list)
    lower = sma - 1.0 * std

    # Drop well below lower band
    result = await s.on_candle(_candle(lower - 5.0))
    assert result is not None
    assert result.side == "long"
    assert result.size_pct == pytest.approx(0.05)


async def test_bb_generates_short_signal_above_upper_band():
    cfg = StrategyEntry(name="bb_reversion", params={"period": 5, "std_dev": 1.0})
    s = BollingerReversionStrategy(config=cfg)

    base = [100.0, 101.0, 99.0, 102.0, 98.0]
    for p in base:
        await s.on_candle(_candle(p))

    prices_list = [100.0, 101.0, 99.0, 102.0, 98.0]
    sma = sum(prices_list) / 5
    std = statistics.stdev(prices_list)
    upper = sma + 1.0 * std

    result = await s.on_candle(_candle(upper + 5.0))
    assert result is not None
    assert result.side == "short"


async def test_bb_generates_close_signal_when_price_returns_to_sma():
    cfg = StrategyEntry(name="bb_reversion", params={"period": 5, "std_dev": 1.0})
    s = BollingerReversionStrategy(config=cfg)

    base = [100.0, 101.0, 99.0, 102.0, 98.0]
    for p in base:
        await s.on_candle(_candle(p))

    # Enter long position
    prices_list = [100.0, 101.0, 99.0, 102.0, 98.0]
    sma = sum(prices_list) / 5
    std = statistics.stdev(prices_list)
    lower = sma - 1.0 * std

    await s.on_candle(_candle(lower - 5.0))
    assert s._in_position is True

    # Price returns to SMA
    result = await s.on_candle(_candle(sma + 0.5))
    assert result is not None
    assert result.side == "close"
    assert s._in_position is False
