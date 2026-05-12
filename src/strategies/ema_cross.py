from __future__ import annotations

from collections import deque

from src.core.config import StrategyEntry
from src.core.types import Candle, OrderFill, Signal
from src.strategies.base import BaseStrategy


class EmaCrossStrategy(BaseStrategy):
    def __init__(self, config: StrategyEntry) -> None:
        super().__init__(config)
        self._fast_period: int = int(config.params.get("fast_ema", 9))
        self._slow_period: int = int(config.params.get("slow_ema", 21))
        self._size_pct: float = float(config.params.get("size_pct", 0.05))
        self._prices: deque[float] = deque(maxlen=self._slow_period * 3)
        self._fast_ema: float | None = None
        self._slow_ema: float | None = None
        self._in_position = False
        self._position_side: str | None = None

    def _calc_ema(self, period: int, prev_ema: float | None) -> float | None:
        if len(self._prices) < period:
            return None
        if prev_ema is None:
            return sum(list(self._prices)[-period:]) / period
        k = 2.0 / (period + 1)
        return float(self._prices[-1]) * k + prev_ema * (1.0 - k)

    async def on_candle(self, candle: Candle) -> Signal | None:
        self._prices.append(candle.close)

        prev_fast = self._fast_ema
        prev_slow = self._slow_ema

        self._fast_ema = self._calc_ema(self._fast_period, self._fast_ema)
        self._slow_ema = self._calc_ema(self._slow_period, self._slow_ema)

        if None in (self._fast_ema, self._slow_ema, prev_fast, prev_slow):
            return None

        # Golden Cross: fast kreuzt slow von unten → Long
        if prev_fast <= prev_slow and self._fast_ema > self._slow_ema:  # type: ignore[operator]
            if not self._in_position or self._position_side == "short":
                self._in_position = True
                self._position_side = "long"
                return Signal(
                    symbol=candle.symbol, side="long",
                    size_pct=self._size_pct, strategy_id=self.id,
                )

        # Death Cross: fast kreuzt slow von oben → Short
        if prev_fast >= prev_slow and self._fast_ema < self._slow_ema:  # type: ignore[operator]
            if not self._in_position or self._position_side == "long":
                self._in_position = True
                self._position_side = "short"
                return Signal(
                    symbol=candle.symbol, side="short",
                    size_pct=self._size_pct, strategy_id=self.id,
                )

        return None

    async def on_fill(self, fill: OrderFill) -> None:
        pass

    def get_state(self) -> dict:
        return {
            "fast_ema": self._fast_ema,
            "slow_ema": self._slow_ema,
            "in_position": self._in_position,
            "position_side": self._position_side,
        }
