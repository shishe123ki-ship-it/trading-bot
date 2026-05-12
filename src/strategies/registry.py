from __future__ import annotations

from src.core.config import StrategyEntry
from src.strategies.base import BaseStrategy
from src.strategies.ema_cross import EmaCrossStrategy

# Grid und BB werden in späteren Tasks hinzugefügt.
# Platzhalter — wird in Task 6 + 7 erweitert.
STRATEGY_REGISTRY: dict[str, type[BaseStrategy]] = {
    "ema_cross": EmaCrossStrategy,
    "grid": EmaCrossStrategy,        # temporärer Platzhalter — wird in Task 6 ersetzt
    "bb_reversion": EmaCrossStrategy, # temporärer Platzhalter — wird in Task 7 ersetzt
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
