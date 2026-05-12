# Trading Bot — Design Spec
**Datum:** 2026-05-12  
**Status:** Genehmigt  
**Ziel:** Vollautomatisches, 24/7 laufendes Krypto-Futures-Trading-System auf Basis eines modularen Python-Monolithen, betrieben via Docker auf einem VPS.

---

## 1. Anforderungen

| Kategorie | Entscheidung |
|---|---|
| Handelsziel | Vollautomatisches Einkommen — konstante kleine Gewinne |
| Risikoverwaltung | Vollständig konfigurierbar per YAML-Parameter |
| Instrumente | Krypto-Futures / Perpetuals (Bybit) |
| Strategie-Ansatz | Modulares Multi-Strategie-Framework mit Backtesting-Pipeline |
| Monitoring | Telegram (Alerts + Befehle) + Web-Dashboard (FastAPI + HTMX) |
| Deployment | Docker-Container auf Linux-VPS (Hetzner CX22, ~4 €/Monat) |

---

## 2. Plattform-Entscheidung: Bybit

### Vergleich

| Name | Fees (Futures) | Min. Deposit | API-Qualität | Latenz | Sandbox | Verdikt |
|---|---|---|---|---|---|---|
| **Bybit** | 0.02% Maker / 0.055% Taker | 0 € | ★★★★★ | Sehr gut | ✅ Testnet | **Gewählt** |
| Binance | 0.02% / 0.05% | 0 € | ★★★★★ | Ausgezeichnet | ✅ Testnet | DE-Regulierung unsicher |
| OKX | 0.02% / 0.05% | 0 € | ★★★★☆ | Gut | ✅ Demo | Gute Alternative |
| Kraken | 0.02% / 0.05% | 0 € | ★★★☆☆ | Mittel | ❌ | Kein Futures-Sandbox |
| Bitget | 0.02% / 0.06% | 0 € | ★★★☆☆ | Mittel | ✅ | Backup-Option |
| KuCoin | 0.02% / 0.06% | 0 € | ★★★★☆ | Gut | ✅ | Kleinere Liquidität |

### Begründung
- Offizielles `pybit` Python-SDK, aktiv gepflegt
- Testnet mit identischer API — risikofreie Entwicklung
- Kein Mindesteinzahlungslimit (passt zu 250 € Startkapital)
- Perpetual Futures mit konfigurierbarem Hebel (1x–100x)
- In Deutschland legal nutzbar

---

## 3. Architektur: Modularer Monolith mit asyncio

### Leitprinzip
Alle Module kommunizieren ausschließlich über einen internen **Event Bus** (asyncio-Queues). Kein Modul importiert ein anderes direkt. Dies ermöglicht isoliertes Testen und einfaches Ersetzen einzelner Komponenten.

### Systemdiagramm

