# Trading Bot — Plan 1: Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lauffähiges Fundament des Trading Bots: geteilte Datentypen, Event Bus, Konfiguration, Logging, Bybit WebSocket Data Feed und das abstrakte Strategy-Interface.

**Architecture:** Modularer asyncio-Monolith. Alle Module kommunizieren ausschließlich über den Event Bus (keine direkten Imports zwischen Domänenmodulen). Der Data Feed empfängt Bybit-WebSocket-Nachrichten in einem Thread und leitet Events thread-safe an den asyncio-Loop weiter.

**Tech Stack:** Python 3.12, pybit>=5.8, pydantic-settings>=2.0, structlog>=24.0, pyyaml, pytest, pytest-asyncio>=0.23

---

## File Map

| Datei | Verantwortlichkeit |
|---|---|
| `pyproject.toml` | Abhängigkeiten, pytest-Konfiguration |
| `config/config.yaml` | Alle Bot-Parameter |
| `config/.env.example` | API-Key-Vorlage |
| `src/__init__.py` | Paket-Marker |
| `src/core/__init__.py` | Paket-Marker |
| `src/core/types.py` | Geteilte Datenklassen: Candle, Signal, OrderFill, Event, EventType |
| `src/core/event_bus.py` | Async Pub/Sub über asyncio.gather |
| `src/core/config.py` | Settings (pydantic-settings), RiskConfig, StrategyEntry |
| `src/core/logger.py` | structlog-Setup, get_logger() |
| `src/data/__init__.py` | Paket-Marker |
| `src/data/feed.py` | BybitFeed: WebSocket → CANDLE_CLOSED Events |
| `src/strategies/__init__.py` | Paket-Marker |
| `src/strategies/base.py` | Abstrakte BaseStrategy |
| `src/main.py` | Einstiegspunkt: wired alles zusammen, graceful shutdown |
| `tests/__init__.py` | Paket-Marker |
| `tests/unit/__init__.py` | Paket-Marker |
| `tests/unit/test_event_bus.py` | Unit-Tests Event Bus |
| `tests/unit/test_config.py` | Unit-Tests Config |
| `tests/unit/test_feed.py` | Unit-Tests Data Feed (gemockter WebSocket) |
| `tests/unit/test_base_strategy.py` | Unit-Tests BaseStrategy-Interface |
| `Dockerfile` | Python 3.12 slim, non-root user |
| `docker-compose.yml` | Service: trading-bot |

---

## Task 1: Projektgerüst aufsetzen

**Files:**
- Create: `pyproject.toml`
- Create: `config/config.yaml`
- Create: `config/.env.example`
- Create: `src/__init__.py`, `src/core/__init__.py`, `src/data/__init__.py`, `src/strategies/__init__.py`
- Create: `tests/__init__.py`, `tests/unit/__init__.py`

- [ ] **Schritt 1: pyproject.toml anlegen**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "trading-bot"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "pybit>=5.8.0",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "structlog>=24.0",
    "aiohttp>=3.9",
    "aiosqlite>=0.20",
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "python-telegram-bot>=21.0",
    "pandas>=2.2",
    "pyyaml>=6.0",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-mock>=3.12",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.hatch.build.targets.wheel]
packages = ["src"]
```

- [ ] **Schritt 2: config/config.yaml anlegen**

```yaml
bybit_testnet: true

risk:
  max_drawdown_pct: 20.0
  max_position_size_pct: 10.0
  max_open_positions: 3
  daily_loss_limit_pct: 5.0
  leverage: 3

backtesting:
  fee_rate: 0.00055
  slippage_pct: 0.05
  initial_capital: 250.0

strategies:
  - name: ema_cross
    enabled: false
    symbols: ["BTCUSDT"]
    interval: "5"
    params:
      fast_ema: 9
      slow_ema: 21
  - name: grid
    enabled: false
    symbols: ["ETHUSDT"]
    interval: "15"
    params:
      grid_count: 10
      grid_spacing_pct: 0.5
  - name: bb_reversion
    enabled: false
    symbols: ["BTCUSDT"]
    interval: "15"
    params:
      period: 20
      std_dev: 2.0
```

- [ ] **Schritt 3: config/.env.example anlegen**

```
BYBIT_API_KEY=your_api_key_here
BYBIT_API_SECRET=your_api_secret_here
BYBIT_TESTNET=true
TELEGRAM_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

