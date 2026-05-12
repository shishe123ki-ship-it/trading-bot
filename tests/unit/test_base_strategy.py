import pytest
from datetime import datetime, timezone
from src.strategies.base import BaseStrategy
from src.core.types import Candle, Signal, OrderFill
from src.core.config import StrategyEntry


def _make_candle(symbol: str = "BTCUSDT") -> Candle:
    return Candle(
        symbol=symbol, interval="5",
        open_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        open=50000.0, high=51000.0, low=49000.0,
        close=50500.0, volume=10.0, is_closed=True,
    )


def test_base_strategy_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        BaseStrategy(config=StrategyEntry(name="test"))  # type: ignore


def test_strategy_missing_on_candle_raises():
    class Incomplete(BaseStrategy):
        async def on_fill(self, fill: OrderFill) -> None:
            pass
        def get_state(self) -> dict:
            return {}
    with pytest.raises(TypeError):
        Incomplete(config=StrategyEntry(name="incomplete"))


def test_strategy_missing_on_fill_raises():
    class Incomplete(BaseStrategy):
        async def on_candle(self, candle: Candle) -> Signal | None:
            return None
        def get_state(self) -> dict:
            return {}
    with pytest.raises(TypeError):
        Incomplete(config=StrategyEntry(name="incomplete"))


def test_strategy_missing_get_state_raises():
    class Incomplete(BaseStrategy):
        async def on_candle(self, candle: Candle) -> Signal | None:
            return None
        async def on_fill(self, fill: OrderFill) -> None:
            pass
    with pytest.raises(TypeError):
        Incomplete(config=StrategyEntry(name="incomplete"))


async def test_complete_strategy_on_candle_returns_none():
    class PassiveStrategy(BaseStrategy):
        async def on_candle(self, candle: Candle) -> Signal | None:
            return None
        async def on_fill(self, fill: OrderFill) -> None:
            pass
        def get_state(self) -> dict:
            return {"active": False}

    strategy = PassiveStrategy(config=StrategyEntry(name="passive"))
    assert strategy.id == "passive"
    result = await strategy.on_candle(_make_candle())
    assert result is None


async def test_complete_strategy_on_candle_returns_signal():
    class AlwaysBuy(BaseStrategy):
        async def on_candle(self, candle: Candle) -> Signal | None:
            return Signal(
                symbol=candle.symbol,
                side="long",
                size_pct=0.05,
                strategy_id=self.id,
            )
        async def on_fill(self, fill: OrderFill) -> None:
            pass
        def get_state(self) -> dict:
            return {}

    strategy = AlwaysBuy(config=StrategyEntry(name="always_buy"))
    signal = await strategy.on_candle(_make_candle())

    assert signal is not None
    assert signal.side == "long"
    assert signal.size_pct == 0.05
    assert signal.strategy_id == "always_buy"
