from __future__ import annotations

from abc import ABC, abstractmethod

from src.core.config import StrategyEntry
from src.core.types import Candle, OrderFill, Signal


class BaseStrategy(ABC):
    def __init__(self, config: StrategyEntry) -> None:
        self.config = config
        self.id = config.name

    @abstractmethod
    async def on_candle(self, candle: Candle) -> Signal | None:
        """Empfängt neue (geschlossene) Kerze; gibt Signal zurück oder None."""

    @abstractmethod
    async def on_fill(self, fill: OrderFill) -> None:
        """Benachrichtigung über ausgeführte Order (wichtig für Grid-State)."""

    @abstractmethod
    def get_state(self) -> dict:
        """Aktueller interner Zustand für Dashboard und Backtesting."""