- [ ] **Schritt 4: Alle leeren `__init__.py`-Dateien anlegen**

```bash
touch src/__init__.py src/core/__init__.py src/data/__init__.py
touch src/strategies/__init__.py
touch tests/__init__.py tests/unit/__init__.py
```

- [ ] **Schritt 5: Abhängigkeiten installieren**

```bash
pip install -e ".[dev]"
```

Erwartete Ausgabe: `Successfully installed trading-bot-0.1.0 ...`

- [ ] **Schritt 6: Commit**

```bash
git init
echo "config/.env" >> .gitignore
echo "__pycache__/" >> .gitignore
echo "*.pyc" >> .gitignore
echo ".pytest_cache/" >> .gitignore
git add pyproject.toml config/config.yaml config/.env.example src/ tests/ .gitignore
git commit -m "feat: project scaffold with pyproject.toml and directory structure"
```

---

## Task 2: Geteilte Datentypen

**Files:**
- Create: `src/core/types.py`
- Test: `tests/unit/test_types.py`

- [ ] **Schritt 1: Failing-Test schreiben**

Datei `tests/unit/test_types.py`:

```python
from datetime import datetime, timezone
from src.core.types import (
    Candle, Signal, OrderFill, Event, EventType,
)


def test_candle_creation():
    candle = Candle(
        symbol="BTCUSDT",
        interval="5",
        open_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        open=50000.0,
        high=51000.0,
        low=49000.0,
        close=50500.0,
        volume=10.5,
        is_closed=True,
    )
    assert candle.symbol == "BTCUSDT"
    assert candle.close == 50500.0
    assert candle.is_closed is True


def test_signal_defaults():
    signal = Signal(
        symbol="BTCUSDT",
        side="long",
        size_pct=0.05,
        strategy_id="ema_cross",
    )
    assert signal.entry_price is None
    assert signal.stop_loss is None
    assert signal.take_profit is None


def test_event_type_enum_values():
    assert EventType.CANDLE_CLOSED.value == "candle_closed"
    assert EventType.SIGNAL_GENERATED.value == "signal_generated"
    assert EventType.ORDER_FILLED.value == "order_filled"


def test_event_has_timestamp():
    event = Event(type=EventType.BALANCE_UPDATED, data={"balance": 250.0})
    assert event.timestamp is not None
```

- [ ] **Schritt 2: Test ausführen und Fehler bestätigen**

```bash
pytest tests/unit/test_types.py -v
```

Erwartete Ausgabe: `ImportError: cannot import name 'Candle' from 'src.core.types'`

- [ ] **Schritt 3: `src/core/types.py` implementieren**

```python
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
    size_pct: float  # 0.0–1.0 des verfügbaren Kapitals
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
```

- [ ] **Schritt 4: Tests bestätigen**

```bash
pytest tests/unit/test_types.py -v
```

Erwartete Ausgabe: `4 passed`

- [ ] **Schritt 5: Commit**

```bash
git add src/core/types.py tests/unit/test_types.py
git commit -m "feat: add shared domain types (Candle, Signal, OrderFill, Event)"
```

---

## Task 3: Event Bus

**Files:**
- Create: `src/core/event_bus.py`
- Test: `tests/unit/test_event_bus.py`

- [ ] **Schritt 1: Failing-Test schreiben**

Datei `tests/unit/test_event_bus.py`:

