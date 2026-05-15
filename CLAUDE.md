# Trading Bot – Project Memory

## Autonome Ausführung

Um das Projekt vollständig und autonom durchzuarbeiten:

```
claude --dangerously-skip-permissions -p "Arbeite das Trading-Agent Projekt vollständig durch. Lies die CLAUDE.md, führe alle Schritte aus, erstelle alle Dateien. Frage nur bei echten Designentscheidungen oder externen API-Zugängen nach."
```

---

## Projektziel
Vollautomatischer 24/7 Krypto-Futures-Trading-Bot für Bybit.
Startkapital: ~250 €. Plattform: Bybit Perpetuals. Sprache: Python 3.12.

---

## Aktueller Stand (2026-05-15)

### Implementierte Pläne
| Plan | Tag | Tests | Status |
|---|---|---|---|
| Plan 1 – Foundation (Core, Data, Config) | `v0.1.0-foundation` | 16 | ✅ Abgeschlossen |
| Plan 2 – Trading Core (Strategies, Risk, Orders, Portfolio) | `v0.2.0-trading-core` | 65 | ✅ Abgeschlossen |
| Plan 3 – Monitoring & Deployment (Backtesting, Telegram, Dashboard, Docker) | `v0.3.0-monitoring` | 83 | ✅ Abgeschlossen |
| Plan 4 – Production Readiness (CI/CD, RSI, Dashboard, Deployment) | `v0.4.0-production-ready` | 94 | ✅ Abgeschlossen |
| Plan 5 – Dashboard Live-Steuerung (Verbindungsstatus, Strategie-Toggle) | – | 106 | ✅ Abgeschlossen |

**Aktueller Test-Stand:** `106 Tests (106 passed, 0 failed)` — alle Pläne abgeschlossen

**GitHub Repo:** https://github.com/shishe123ki-ship-it/trading-bot (privat)

---

## Fertige Dateien

### Core (Plan 1)
| Datei | Beschreibung |
|---|---|
| `src/core/types.py` | Candle, Signal, OrderFill, Event, EventType, BacktestConfig, RiskConfig |
| `src/core/config.py` | Settings (pydantic-settings v2), StrategyEntry, BacktestConfig, RiskConfig |
| `src/core/event_bus.py` | Asyncio pub/sub EventBus — sync + async Handler, gather-basiert |
| `src/core/logger.py` | structlog Setup |
| `src/data/feed.py` | BybitFeed — pybit WebSocket, CANDLE_CLOSED Events, `connected` Property |

### Trading Core (Plan 2)
| Datei | Beschreibung |
|---|---|
| `src/portfolio/tracker.py` | SQLite-Portfolio (aiosqlite), PnL, Drawdown, Positions, `bot_status`- und `strategy_overrides`-Tabellen (Plan 5 IPC) |
| `src/risk/manager.py` | RiskManager — daily_loss, max_drawdown, max_positions, leverage-Cap |
| `src/execution/order_manager.py` | OrderManager — Bybit REST, Position-Sizing, ORDER_PLACED/FILLED Events |
| `src/strategies/base.py` | BaseStrategy ABC mit `id`, `config`, `on_candle`, `on_fill`, `get_state` |
| `src/strategies/ema_cross.py` | EMA-Crossover (Golden/Death Cross) |
| `src/strategies/grid.py` | Grid-Trading (Preis-Level-Durchbruch) |
| `src/strategies/bb_reversion.py` | Bollinger-Band Mean-Reversion |
| `src/strategies/registry.py` | STRATEGY_REGISTRY + load_strategies() |
| `src/main.py` | Haupt-Orchestrierung: alle Komponenten verdrahtet + TelegramMonitor optional, Windows-Signal-Handler (SIGINT/SIGTERM) |

### Monitoring & Deployment (Plan 3 — ✅ Fertig)
| Datei | Beschreibung | Status |
|---|---|---|
| `src/backtesting/__init__.py` | Paket-Stub | ✅ |
| `src/backtesting/engine.py` | BacktestEngine: OHLCV-Fetch (Bybit REST), Strategie-Simulation, Metriken | ✅ |
| `src/monitoring/__init__.py` | Paket-Stub | ✅ |
| `src/monitoring/telegram_bot.py` | TelegramMonitor: Push-Alerts + /pause /resume /status /set /backtest | ✅ |
| `src/monitoring/dashboard.py` | FastAPI Dashboard: /api/portfolio, /api/trades, /api/equity, /api/strategies, HTMX-Partials, SSE | ✅ |
| `src/monitoring/templates/index.html` | Hauptseite (Dark-Theme, HTMX-Polling) | ✅ |
| `src/monitoring/templates/partials/portfolio.html` | Portfolio-Metriken-Fragment | ✅ |
| `src/monitoring/templates/partials/trades.html` | Trades-Tabelle-Fragment | ✅ |
| `docker-compose.yml` | Docker-Compose mit trading-bot, dashboard, caddy Services | ✅ |
| `config/Caddyfile` | Caddy reverse proxy mit basicauth | ✅ |

### CI/CD + Tooling (Plan 4)
| Datei | Beschreibung |
|---|---|
| `data/.gitkeep` | Git-Platzhalter für data/-Verzeichnis |
| `.github/workflows/ci.yml` | GitHub Actions CI (Python 3.12, pytest) |
| `Makefile` | make test, make run, make docker-build, make lint |
| `scripts/setup-vps.sh` | Automatisiertes VPS-Setup (Ubuntu 22.04) |

### Strategien (Plan 4)
| Datei | Beschreibung |
|---|---|
| `src/strategies/rsi.py` | RSI-Strategie (Überverkauf/Überkauf-Signale, deque-basiert) |

