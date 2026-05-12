# Trading Bot – Project Memory

## Projektziel
Vollautomatischer 24/7 Krypto-Futures-Trading-Bot für Bybit.
Startkapital: ~250 €. Plattform: Bybit Perpetuals. Sprache: Python 3.12.

---

## Aktueller Stand (2026-05-12)

### Implementierte Pläne
| Plan | Tag | Tests | Status |
|---|---|---|---|
| Plan 1 – Foundation (Core, Data, Config) | `v0.1.0-foundation` | 16 | ✅ Abgeschlossen |
| Plan 2 – Trading Core (Strategies, Risk, Orders, Portfolio) | `v0.2.0-trading-core` | 65 | ✅ Abgeschlossen |
| Plan 3 – Monitoring & Deployment (Backtesting, Telegram, Dashboard, Docker) | (noch kein Tag) | 83 | ⏳ Tasks 1–4 fertig, Tasks 5–7 offen |

**Aktueller Test-Stand:** `83 passed` — letzter Commit: `7c1f93e`

---

## Fertige Dateien

### Core (Plan 1)
| Datei | Beschreibung |
|---|---|
| `src/core/types.py` | Candle, Signal, OrderFill, Event, EventType, BacktestConfig, RiskConfig |
| `src/core/config.py` | Settings (pydantic-settings v2), StrategyEntry, BacktestConfig, RiskConfig |
| `src/core/event_bus.py` | Asyncio pub/sub EventBus — sync + async Handler, gather-basiert |
| `src/core/logger.py` | structlog Setup |
| `src/data/feed.py` | BybitFeed — pybit WebSocket, CANDLE_CLOSED Events |

### Trading Core (Plan 2)
| Datei | Beschreibung |
|---|---|
| `src/portfolio/tracker.py` | SQLite-Portfolio (aiosqlite), PnL, Drawdown, Positions |
| `src/risk/manager.py` | RiskManager — daily_loss, max_drawdown, max_positions, leverage-Cap |
| `src/execution/order_manager.py` | OrderManager — Bybit REST, Position-Sizing, ORDER_PLACED/FILLED Events |
| `src/strategies/base.py` | BaseStrategy ABC mit `id`, `config`, `on_candle`, `on_fill`, `get_state` |
| `src/strategies/ema_cross.py` | EMA-Crossover (Golden/Death Cross) |
| `src/strategies/grid.py` | Grid-Trading (Preis-Level-Durchbruch) |
| `src/strategies/bb_reversion.py` | Bollinger-Band Mean-Reversion |
| `src/strategies/registry.py` | STRATEGY_REGISTRY + load_strategies() |
| `src/main.py` | Haupt-Orchestrierung: alle Komponenten verdrahtet + TelegramMonitor optional |

### Monitoring & Deployment (Plan 3 — Teilweise fertig)
| Datei | Beschreibung | Status |
|---|---|---|
| `src/backtesting/__init__.py` | Paket-Stub | ✅ |
| `src/backtesting/engine.py` | BacktestEngine: OHLCV-Fetch (Bybit REST), Strategie-Simulation, Metriken | ✅ |
| `src/monitoring/__init__.py` | Paket-Stub | ✅ |
| `src/monitoring/telegram_bot.py` | TelegramMonitor: Push-Alerts + /pause /resume /status /set /backtest | ✅ |
| `src/monitoring/dashboard.py` | FastAPI Dashboard: /api/portfolio, /api/trades, HTMX-Partials, SSE | ✅ |
| `src/monitoring/templates/index.html` | Hauptseite (Dark-Theme, HTMX-Polling) | ✅ |
| `src/monitoring/templates/partials/portfolio.html` | Portfolio-Metriken-Fragment | ✅ |
| `src/monitoring/templates/partials/trades.html` | Trades-Tabelle-Fragment | ✅ |
| `docker-compose.yml` | Noch nicht finalisiert (nur trading-bot Service) | ⏳ Task 6 |
| `config/Caddyfile` | Noch nicht erstellt | ⏳ Task 6 |

### Tests
| Datei | Anzahl | Was getestet wird |
|---|---|---|
| `tests/unit/test_event_bus.py` | – | EventBus pub/sub |
| `tests/unit/test_portfolio_tracker.py` | 8 | SQLite-Persistenz, PnL, Drawdown |
| `tests/unit/test_risk_manager.py` | 9 | daily_loss, drawdown, positions, pause/resume |
| `tests/unit/test_order_manager.py` | 4 | Qty-Berechnung, Signal-Verarbeitung |
| `tests/unit/test_strategies.py` | 18 | EMA, Grid, Bollinger-Band (TDD) |
| `tests/unit/test_backtesting.py` | 4 | BacktestResult, OHLCV-Parsing, run(), Flatline |
| `tests/unit/test_telegram_bot.py` | 8 | Push-Alerts, Commands (mit Auth-Guard) |
| `tests/unit/test_dashboard.py` | 6 | FastAPI-Endpoints (httpx AsyncClient) |

---

## Offene Tasks (Plan 3)

### Task 5: main.py — BacktestEngine + Telegram verdrahten
**Datei:** `src/main.py` (modifizieren)

main.py muss ergänzt werden um:
```python
from src.backtesting.engine import BacktestEngine
...
backtest_engine = BacktestEngine(settings=settings)
...
# Telegram Monitor (optional)
if settings.telegram_token and settings.telegram_chat_id:
    from src.monitoring.telegram_bot import TelegramMonitor
    monitor = TelegramMonitor(
        token=settings.telegram_token,
        chat_id=settings.telegram_chat_id,
        event_bus=bus,
        risk_manager=risk,
        portfolio=tracker,
        backtest_engine=backtest_engine,
    )
    await monitor.start()
...
if monitor:
    await monitor.stop()
```
Nach diesem Task: `python -m pytest -v --tb=short` → mind. 83 passed