```python
import pytest
from datetime import datetime, timezone
from src.core.event_bus import EventBus
from src.core.types import Candle, Event, EventType


async def test_event_bus_delivers_to_single_subscriber():
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe(EventType.CANDLE_CLOSED, handler)

    candle = Candle(
        symbol="BTCUSDT", interval="5",
        open_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        open=50000.0, high=51000.0, low=49000.0,
        close=50500.0, volume=10.0, is_closed=True,
    )
    await bus.publish(Event(type=EventType.CANDLE_CLOSED, data=candle))

    assert len(received) == 1
    assert received[0].data.symbol == "BTCUSDT"


async def test_event_bus_delivers_to_multiple_subscribers():
    bus = EventBus()
    call_count = 0

    async def handler1(event: Event) -> None:
        nonlocal call_count
        call_count += 1

    async def handler2(event: Event) -> None:
        nonlocal call_count
        call_count += 1

    bus.subscribe(EventType.BALANCE_UPDATED, handler1)
    bus.subscribe(EventType.BALANCE_UPDATED, handler2)

    await bus.publish(Event(type=EventType.BALANCE_UPDATED, data={"balance": 250.0}))

    assert call_count == 2


async def test_event_bus_ignores_events_without_subscribers():
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe(EventType.ORDER_FILLED, handler)
    # Publish a DIFFERENT event type
    await bus.publish(Event(type=EventType.CANDLE_CLOSED, data={}))

    assert len(received) == 0


async def test_event_bus_multiple_event_types_isolated():
    bus = EventBus()
    candle_events: list[Event] = []
    order_events: list[Event] = []

    async def candle_handler(event: Event) -> None:
        candle_events.append(event)

    async def order_handler(event: Event) -> None:
        order_events.append(event)

    bus.subscribe(EventType.CANDLE_CLOSED, candle_handler)
    bus.subscribe(EventType.ORDER_FILLED, order_handler)

    await bus.publish(Event(type=EventType.CANDLE_CLOSED, data={}))
    await bus.publish(Event(type=EventType.ORDER_FILLED, data={}))

    assert len(candle_events) == 1
    assert len(order_events) == 1
```

- [ ] **Schritt 2: Test ausführen und Fehler bestätigen**

```bash
pytest tests/unit/test_event_bus.py -v
```

Erwartete Ausgabe: `ImportError: cannot import name 'EventBus'`

- [ ] **Schritt 3: `src/core/event_bus.py` implementieren**

```python
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Callable, Awaitable

from src.core.types import Event, EventType

Handler = Callable[[Event], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[EventType, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event: Event) -> None:
        handlers = self._handlers.get(event.type, [])
        if handlers:
            await asyncio.gather(*(h(event) for h in handlers))
```

- [ ] **Schritt 4: Tests bestätigen**

```bash
pytest tests/unit/test_event_bus.py -v
```

Erwartete Ausgabe: `4 passed`

- [ ] **Schritt 5: Commit**

```bash
git add src/core/event_bus.py tests/unit/test_event_bus.py
git commit -m "feat: add async event bus with pub/sub"
```

---

## Task 4: Konfiguration

**Files:**
- Create: `src/core/config.py`
- Test: `tests/unit/test_config.py`

- [ ] **Schritt 1: Failing-Test schreiben**

Datei `tests/unit/test_config.py`:

```python
import tempfile
from pathlib import Path
import yaml
from src.core.config import Settings, RiskConfig


def _yaml_settings(data: dict) -> Settings:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        yaml.dump(data, f)
        return Settings.from_yaml(Path(f.name))


def test_settings_loads_defaults_from_empty_yaml():
    settings = _yaml_settings({})
    assert settings.risk.leverage == 3
    assert settings.risk.max_open_positions == 3
    assert settings.bybit_testnet is True


def test_settings_overrides_risk_from_yaml():
    settings = _yaml_settings({"risk": {"leverage": 5, "max_open_positions": 2}})
    assert settings.risk.leverage == 5
    assert settings.risk.max_open_positions == 2
    # Other defaults preserved
    assert settings.risk.max_drawdown_pct == 20.0


def test_settings_loads_strategies_list():
    data = {
        "strategies": [
            {"name": "ema_cross", "enabled": True, "symbols": ["BTCUSDT"], "interval": "5"}
        ]
    }
    settings = _yaml_settings(data)
    assert len(settings.strategies) == 1
    assert settings.strategies[0].name == "ema_cross"
    assert settings.strategies[0].symbols == ["BTCUSDT"]


def test_settings_strategy_has_default_params():
    settings = _yaml_settings({"strategies": [{"name": "grid"}]})
    assert settings.strategies[0].params == {}
    assert settings.strategies[0].enabled is True


def test_risk_config_update_changes_value():
    risk = RiskConfig()
    risk.update("leverage", "7")
    assert risk.leverage == 7


def test_risk_config_update_preserves_other_values():
    risk = RiskConfig(leverage=3, max_open_positions=3)
    risk.update("leverage", "10")
    assert risk.max_open_positions == 3


def test_risk_config_update_unknown_key_raises():
    risk = RiskConfig()
    try:
        risk.update("nonexistent_key", "1")
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "Unknown risk parameter" in str(e)
```

