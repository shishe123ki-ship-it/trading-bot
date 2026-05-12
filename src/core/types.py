from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from enum import Enum


@dataclass
class Candle:
    symbol: str
    interval: str
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_closed: bool


@dataclass
class Signal:
    symbol: str
    side: Literal["long", "short", "close"]
    size_pct: float  # 0.0-1.0 des verfügbaren Kapitals
    strategy_id: str
    entry_price: float | None = None  # None = Market Order
    stop_loss: float | None = None
    take_profit: float | None = None


@dataclass
class OrderFill:
    order_id: str
    symbol: str
    side: Literal["Buy", "Sell"]
    qty: float
    avg_price: float
    fee: float
    timestamp: datetime
    strategy_id: str


class EventType(Enum):
    CANDLE_CLOSED = "candle_closed"
    SIGNAL_GENERATED = "signal_generated"
    ORDER_PLACED = "order_placed"
    ORDER_FILLED = "order_filled"
    POSITION_CLOSED = "position_closed"
    RISK_BREACHED = "risk_breached"
    BALANCE_UPDATED = "balance_updated"


@dataclass
class Event:
    type: EventType
    data: Any
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
