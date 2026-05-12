from __future__ import annotations

from src.core.config import StrategyEntry
from src.core.types import Candle, OrderFill, Signal
from src.strategies.base import BaseStrategy


class GridStrategy(BaseStrategy):
    def __init__(self, config: StrategyEntry) -> None:
        super().__init__(config)
        self._grid_count: int = int(config.params.get("grid_count", 10))
        self._grid_spacing_pct: float = float(config.params.get("grid_spacing_pct", 0.5)) / 100
        self._size_pct: float = float(config.params.get("size_pct", 0.02))
        self._initialized = False
        self._center_price: float | None = None
        self._grid_levels: list[float] = []
        self._last_price: float | None = None

    def _build_grid(self, center: float) -> None:
        half = self._grid_count // 2
        self._grid_levels = [
            round(center * (1.0 + i * self._grid_spacing_pct), 8)
            for i in range(-half, half + 1)
            if i != 0
        ]
        self._center_price = center

    async def on_candle(self, candle: Candle) -> Signal | None:
        price = candle.close

        if not self._initialized:
            self._build_grid(price)
            self._initialized = True
            self._last_price = price
            return None

        if self._last_price is None:
            self._last_price = price
            return None

        signal: Signal | None = None

        for level in self._grid_levels:
            if level < self._center_price:  # type: ignore[operator]
                # Kauflevel: Preis fällt durch dieses Level
                if self._last_price > level >= price:
                    signal = Signal(
                        symbol=candle.symbol, side="long",
                        size_pct=self._size_pct, strategy_id=self.id,
                        entry_price=level,
                    )
                    break
            else:
                # Verkauflevel: Preis steigt durch dieses Level
                if self._last_price < level <= price:
                    signal = Signal(
                        symbol=candle.symbol, side="short",
                        size_pct=self._size_pct, strategy_id=self.id,
                        entry_price=level,
                    )
                    break

        self._last_price = price
        return signal

    async def on_fill(self, fill: OrderFill) -> None:
        pass

    def get_state(self) -> dict:
        return {
            "initialized": self._initialized,
            "center_price": self._center_price,
            "grid_levels": self._grid_levels,
            "last_price": self._last_price,
        }