- [ ] **Schritt 2: Test ausführen und Fehler bestätigen**

```bash
pytest tests/unit/test_config.py -v
```

Erwartete Ausgabe: `ImportError: cannot import name 'Settings'`

- [ ] **Schritt 3: `src/core/config.py` implementieren**

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class RiskConfig(BaseModel):
    max_drawdown_pct: float = 20.0
    max_position_size_pct: float = 10.0
    max_open_positions: int = 3
    daily_loss_limit_pct: float = 5.0
    leverage: int = 3

    def update(self, key: str, value: str) -> None:
        if not hasattr(self, key):
            raise ValueError(f"Unknown risk parameter: {key}")
        field_type = type(getattr(self, key))
        setattr(self, key, field_type(value))


class BacktestConfig(BaseModel):
    fee_rate: float = 0.00055
    slippage_pct: float = 0.05
    initial_capital: float = 250.0


class StrategyEntry(BaseModel):
    name: str
    enabled: bool = True
    symbols: list[str] = ["BTCUSDT"]
    interval: str = "5"
    params: dict[str, Any] = {}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="config/.env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    bybit_api_key: str = ""
    bybit_api_secret: str = ""
    bybit_testnet: bool = True
    telegram_token: str = ""
    telegram_chat_id: str = ""

    risk: RiskConfig = RiskConfig()
    backtesting: BacktestConfig = BacktestConfig()
    strategies: list[StrategyEntry] = []

    @classmethod
    def from_yaml(cls, yaml_path: Path = Path("config/config.yaml")) -> Settings:
        data: dict[str, Any] = {}
        if yaml_path.exists():
            with open(yaml_path) as f:
                data = yaml.safe_load(f) or {}
        return cls(**data)
```

- [ ] **Schritt 4: Tests bestätigen**

```bash
pytest tests/unit/test_config.py -v
```

Erwartete Ausgabe: `7 passed`

- [ ] **Schritt 5: Commit**

```bash
git add src/core/config.py tests/unit/test_config.py
git commit -m "feat: add pydantic-settings config with YAML + env support"
```

---

## Task 5: Logger

**Files:**
- Create: `src/core/logger.py`

*(Kein Test — reine Infrastruktur ohne Domänenlogik)*

- [ ] **Schritt 1: `src/core/logger.py` implementieren**

```python
from __future__ import annotations

import logging
import sys

import structlog


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
```

- [ ] **Schritt 2: Smoke-Test in Python-Shell**

```bash
python -c "
from src.core.logger import setup_logging, get_logger
setup_logging()
log = get_logger('smoke')
log.info('logger_works', value=42)
"
```

Erwartete Ausgabe: Eine strukturierte Log-Zeile mit `logger_works` und `value=42`.

- [ ] **Schritt 3: Commit**

```bash
git add src/core/logger.py
git commit -m "feat: add structlog-based logger"
```

---

## Task 6: BaseStrategy

**Files:**
- Create: `src/strategies/base.py`
- Test: `tests/unit/test_base_strategy.py`

- [ ] **Schritt 1: Failing-Test schreiben**

Datei `tests/unit/test_base_strategy.py`:

```python
import pytest
from datetime import datetime, timezone
from src.strategies.base import BaseStrategy
from src.core.types import Candle, Signal, OrderFill
from src.core.config import StrategyEntry


def _make_candle(symbol: str = "BTCUSDT") -> Candle:
    return Candle(
        symbol=symbol, interval="5",
        open_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        open=50000.0, high=51000.0, low=49000.0,
        close=50500.0, volume=10.0, is_closed=True,
    )


def test_base_strategy_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        BaseStrategy(config=StrategyEntry(name="test"))  # type: ignore


def test_strategy_missing_on_candle_raises():
    class Incomplete(BaseStrategy):
        async def on_fill(self, fill: OrderFill) -> None:
            pass
        def get_state(self) -> dict:
            return {}
    with pytest.raises(TypeError):
        Incomplete(config=StrategyEntry(name="incomplete"))


