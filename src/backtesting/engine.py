from __future__ import annotations

import asyncio
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone

import structlog
from pybit.unified_trading import HTTP

from src.core.config import Settings, StrategyEntry
from src.core.types import Candle
from src.strategies.base import BaseStrategy

log = structlog.get_logger(__name__)


@dataclass
class BacktestResult:
    strategy_id: str
    symbol: str
    days: int
    total_trades: int
    win_rate: float
    total_pnl: float
    sharpe_ratio: float
    max_drawdown_pct: float
    equity_curve: list[float] = field(default_factory=list)


class BacktestEngine:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._session = HTTP(
            testnet=settings.bybit_testnet,
            api_key=settings.bybit_api_key,
            api_secret=settings.bybit_api_secret,
        )

    async def run(
        self,
        strategy_cls: type[BaseStrategy],
        strategy_cfg: StrategyEntry,
        symbol: str,
        days: int,
    ) -> BacktestResult:
        """Führt Backtest in einem Thread-Pool aus (blockiert asyncio nicht)."""
        return await asyncio.to_thread(
            self._run_sync, strategy_cls, strategy_cfg, symbol, days
        )

    def _run_sync(
        self,
        strategy_cls: type[BaseStrategy],
        strategy_cfg: StrategyEntry,
        symbol: str,
        days: int,
    ) -> BacktestResult:
        interval = strategy_cfg.interval or "60"
        limit = min(days * 24, 1000)
        candles = self._fetch_ohlcv(symbol, interval, limit)
        strategy = strategy_cls(config=strategy_cfg)
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._simulate_async(strategy, candles, symbol, days))
        finally:
            loop.close()

    def _fetch_ohlcv(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        result = self._session.get_kline(
            category="linear", symbol=symbol, interval=interval, limit=limit,
        )
        rows = result.get("result", {}).get("list", [])
        candles: list[Candle] = []
        for row in reversed(rows):  # Bybit gibt neueste zuerst zurück
            candles.append(Candle(
                symbol=symbol,
                interval=interval,
                open_time=datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
                is_closed=True,
            ))
        return candles

    async def _simulate_async(
        self,
        strategy: BaseStrategy,
        candles: list[Candle],
        symbol: str,
        days: int,
    ) -> BacktestResult:
        fee_rate = self._settings.backtesting.fee_rate
        slippage = self._settings.backtesting.slippage_pct / 100
        capital = self._settings.backtesting.initial_capital
        equity = capital
        peak = capital
        equity_curve: list[float] = [equity]
        max_drawdown = 0.0
        trade_pnls: list[float] = []
        trade_returns: list[float] = []
        position: dict | None = None

        for candle in candles:
            sig = await strategy.on_candle(candle)
            if sig is None:
                continue

            price = candle.close

            if sig.side in ("long", "short") and position is None:
                entry = price * (1 + slippage if sig.side == "long" else 1 - slippage)
                fee = capital * sig.size_pct * fee_rate
                equity -= fee
                position = {
                    "side": sig.side,
                    "entry": entry,
                    "notional": capital * sig.size_pct,
                }

            elif sig.side == "close" and position is not None:
                exit_p = price * (1 - slippage if position["side"] == "long" else 1 + slippage)
                fee = position["notional"] * fee_rate
                pnl_pct = (exit_p - position["entry"]) / position["entry"]
                if position["side"] == "short":
                    pnl_pct = -pnl_pct
                pnl = position["notional"] * pnl_pct - fee
                equity += pnl
                trade_pnls.append(pnl)
                trade_returns.append(pnl / position["notional"])
                position = None

            peak = max(peak, equity)
            dd = (peak - equity) / peak * 100 if peak > 0 else 0.0
            max_drawdown = max(max_drawdown, dd)
            equity_curve.append(equity)

        total_trades = len(trade_pnls)
        winners = [p for p in trade_pnls if p > 0]
        win_rate = len(winners) / total_trades if total_trades > 0 else 0.0
        total_pnl = sum(trade_pnls)
        sharpe = self._sharpe(trade_returns)

        log.info(
            "backtest_complete",
            strategy=strategy.id, symbol=symbol,
            trades=total_trades, win_rate=round(win_rate, 3), pnl=round(total_pnl, 4),
        )
        return BacktestResult(
            strategy_id=strategy.id, symbol=symbol, days=days,
            total_trades=total_trades, win_rate=win_rate, total_pnl=total_pnl,
            sharpe_ratio=sharpe, max_drawdown_pct=max_drawdown, equity_curve=equity_curve,
        )

    @staticmethod
    def _sharpe(returns: list[float]) -> float:
        if len(returns) < 2:
            return 0.0
        mean = statistics.mean(returns)
        std = statistics.stdev(returns)
        if std == 0:
            return 0.0
        return mean / std * (252 ** 0.5)
