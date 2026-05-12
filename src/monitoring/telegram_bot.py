from __future__ import annotations

import structlog
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from src.backtesting.engine import BacktestEngine
from src.core.config import StrategyEntry
from src.core.event_bus import EventBus
from src.core.types import Event, EventType, OrderFill
from src.portfolio.tracker import PortfolioTracker
from src.risk.manager import RiskManager
from src.strategies.registry import STRATEGY_REGISTRY

log = structlog.get_logger(__name__)


class TelegramMonitor:
    def __init__(
        self,
        token: str,
        chat_id: str,
        event_bus: EventBus,
        risk_manager: RiskManager,
        portfolio: PortfolioTracker,
        backtest_engine: BacktestEngine,
    ) -> None:
        self._token = token
        self._chat_id = chat_id
        self._bus = event_bus
        self._risk = risk_manager
        self._portfolio = portfolio
        self._backtest = backtest_engine
        self._app: Application | None = None

    async def start(self) -> None:
        self._app = Application.builder().token(self._token).build()
        self._app.add_handler(CommandHandler("status", self.cmd_status))
        self._app.add_handler(CommandHandler("pause", self.cmd_pause))
        self._app.add_handler(CommandHandler("resume", self.cmd_resume))
        self._app.add_handler(CommandHandler("set", self.cmd_set))
        self._app.add_handler(CommandHandler("backtest", self.cmd_backtest))
        self._bus.subscribe(EventType.ORDER_FILLED, self._on_order_filled)
        self._bus.subscribe(EventType.RISK_BREACHED, self._on_risk_breached)
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()
        log.info("telegram_monitor_started")

    async def stop(self) -> None:
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

    async def _send(self, text: str) -> None:
        if self._app and self._app.bot:
            try:
                await self._app.bot.send_message(chat_id=self._chat_id, text=text)
            except Exception as exc:
                log.warning("telegram_send_failed", error=str(exc))

    async def _on_order_filled(self, event: Event) -> None:
        fill: OrderFill = event.data
        await self._send(
            f"✅ Order gefüllt: {fill.side} {fill.qty:.4f} {fill.symbol} "
            f"@ {fill.avg_price:.2f} USDT"
        )

    async def _on_risk_breached(self, event: Event) -> None:
        await self._send(f"⚠️ Risk-Limit überschritten: {event.data}")

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        pnl = await self._portfolio.get_realized_pnl()
        positions = await self._portfolio.get_open_position_count()
        daily = await self._portfolio.get_daily_pnl_pct()
        await update.message.reply_text(
            f"📊 Status\n"
            f"Realisierter PnL: {pnl:.4f} USDT\n"
            f"Offene Positionen: {positions}\n"
            f"Tages-PnL: {daily:.2f}%\n"
            f"Bot pausiert: {self._risk.is_paused}"
        )

    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self._risk.pause()
        await update.message.reply_text("⏸ Bot pausiert. Neue Orders werden geblockt.")

    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self._risk.resume()
        await update.message.reply_text("▶️ Bot fortgesetzt.")

    async def cmd_set(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args or len(context.args) != 2:
            await update.message.reply_text(
                "Verwendung: /set <parameter> <wert>\nBeispiel: /set leverage 2"
            )
            return
        key, value = context.args
        try:
            self._risk._config.update(key, value)
            await update.message.reply_text(f"✅ {key} = {value}")
        except ValueError as exc:
            await update.message.reply_text(f"❌ Fehler: {exc}")

    async def cmd_backtest(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args or len(context.args) != 3:
            await update.message.reply_text(
                "Verwendung: /backtest <strategie> <symbol> <tage>\n"
                "Beispiel: /backtest ema_cross BTCUSDT 30"
            )
            return
        strategy_name, symbol, days_str = context.args
        try:
            days = int(days_str)
        except ValueError:
            await update.message.reply_text("❌ <tage> muss eine ganze Zahl sein.")
            return
        cls = STRATEGY_REGISTRY.get(strategy_name)
        if cls is None:
            await update.message.reply_text(
                f"❌ Unbekannte Strategie: '{strategy_name}'. "
                f"Verfügbar: {list(STRATEGY_REGISTRY)}"
            )
            return
        await update.message.reply_text(
            f"🔄 Backtest läuft: {strategy_name} / {symbol} ({days} Tage)…"
        )
        cfg = StrategyEntry(name=strategy_name, symbols=[symbol])
        result = await self._backtest.run(cls, cfg, symbol, days)
        await update.message.reply_text(
            f"📈 Backtest-Ergebnis\n"
            f"Strategie: {strategy_name} / {symbol}\n"
            f"Trades: {result.total_trades}\n"
            f"Win Rate: {result.win_rate:.1%}\n"
            f"PnL: {result.total_pnl:.4f} USDT\n"
            f"Sharpe: {result.sharpe_ratio:.2f}\n"
            f"Max Drawdown: {result.max_drawdown_pct:.2f}%"
        )
