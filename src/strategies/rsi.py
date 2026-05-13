from __future__ import annotations

from collections import deque

import structlog

from src.core.config import StrategyEntry
from src.core.types import Candle, Signal
from src.strategies.base import BaseStrategy

log = structlog.get_logger(__name__)


class RsiStrategy(BaseStrategy):
    def __init__(self, config: StrategyEntry) -> None:
        super().__init__(config)
        self._period = int(config.params.get("period", 14))
        self._oversold = float(config.params.get("oversold", 30.0))
        self._overbought = float(config.params.get("overbought", 70.0))
        self._prices: deque[float] = deque(maxlen=self._period + 1)
        self._rsi: float = 50.0
        self._in_position = False

    async def on_candle(self, candle: Candle) -> Signal | None:
        self._prices.append(candle.close)
        if len(self._prices) < self._period + 1:
            return None

        prices = list(self._prices)
        changes = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
        gains = [c for c in changes if c > 0]
        losses = [-c for c in changes if c < 0]

        avg_gain = sum(gains) / len(changes) if gains else 0.0
        avg_loss = sum(losses) / len(changes) if losses else 0.0

        if avg_gain == 0 and avg_loss == 0:
            self._rsi = 50.0
        elif avg_loss == 0:
            self._rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            self._rsi = 100.0 - 100.0 / (1.0 + rs)

        size_pct = float(self.config.params.get("size_pct", 1.0))

        if self._rsi < self._oversold and not self._in_position:
            self._in_position = True
            return Signal(
                symbol=candle.symbol,
                side="long",
                size_pct=size_pct,
                entry_price=None,
                stop_loss=None,
                take_profit=None,
                strategy_id=self.id,
            )

        if self._rsi > self._overbought and self._in_position:
            self._in_position = False
            return Signal(
                symbol=candle.symbol,
                side="close",
                size_pct=0.0,
                entry_price=None,
                stop_loss=None,
                take_profit=None,
                strategy_id=self.id,
            )

        return None

    async def on_fill(self, fill) -> None:
        pass

    def get_state(self) -> dict:
        return {
            "rsi": round(self._rsi, 2),
            "in_position": self._in_position,
            "period": self._period,
        }