def test_strategy_missing_on_fill_raises():
    class Incomplete(BaseStrategy):
        async def on_candle(self, candle: Candle) -> Signal | None:
            return None
        def get_state(self) -> dict:
            return {}
    with pytest.raises(TypeError):
        Incomplete(config=StrategyEntry(name="incomplete"))


def test_strategy_missing_get_state_raises():
    class Incomplete(BaseStrategy):
        async def on_candle(self, candle: Candle) -> Signal | None:
            return None
        async def on_fill(self, fill: OrderFill) -> None:
            pass
    with pytest.raises(TypeError):
        Incomplete(config=StrategyEntry(name="incomplete"))


async def test_complete_strategy_on_candle_returns_none():
    class PassiveStrategy(BaseStrategy):
        async def on_candle(self, candle: Candle) -> Signal | None:
            return None
        async def on_fill(self, fill: OrderFill) -> None:
            pass
        def get_state(self) -> dict:
            return {"active": False}

    strategy = PassiveStrategy(config=StrategyEntry(name="passive"))
    assert strategy.id == "passive"
    result = await strategy.on_candle(_make_candle())
    assert result is None


async def test_complete_strategy_on_candle_returns_signal():
    class AlwaysBuy(BaseStrategy):
        async def on_candle(self, candle: Candle) -> Signal | None:
            return Signal(
                symbol=candle.symbol,
                side="long",
                size_pct=0.05,
                strategy_id=self.id,
            )
        async def on_fill(self, fill: OrderFill) -> None:
            pass
        def get_state(self) -> dict:
            return {}

    strategy = AlwaysBuy(config=StrategyEntry(name="always_buy"))
    signal = await strategy.on_candle(_make_candle())

    assert signal is not None
    assert signal.side == "long"
    assert signal.size_pct == 0.05
    assert signal.strategy_id == "always_buy"
```

- [ ] **Schritt 2: Test ausführen und Fehler bestätigen**

```bash
pytest tests/unit/test_base_strategy.py -v
```

Erwartete Ausgabe: `ImportError: cannot import name 'BaseStrategy'`

- [ ] **Schritt 3: `src/strategies/base.py` implementieren**

```python
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
```

- [ ] **Schritt 4: Tests bestätigen**

```bash
pytest tests/unit/test_base_strategy.py -v
```

Erwartete Ausgabe: `6 passed`

- [ ] **Schritt 5: Commit**

```bash
git add src/strategies/base.py tests/unit/test_base_strategy.py
git commit -m "feat: add abstract BaseStrategy with Signal return contract"
```

---

## Task 7: Bybit Data Feed

**Files:**
- Create: `src/data/feed.py`
- Test: `tests/unit/test_feed.py`

- [ ] **Schritt 1: Failing-Test schreiben**

Datei `tests/unit/test_feed.py`:

```python
import asyncio
import pytest
from src.data.feed import BybitFeed
from src.core.event_bus import EventBus
from src.core.types import EventType


def _make_kline_message(
    symbol: str = "BTCUSDT",
    interval: str = "5",
    confirm: bool = True,
) -> dict:
    return {
        "topic": f"kline.{interval}.{symbol}",
        "data": [{
            "confirm": confirm,
            "start": 1704067200000,  # 2024-01-01 00:00:00 UTC ms
            "open": "50000",
            "high": "51000",
            "low": "49000",
            "close": "50500",
            "volume": "10.5",
        }],
    }


async def test_handle_kline_publishes_candle_on_closed_candle():
    bus = EventBus()
    received = []

    async def capture(event):
        received.append(event)

    bus.subscribe(EventType.CANDLE_CLOSED, capture)
    feed = BybitFeed(event_bus=bus, testnet=True)
    feed._loop = asyncio.get_running_loop()

    feed._handle_kline(_make_kline_message(confirm=True))
    await asyncio.sleep(0.05)

    assert len(received) == 1
    candle = received[0].data
    assert candle.symbol == "BTCUSDT"
    assert candle.interval == "5"
    assert candle.close == 50500.0
    assert candle.volume == 10.5
    assert candle.is_closed is True


async def test_handle_kline_ignores_open_candle():
    bus = EventBus()
    received = []

    async def capture(event):
        received.append(event)

    bus.subscribe(EventType.CANDLE_CLOSED, capture)
    feed = BybitFeed(event_bus=bus, testnet=True)
    feed._loop = asyncio.get_running_loop()

    feed._handle_kline(_make_kline_message(confirm=False))
    await asyncio.sleep(0.05)

    assert len(received) == 0


