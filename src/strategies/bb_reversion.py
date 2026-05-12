from __future__ import annotations

import statistics
from collections import deque

from src.core.config import StrategyEntry
from src.core.types import Candle, OrderFill, Signal
from src.strategies.base import BaseStrategy


class BollingerReversionStrategy(BaseStrategy):
    def __init__(self, config: StrategyEntry) -> None:
        super().__init__(config)
        self._period: int = int(config.params.get("period", 20))
        self._std_dev: float = float(config.params.get("std_dev", 2.0))
        self._size_pct: float = float(config.params.get("size_pct", 0.05))
        self._prices: deque[float] = deque(maxlen=self._period)
        self._in_position = False
        self._position_side: str | None = None

    def _bands(self) -> tuple[float, float, float] | None:
        if len(self._prices) < self._period:
            return None
        prices = list(self._prices)
        sma = sum(prices) / self._period
        std = statistics.stdev(prices)
        return (
            sma - self._std_dev * std,
            sma,
            sma + self._std_dev * std,
        )

    async def on_candle(self, candle: Candle) -> Signal | None:
        # Bänder anhand der bisherigen Preise berechnen (vor dem Append)
        bands = self._bands()
        self._prices.append(candle.close)
        if bands is None:
            return None

        lower, sma, upper = bands
        price = candle.close

        # Position schließen wenn Preis zur SMA zurückkehrt
        if self._in_position:
            if self._position_side == "long" and price >= sma:
                self._in_position = False
                self._position_side = None
                return Signal(
                    symbol=candle.symbol, side="close",
                    size_pct=1.0, strategy_id=self.id,
                )
            if self._position_side == "short" and price <= sma:
                self._in_position = False
                self._position_side = None
                return Signal(
                    symbol=candle.symbol, side="close",
                    size_pct=1.0, strategy_id=self.id,
                )

        # Neue Position eröffnen bei Banddurchbruch
        if not self._in_position:
            if price < lower:
                self._in_position = True
                self._position_side = "long"
                return Signal(
                    symbol=candle.symbol, side="long",
                    size_pct=self._size_pct, strategy_id=self.id,
                )
            if price > upper:
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
        bands = self._bands()
        lower, sma, upper = bands if bands else (None, None, None)
        return {
            "lower_band": lower,
            "sma": sma,
            "upper_band": upper,
            "in_position": self._in_position,
            "position_side": self._position_side,
        }