### Task 6: Docker-Compose-Finalisierung
**Dateien:** `docker-compose.yml` (ersetzen), `config/Caddyfile` (neu)

`docker-compose.yml` (vollständig ersetzen):
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
      options: {max-size: "10m", max-file: "3"}

  dashboard:
    build: .
    command: uvicorn src.monitoring.dashboard:app --host 0.0.0.0 --port 8080
    restart: unless-stopped
    env_file: config/.env
    environment:
      - DASHBOARD_DB_PATH=/app/data/portfolio.db
    volumes:
      - ./config:/app/config:ro
      - bot-data:/app/data:ro
    depends_on: [trading-bot]

  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports: ["80:80", "443:443"]
    volumes:
      - ./config/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy-data:/data
    depends_on: [dashboard]

volumes:
  bot-data:
  caddy-data:
```

`config/Caddyfile` (neu erstellen):
```
:80 {
    basicauth {
        admin $2a$14$Zkx19XLiW6VYouLHR5NmfOFU0z2GTNmpkT/5qqR7hx4IjWJPDhjm2
    }
    reverse_proxy dashboard:8080
}
```
Passwort-Hash erneuern vor Deployment: `caddy hash-password --plaintext <passwort>`

Commit: `git add docker-compose.yml config/Caddyfile && git commit -m "feat: finalize docker-compose with dashboard service and Caddy reverse proxy"`

### Task 7: Abschluss-Test + Tag
```bash
python -m pytest -v --tb=short        # mind. 83 passed
git tag v0.3.0-monitoring
```

---

## Architektur-Überblick

```
asyncio Event Bus (pub/sub)
    │
    ├── BybitFeed  ──── CANDLE_CLOSED ──►  Strategien (EMA, Grid, BB)
    │                                           │ SIGNAL_GENERATED
    │                                           ▼
    │                                      RiskManager (validate)
    │                                           │ ok
    │                                           ▼
    │                               OrderManager (Bybit REST)
    │                                           │ ORDER_FILLED
    │                                           ▼
    ├── PortfolioTracker (SQLite)    ◄──────────┘
    │
    ├── TelegramMonitor (optional)  ◄── ORDER_FILLED, RISK_BREACHED
    │
    └── BacktestEngine (to_thread)  ──── asyncio.new_event_loop()
```

**Dashboard** (separater Docker-Service):
- FastAPI + Jinja2 + HTMX
- Liest SQLite read-only via aiosqlite
- Caddy reverse proxy mit basicauth

---

## Wichtige technische Details

### Bekannte Eigenheiten
- `EventBus.publish()`: Sync-Handler werden aufgerufen (Rückgabe ignoriert), async Handler via `asyncio.gather()`
- `BacktestEngine._run_sync()`: Nutzt `asyncio.new_event_loop()` + `run_until_complete()` (nicht `asyncio.run()`!) damit es aus `to_thread()` heraus funktioniert
- `BollingerReversionStrategy.on_candle()`: Bänder werden VOR dem Append des neuen Preises berechnet (Timing-Fix)
- `TelegramMonitor`: Sender-Auth via `_is_authorized()` (chat_id-Check) — jeder Command prüft das
- `dashboard.py`: Starlette 1.0 API: `TemplateResponse(request, "template.html", context)` (nicht die alte Signatur)

### Config-Felder in Settings
- `settings.bybit_testnet` — bool
- `settings.bybit_api_key` / `settings.bybit_api_secret`
- `settings.telegram_token` / `settings.telegram_chat_id` — optional, None = Telegram deaktiviert
- `settings.risk` — RiskConfig (daily_loss_limit_pct, max_drawdown_pct, max_open_positions, max_position_size_pct, leverage)
- `settings.backtesting` — BacktestConfig (fee_rate, slippage_pct, initial_capital)
- `settings.strategies` — list[StrategyEntry]

### Deployment-Checkliste (nach Plan 3 abgeschlossen)
1. Hetzner CX22 VPS erstellen, Docker + Docker Compose installieren
2. `git clone <repo>`, `cp config/.env.example config/.env`
3. API-Keys eintragen, `bybit_testnet: true` lassen
4. `docker compose up -d`
5. Caddy-Passwort setzen: `caddy hash-password --plaintext <passwort>` → Hash in `config/Caddyfile`
6. Telegram-Bot testen: `/status`, `/pause`, `/resume`
7. Dashboard öffnen: `http://<vps-ip>`
8. Nach erfolgreichen Tests: `bybit_testnet: false`, Startkapital einzahlen

---

## Einschränkungen
- API Keys OHNE Withdrawal-Berechtigung konfigurieren
- Max. Risiko pro Trade: konfigurierbar via `max_position_size_pct`
- Max. Tagesverlust: konfigurierbar via `daily_loss_limit_pct` (default 5%)
- Max. Drawdown: konfigurierbar via `max_drawdown_pct` (default 20%)

---

## Plan-Dateien
| Plan | Pfad |
|---|---|
| Plan 1 (Foundation) | `docs/superpowers/plans/2026-05-12-trading-bot-plan-1-foundation.md` |
| Plan 2 (Trading Core) | `docs/superpowers/plans/2026-05-12-trading-bot-plan-2-trading-core.md` |
| Plan 3 (Monitoring) | `docs/superpowers/plans/2026-05-12-trading-bot-plan-3-monitoring.md` |
| Design-Spec | `docs/superpowers/specs/2026-05-12-trading-bot-design.md` |