async def test_handle_kline_parses_symbol_and_interval_from_topic():
    bus = EventBus()
    received = []

    async def capture(event):
        received.append(event)

    bus.subscribe(EventType.CANDLE_CLOSED, capture)
    feed = BybitFeed(event_bus=bus, testnet=True)
    feed._loop = asyncio.get_running_loop()

    feed._handle_kline(_make_kline_message(symbol="ETHUSDT", interval="15", confirm=True))
    await asyncio.sleep(0.05)

    assert received[0].data.symbol == "ETHUSDT"
    assert received[0].data.interval == "15"


def test_feed_subscribe_stores_subscription():
    bus = EventBus()
    feed = BybitFeed(event_bus=bus, testnet=True)
    feed.subscribe("BTCUSDT", "5")
    feed.subscribe("ETHUSDT", "15")
    assert ("BTCUSDT", "5") in feed._subscriptions
    assert ("ETHUSDT", "15") in feed._subscriptions
```

- [ ] **Schritt 2: Test ausführen und Fehler bestätigen**

```bash
pytest tests/unit/test_feed.py -v
```

Erwartete Ausgabe: `ImportError: cannot import name 'BybitFeed'`

- [ ] **Schritt 3: `src/data/feed.py` implementieren**

```python
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog
from pybit.unified_trading import WebSocket

from src.core.event_bus import EventBus
from src.core.types import Candle, Event, EventType

log = structlog.get_logger(__name__)


class BybitFeed:
    def __init__(self, event_bus: EventBus, testnet: bool = True) -> None:
        self._bus = event_bus
        self._testnet = testnet
        self._ws: WebSocket | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscriptions: list[tuple[str, str]] = []

    def subscribe(self, symbol: str, interval: str) -> None:
        self._subscriptions.append((symbol, interval))

    def _handle_kline(self, message: dict) -> None:
        """Synchroner WebSocket-Callback — Thread-safe Weiterleitung an asyncio."""
        topic: str = message.get("topic", "")
        data_list: list[dict] = message.get("data", [])

        for item in data_list:
            if not item.get("confirm", False):
                continue  # Nur geschlossene Kerzen verarbeiten

            parts = topic.split(".")
            interval = parts[1] if len(parts) == 3 else "1"
            symbol = parts[2] if len(parts) == 3 else "UNKNOWN"

            candle = Candle(
                symbol=symbol,
                interval=interval,
                open_time=datetime.fromtimestamp(
                    item["start"] / 1000, tz=timezone.utc
                ),
                open=float(item["open"]),
                high=float(item["high"]),
                low=float(item["low"]),
                close=float(item["close"]),
                volume=float(item["volume"]),
                is_closed=True,
            )

            if self._loop and not self._loop.is_closed():
                asyncio.run_coroutine_threadsafe(
                    self._bus.publish(
                        Event(type=EventType.CANDLE_CLOSED, data=candle)
                    ),
                    self._loop,
                )

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._ws = WebSocket(
            testnet=self._testnet,
            channel_type="linear",
        )
        for symbol, interval in self._subscriptions:
            self._ws.kline_stream(
                interval=int(interval),
                symbol=symbol,
                callback=self._handle_kline,
            )
            log.info("feed_subscribed", symbol=symbol, interval=interval)
        log.info("feed_started", testnet=self._testnet)

    async def stop(self) -> None:
        if self._ws:
            self._ws.exit()
        log.info("feed_stopped")
```

- [ ] **Schritt 4: Tests bestätigen**

```bash
pytest tests/unit/test_feed.py -v
```

Erwartete Ausgabe: `4 passed`

- [ ] **Schritt 5: Commit**

```bash
git add src/data/feed.py tests/unit/test_feed.py
git commit -m "feat: add Bybit WebSocket data feed with thread-safe asyncio bridge"
```

---

## Task 8: Haupt-Einstiegspunkt

**Files:**
- Create: `src/main.py`

*(Kein Unit-Test — Integration gegen Bybit Testnet manuell)*

- [ ] **Schritt 1: `src/main.py` implementieren**

```python
from __future__ import annotations

