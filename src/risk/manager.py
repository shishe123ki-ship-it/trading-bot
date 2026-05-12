from __future__ import annotations

from dataclasses import replace

import structlog

from src.core.config import RiskConfig
from src.core.types import Signal
from src.portfolio.tracker import PortfolioTracker

log = structlog.get_logger(__name__)


class RiskManager:
    def __init__(self, config: RiskConfig, portfolio: PortfolioTracker) -> None:
        self._config = config
        self._portfolio = portfolio
        self._paused = False

    def pause(self) -> None:
        self._paused = True
        log.warning("risk_manager_paused")

    def resume(self) -> None:
        self._paused = False
        log.info("risk_manager_resumed")

    @property
    def is_paused(self) -> bool:
        return self._paused

    async def validate(self, signal: Signal) -> Signal | None:
        """Prüft Signal gegen Risk-Limits. Gibt None zurück wenn abgelehnt."""
        if self._paused:
            log.info("signal_rejected_paused", symbol=signal.symbol)
            return None

        # Tages-Verlustlimit
        daily_pnl = await self._portfolio.get_daily_pnl_pct()
        if daily_pnl <= -self._config.daily_loss_limit_pct:
            self.pause()
            log.warning("daily_loss_limit_reached", pnl_pct=round(daily_pnl, 2))
            return None

        # Max Drawdown
        drawdown = await self._portfolio.get_drawdown_pct()
        if drawdown >= self._config.max_drawdown_pct:
            self.pause()
            log.warning("max_drawdown_reached", drawdown_pct=round(drawdown, 2))
            return None

        # Max offene Positionen (Close-Signals ausgenommen)
        if signal.side != "close":
            open_positions = await self._portfolio.get_open_position_count()
            if open_positions >= self._config.max_open_positions:
                log.info("signal_rejected_max_positions", count=open_positions)
                return None

        # Positionsgröße begrenzen
        max_size = self._config.max_position_size_pct / 100
        if signal.size_pct > max_size:
            signal = replace(signal, size_pct=max_size)
            log.info("signal_size_capped", cap=max_size)

        return signal