```
┌─────────────────────────────────────────────────────────┐
│                    Trading Bot Process                   │
│                                                         │
│  ┌──────────┐    ┌─────────────┐    ┌───────────────┐  │
│  │ Data Feed│───▶│  Event Bus  │◀───│  Order Manager│  │
│  │(WebSocket│    │  (asyncio   │    │  (Bybit REST/ │  │
│  │  Bybit)  │    │   queues)   │    │   WebSocket)  │  │
│  └──────────┘    └──────┬──────┘    └───────────────┘  │
│                         │                    ▲          │
│              ┌──────────┼──────────┐         │          │
│              ▼          ▼          ▼         │          │
│  ┌──────────────┐ ┌──────────┐ ┌──────────┐ │          │
│  │  Strategy    │ │  Risk    │ │Portfolio │ │          │
│  │  Engine      │ │  Manager │ │ Tracker  │ │          │
│  │  (Plugins)   │─▶(Gating) ─▶│  (SQLite)│─┘          │
│  └──────────────┘ └──────────┘ └──────────┘            │
│                                                         │
│  ┌──────────────┐              ┌───────────────────┐   │
│  │  Backtester  │              │  Monitoring Layer │   │
│  │(ProcessPool) │              │ Telegram│Dashboard│   │
│  └──────────────┘              └───────────────────┘   │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │           Config Manager (YAML + .env)           │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### Verzeichnisstruktur

```
trading-bot/
├── config/
│   ├── config.yaml          # Alle Parameter (Symbole, Hebel, Risiko...)
│   └── .env                 # API-Keys, Telegram-Token (nie in git)
├── src/
│   ├── core/
│   │   ├── event_bus.py     # Zentraler pub/sub über asyncio-Queues
│   │   ├── config.py        # Config-Loader & Validierung (pydantic-settings)
│   │   └── logger.py        # Strukturiertes Logging (structlog)
│   ├── data/
│   │   └── feed.py          # Bybit WebSocket → OHLCV, Orderbook
│   ├── strategies/
│   │   ├── base.py          # Abstract BaseStrategy
│   │   ├── grid.py          # Grid-Trading
│   │   ├── ema_cross.py     # EMA-Crossover Trend-Following
│   │   └── bb_reversion.py  # Bollinger-Band Mean-Reversion
│   ├── risk/
│   │   └── manager.py       # Positionsgröße, Drawdown-Guard, Max-Exposure
│   ├── execution/
│   │   └── order_manager.py # Order-Placement, Tracking, Cancellation
│   ├── portfolio/
│   │   └── tracker.py       # PnL, offene Positionen, Balance (SQLite)
│   ├── backtesting/
│   │   └── engine.py        # Historische Simulation (ProcessPoolExecutor)
│   └── monitoring/
│       ├── telegram_bot.py  # Push-Alerts + Steuerungs-Befehle
│       └── dashboard.py     # FastAPI + HTMX Web-UI
├── tests/
│   ├── unit/
│   └── integration/
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```

---

## 4. Kernmodule

### 4.1 Event Bus

```python
class EventType(Enum):
    CANDLE_CLOSED    = "candle_closed"
    SIGNAL_GENERATED = "signal_generated"
    ORDER_PLACED     = "order_placed"
    ORDER_FILLED     = "order_filled"
    POSITION_CLOSED  = "position_closed"
    RISK_BREACHED    = "risk_breached"
    BALANCE_UPDATED  = "balance_updated"
```

**Trade-Datenfluss:**
```
DataFeed → CANDLE_CLOSED → StrategyEngine → SIGNAL_GENERATED
         → RiskManager (Gate) → ORDER_PLACED
         → OrderManager → ORDER_FILLED
         → PortfolioTracker + Telegram-Alert
```

### 4.2 Strategy Plugin Interface

Jede Strategie erbt von `BaseStrategy` und implementiert drei Methoden:

```python
class BaseStrategy(ABC):
    @abstractmethod
    async def on_candle(self, candle: Candle) -> Signal | None: ...

    @abstractmethod
    async def on_fill(self, fill: OrderFill) -> None: ...

    @abstractmethod
    def get_state(self) -> dict: ...
```

**Signal-Objekt:**
```python
@dataclass
class Signal:
    symbol: str
    side: Literal["long", "short", "close"]
    size_pct: float        # 0.0–1.0 des verfügbaren Kapitals
    entry_price: float | None   # None = Market Order
    stop_loss: float | None
    take_profit: float | None
    strategy_id: str
```

Neue Strategie hinzufügen: neue Datei in `strategies/`, in `config.yaml` aktivieren. Kein Umbau des Kerns nötig.

### 4.3 Risk Manager

Gatekeeper zwischen Signal und Order-Placement. Konfigurierbar per YAML:

```yaml
risk:
  max_drawdown_pct: 20        # Bot pausiert bei -20% Gesamtkapital
  max_position_size_pct: 10   # Kein Trade > 10% des Portfolios
  max_open_positions: 3       # Maximal 3 gleichzeitige Positionen
  daily_loss_limit_pct: 5     # Stop-Trading nach -5% an einem Tag
  leverage: 3                 # Standard-Hebel (empfohlen: 1–10)