import asyncio
import signal
from pathlib import Path

from src.core.config import Settings
from src.core.event_bus import EventBus
from src.core.logger import get_logger, setup_logging
from src.data.feed import BybitFeed

log = get_logger(__name__)


async def main() -> None:
    settings = Settings.from_yaml(Path("config/config.yaml"))
    setup_logging()

    bus = EventBus()
    feed = BybitFeed(event_bus=bus, testnet=settings.bybit_testnet)

    for strategy_cfg in settings.strategies:
        if strategy_cfg.enabled:
            for symbol in strategy_cfg.symbols:
                feed.subscribe(symbol=symbol, interval=strategy_cfg.interval)

    # Graceful Shutdown bei SIGINT/SIGTERM
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    await feed.start()
    log.info("bot_started", testnet=settings.bybit_testnet)

    await stop_event.wait()

    await feed.stop()
    log.info("bot_stopped")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Schritt 2: Alle Tests bestätigen**

```bash
pytest -v
```

Erwartete Ausgabe: `17 passed` (alle bisherigen Tests grün)

- [ ] **Schritt 3: Commit**

```bash
git add src/main.py
git commit -m "feat: add main entry point with graceful shutdown"
```

---

## Task 9: Docker-Setup

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`

- [ ] **Schritt 1: `Dockerfile` anlegen**

```dockerfile
FROM python:3.12-slim

# Non-root user für Sicherheit
RUN useradd --create-home --shell /bin/bash botuser

WORKDIR /app

# Abhängigkeiten zuerst (besseres Layer-Caching)
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Quellcode kopieren
COPY src/ src/

# Kein config/ im Image — wird als Volume eingehängt
USER botuser

CMD ["python", "-m", "src.main"]
```

- [ ] **Schritt 2: `docker-compose.yml` anlegen**

```yaml
version: "3.9"

services:
  trading-bot:
    build: .
    restart: unless-stopped
    env_file: config/.env
    volumes:
      - ./config:/app/config:ro
      - bot-data:/app/data
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

volumes:
  bot-data:
```

- [ ] **Schritt 3: `.dockerignore` anlegen**

```
config/.env
__pycache__/
*.pyc
.pytest_cache/
.git/
tests/
docs/
*.md
```

- [ ] **Schritt 4: Docker-Image bauen**

```bash
docker build -t trading-bot:dev .
```

Erwartete Ausgabe: `Successfully built ...`

- [ ] **Schritt 5: Commit**

```bash
git add Dockerfile docker-compose.yml .dockerignore
git commit -m "feat: add Docker setup with non-root user and volume for config"
```

---

## Task 10: Plan-1-Abschluss-Test

- [ ] **Schritt 1: Gesamten Test-Suite ausführen**

```bash
pytest -v --tb=short
```

Erwartete Ausgabe: `17 passed, 0 failed`

- [ ] **Schritt 2: Manuelle Smoke-Test gegen Bybit Testnet**

1. Testnet-API-Key auf https://testnet.bybit.com erstellen
2. `config/.env` anlegen (aus `.env.example`):
```
BYBIT_API_KEY=<dein_testnet_key>
BYBIT_API_SECRET=<dein_testnet_secret>
BYBIT_TESTNET=true
```
3. Eine Strategie in `config/config.yaml` aktivieren (`enabled: true`)
4. Bot starten:
```bash
python -m src.main
```
5. Im Log erscheinen innerhalb weniger Minuten `candle_closed`-Events für das abonnierte Symbol
6. Mit `Ctrl+C` beenden — `bot_stopped` erscheint im Log

- [ ] **Schritt 3: Finaler Commit mit Tag**

```bash
git add -A
git commit -m "chore: plan 1 complete — foundation layer verified"
git tag v0.1.0-foundation
```

---

## Nächste Schritte

Plan 2 baut auf dieser Basis auf:
- **Risk Manager** — Gatekeeper zwischen Signal und Order
- **Order Manager** — Bybit REST: Order platzieren, tracken, stornieren
- **Portfolio Tracker** — SQLite via aiosqlite, PnL-Berechnung
- **3 Strategien** — Grid, EMA-Crossover, Bollinger-Band Mean-Reversion

Spec: `docs/superpowers/specs/2026-05-12-trading-bot-design.md`
