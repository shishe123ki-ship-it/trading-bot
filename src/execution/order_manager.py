from __future__ import annotations

from datetime import datetime, timezone

import structlog
from pybit.unified_trading import HTTP

from src.core.config import Settings
from src.core.event_bus import EventBus
from src.core.types import Event, EventType, OrderFill, Signal
from src.portfolio.tracker import PortfolioTracker
from src.risk.manager import RiskManager

log = structlog.get_logger(__name__)


class OrderManager:
    def __init__(
        self,
        event_bus: EventBus,
        settings: Settings,
        risk_manager: RiskManager,
        portfolio: PortfolioTracker,
    ) -> None:
        self._bus = event_bus
        self._settings = settings
        self._risk = risk_manager
        self._portfolio = portfolio
        self._session = HTTP(
            testnet=settings.bybit_testnet,
            api_key=settings.bybit_api_key,
            api_secret=settings.bybit_api_secret,
        )

    def initialize(self) -> None:
        self._bus.subscribe(EventType.SIGNAL_GENERATED, self._on_signal)
        log.info("order_manager_initialized")

    async def _on_signal(self, event: Event) -> None:
        signal: Signal = event.data
        validated = await self._risk.validate(signal)
        if validated is None:
            return
        await self._place_order(validated)

    async def _place_order(self, signal: Signal) -> None:
        try:
            side = "Buy" if signal.side == "long" else "Sell"
            balance = self._settings.backtesting.initial_capital

            if signal.entry_price:
                price = signal.entry_price
                order_type = "Limit"
            else:
                ticker = self._session.get_tickers(
                    category="linear", symbol=signal.symbol
                )
                price = float(ticker["result"]["list"][0]["lastPrice"])
                order_type = "Market"

            qty = self._calc_qty(signal.size_pct, balance, price)

            order_params: dict = {
                "category": "linear",
                "symbol": signal.symbol,
                "side": side,
                "orderType": order_type,
                "qty": qty,
                "timeInForce": "GTC",
                "leverage": str(self._settings.risk.leverage),
            }
            if signal.entry_price:
                order_params["price"] = str(signal.entry_price)
            if signal.stop_loss:
                order_params["stopLoss"] = str(signal.stop_loss)
            if signal.take_profit:
                order_params["takeProfit"] = str(signal.take_profit)

            result = self._session.place_order(**order_params)
            order_id: str = result["result"]["orderId"]

            await self._bus.publish(Event(
                type=EventType.ORDER_PLACED,
                data={"order_id": order_id, "signal": signal},
            ))

            fill = OrderFill(
                order_id=order_id,
                symbol=signal.symbol,
                side=side,
                qty=float(qty),
                avg_price=price,
                fee=float(qty) * price * 0.00055,
                timestamp=datetime.now(tz=timezone.utc),
                strategy_id=signal.strategy_id,
            )
            await self._bus.publish(Event(type=EventType.ORDER_FILLED, data=fill))
            log.info("order_placed", order_id=order_id, symbol=signal.symbol, side=side)

        except Exception as exc:
            log.error("order_placement_failed", error=str(exc), symbol=signal.symbol)

    def _calc_qty(self, size_pct: float, balance: float, price: float) -> str:
        """Berechnet Order-Größe in Base Asset (3 Dezimalstellen)."""
        usdt_amount = balance * size_pct * self._settings.risk.leverage
        qty = usdt_amount / price
        return f"{qty:.5f}"