```

Alle Parameter zur Laufzeit per Telegram-Befehl änderbar (`/set risk.leverage 2`).

### 4.4 Portfolio Tracker

- Persistiert alle Trades in SQLite (`aiosqlite`)
- Berechnet: realisierter PnL, unrealisierter PnL, Equity-Kurve, Win Rate
- Wird vom Dashboard gelesen (read-only Zugriff)

### 4.5 Backtesting Engine

- Läuft in `ProcessPoolExecutor` — blockiert Live-Loop nicht
- Zieht historische OHLCV-Daten via Bybit REST API (bis 2 Jahre)
- Nutzt dieselben `BaseStrategy`-Klassen wie Live-Trading
- Simuliert Fees (`0.00055`) und Slippage (`0.05%`) konfigurierbar
- Output: Sharpe Ratio, Max Drawdown, Win Rate, PnL-Kurve als JSON

**Strategie-Promotion-Pipeline:**
```
Strategie schreiben
  → Backtest lokal
  → Ergebnisse im Dashboard prüfen
  → Paper Trading auf Bybit Testnet
  → Live mit kleiner Position (z.B. 5% Kapital)
```

---

## 5. Monitoring

### Telegram-Befehle
| Befehl | Funktion |
|---|---|
| `/status` | Aktuelles Portfolio, PnL, offene Positionen |
| `/pause` | Keine neuen Trades, offene Positionen bleiben |
| `/resume` | Trading fortsetzen |
| `/set <key> <value>` | Parameter live ändern |
| `/backtest <strategy> <symbol> <days>` | Backtest anstoßen |

### Web-Dashboard
- **Framework:** FastAPI + HTMX (kein JavaScript-Framework)
- **Seiten:** Portfolio-Übersicht, Trade-History, aktive Strategien, Log-Stream
- **Port:** 8080, erreichbar per SSH-Tunnel oder Caddy + Basic-Auth
- **Datenquelle:** SQLite (read-only), Live-Updates via Server-Sent Events

---

## 6. Deployment

### Docker-Setup (3 Services)

```
┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│  trading-   │   │  dashboard  │   │   caddy     │
│    bot      │   │  (FastAPI   │   │  (Reverse   │
│  (Python)   │   │  Port 8080) │   │   Proxy +   │
│             │   │             │   │   HTTPS)    │
└──────┬──────┘   └──────┬──────┘   └─────────────┘
       └────────┬─────────┘
                │
         ┌──────▼──────┐
         │   SQLite    │
         │  (Volume)   │
         └─────────────┘
```

### Sicherheit
- API-Keys ausschließlich in `.env`, nie im Docker-Image
- Dashboard nur per SSH-Tunnel oder Caddy + Basic-Auth erreichbar
- Kein Root-User im Container
- `restart: unless-stopped` für automatischen Neustart

### VPS-Empfehlung
**Hetzner CX22** — 2 vCPU, 4 GB RAM, 40 GB SSD — ~4 €/Monat

---

## 7. Tech-Stack

| Komponente | Technologie |
|---|---|
| Sprache | Python 3.12 |
| Async Runtime | `asyncio` + `aiohttp` |
| Bybit-Anbindung | `pybit` (offizielles SDK) |
| Config-Validierung | `pydantic-settings` |
| Datenbank | SQLite via `aiosqlite` |
| Web-Dashboard | `FastAPI` + `HTMX` |
| Telegram | `python-telegram-bot` |
| Backtesting | `pandas` + `ProcessPoolExecutor` |
| Logging | `structlog` |
| Deployment | `Docker` + `docker-compose` |

---

## 8. Enthaltene Strategien (MVP)

| Strategie | Datei | Beschreibung |
|---|---|---|
| Grid Trading | `grid.py` | Kauf-/Verkaufsorders in konfigurierbaren Preisabständen |
| EMA-Crossover | `ema_cross.py` | Trend-Following via Fast/Slow EMA |
| Bollinger-Band | `bb_reversion.py` | Mean-Reversion bei Über-/Unterschreiten der Bänder |

---

## 9. Testing-Strategie

- **Unit-Tests:** Jedes Modul isoliert testbar (Event Bus gemockt)
- **Strategie-Tests:** Backtesting-Engine mit bekannten historischen Daten
- **Integration-Tests:** Gegen Bybit Testnet (Paper Trading)
- **Kein Live-Geld** bis alle Integrationstests grün sind
