from __future__ import annotations

from src.core.config import StrategyEntry
from src.strategies.base import BaseStrategy
from src.strategies.bb_reversion import BollingerReversionStrategy
from src.strategies.ema_cross import EmaCrossStrategy
from src.strategies.grid import GridStrategy
from src.strategies.rsi import RsiStrategy

STRATEGY_REGISTRY: dict[str, type[BaseStrategy]] = {
    "ema_cross": EmaCrossStrategy,
    "grid": GridStrategy,
    "bb_reversion": BollingerReversionStrategy,
    "rsi": RsiStrategy,
}


def load_strategies(configs: list[StrategyEntry]) -> list[BaseStrategy]:
    strategies: list[BaseStrategy] = []
    for cfg in configs:
        if not cfg.enabled:
            continue
        cls = STRATEGY_REGISTRY.get(cfg.name)
        if cls is None:
            raise ValueError(
                f"Unknown strategy: '{cfg.name}'. Available: {list(STRATEGY_REGISTRY)}"
            )
        strategies.append(cls(config=cfg))
    return strategies