### Dashboard-Erweiterungen (Plan 4)
| Datei | Beschreibung |
|---|---|
| `src/monitoring/templates/partials/strategies.html` | Strategie-Übersicht-Fragment |

### Dashboard Live-Steuerung (Plan 5 — ✅ Abgeschlossen)
| Datei | Beschreibung | Status |
|---|---|---|
| `src/portfolio/tracker.py` | `bot_status`- + `strategy_overrides`-Tabellen im Schema | ✅ |
| `src/data/feed.py` | `connected` Property für WebSocket-Status | ✅ |
| `src/main.py` | `_init_strategy_overrides`, `_heartbeat_loop`, `_strategy_watcher_loop` auf Modul-Level, Background-Tasks, `_dispatch_candle` prüft enabled | ✅ |
| `src/monitoring/dashboard.py` | 3 neue Endpoints: /api/status, /api/strategies/{id}/toggle, /api/strategies (erweitert mit enabled) | ✅ |
| `src/monitoring/templates/partials/status.html` | Verbindungsanzeige grün/rot mit last_seen Timestamp | ✅ |
| `src/monitoring/templates/partials/strategy_row.html` | Strategie-Zeile mit HTMX Toggle-Button | ✅ |
| `tests/unit/test_feed.py` | Tests für BybitFeed inkl. `connected` Property | ✅ |
| `tests/unit/test_main_helpers.py` | 4 Tests für Hilfsfunktionen (Heartbeat, Override, dispatch) | ✅ |

### Tests
| Datei | Anzahl | Was getestet wird |
|---|---|---|
| `tests/unit/test_event_bus.py` | – | EventBus pub/sub |
| `tests/unit/test_portfolio_tracker.py` | 10 | SQLite-Persistenz, PnL, Drawdown, bot_status-Tabelle, strategy_overrides-Tabelle |
| `tests/unit/test_risk_manager.py` | 9 | daily_loss, drawdown, positions, pause/resume |
| `tests/unit/test_order_manager.py` | 4 | Qty-Berechnung, Signal-Verarbeitung |
| `tests/unit/test_strategies.py` | 23 | EMA, Grid, Bollinger-Band, RSI (TDD) |
| `tests/unit/test_backtesting.py` | 4 | BacktestResult, OHLCV-Parsing, run(), Flatline |
| `tests/unit/test_telegram_bot.py` | 8 | Push-Alerts, Commands (mit Auth-Guard) |
| `tests/unit/test_dashboard.py` | 17 | FastAPI-Endpoints inkl. /api/status, /api/strategies/{id}/toggle (httpx AsyncClient) |
| `tests/unit/test_feed.py` | 5 | BybitFeed WebSocket-Callback, connected Property |
| `tests/unit/test_main_helpers.py` | 4 | _init_strategy_overrides, _heartbeat_loop, _strategy_watcher_loop |

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
- `main.py` Windows-Kompatibilität: `loop.add_signal_handler()` existiert unter Windows nicht — stattdessen `signal.signal(SIGINT/SIGTERM, _win_stop)` mit `loop.call_soon_threadsafe(stop_event.set)` verwenden
- Plan 5 IPC: SQLite als Brücke zwischen Bot und Dashboard — Bot schreibt Heartbeat alle 10s in `bot_status`, liest `strategy_overrides` alle 30s; Dashboard schreibt Toggles und zeigt Status via HTMX

### Config-Felder in Settings
- `settings.bybit_testnet` — bool
- `settings.bybit_api_key` / `settings.bybit_api_secret`
- `settings.telegram_token` / `settings.telegram_chat_id` — optional, None = Telegram deaktiviert
- `settings.risk` — RiskConfig (daily_loss_limit_pct, max_drawdown_pct, max_open_positions, max_position_size_pct, leverage)
- `settings.backtesting` — BacktestConfig (fee_rate, slippage_pct, initial_capital)
- `settings.strategies` — list[StrategyEntry]

### Deployment-Checkliste (🔄 In Bearbeitung)

**Externe Ressourcen:**
- [x] Hetzner CX22 VPS — IP: `128.140.110.145`
- [x] Bybit Testnet API-Keys — vorhanden
- [x] GitHub Repo — https://github.com/shishe123ki-ship-it/trading-bot (privat)
- [ ] Telegram — wird NICHT verwendet

**Deployment-Schritte:**
1. SSH auf VPS: `ssh root@128.140.110.145`
2. Setup-Skript ausführen: `curl -fsSL https://raw.githubusercontent.com/shishe123ki-ship-it/trading-bot/master/scripts/setup-vps.sh | bash -s https://github.com/shishe123ki-ship-it/trading-bot.git`
3. API-Keys in `config/.env` eintragen (TELEGRAM_TOKEN und TELEGRAM_CHAT_ID leer lassen)
4. Caddy-Passwort setzen: `docker run --rm caddy:2-alpine caddy hash-password --plaintext <passwort>` → Hash in `config/Caddyfile`
5. `docker compose up -d`
6. Dashboard öffnen: `http://128.140.110.145`
7. Nach erfolgreichen Tests: `bybit_testnet: false` in `config/config.yaml`, Startkapital einzahlen

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
| Plan 4 (Production Readiness) | `docs/superpowers/plans/2026-05-13-trading-bot-plan-4-production-readiness.md` |
| Design-Spec | `docs/superpowers/specs/2026-05-12-trading-bot-design.md` |
| Plan 4 Design-Spec | `docs/superpowers/specs/2026-05-13-plan4-production-readiness-design.md` |
| Plan 5 (Dashboard Live-Steuerung) | `docs/superpowers/plans/2026-05-14-dashboard-live-control.md` |
