# Trading Bot — Plan 4 Design Spec: Production Readiness

**Datum:** 2026-05-13  
**Status:** Genehmigt  
**Ziel:** Den Bot produktionsreif machen: CI/CD, vierte Strategie (RSI), Dashboard-Erweiterungen und Deployment-Vorbereitung.

---

## 1. Überblick

Plan 4 baut auf dem abgeschlossenen Plan 3 (v0.3.0-monitoring, 83 Tests) auf und ergänzt vier unabhängige Bereiche:

| Bereich | Dateien | Neue Tests |
|---|---|---|
| A — CI/CD + Deployment-Readiness | `data/.gitkeep`, `.github/workflows/ci.yml`, `Makefile`, `CLAUDE.md` | 0 |
| B — RSI-Strategie | `src/strategies/rsi.py`, Tests | ~5 |
| C — Dashboard-Erweiterungen | `src/monitoring/dashboard.py`, Templates, Tests | ~6 |
| D — Deployment-Vorbereitung | `scripts/setup-vps.sh`, `config/config.yaml` | 0 |

**Erwarteter Test-Stand nach Plan 4:** ~98 passed

---

## 2. Bereich A — CI/CD + Deployment-Readiness

### 2.1 `data/.gitkeep`

Das `data/`-Verzeichnis wird von `PortfolioTracker` zur Laufzeit beschrieben (`data/portfolio.db`). Git trackt leere Verzeichnisse nicht — ohne `.gitkeep` fehlt das Verzeichnis nach `git clone` und der Bot schlägt beim ersten Start fehl.

**Lösung:** `data/.gitkeep` anlegen, `.gitignore` um `data/*.db` ergänzen (Verzeichnis tracken, DB-Datei ausschließen).

### 2.2 GitHub Actions CI

Datei: `.github/workflows/ci.yml`

```yaml
name: CI
on:
  push:
    branches: ["master", "main"]
  pull_request:
    branches: ["master", "main"]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: python -m pytest -v --tb=short
```

### 2.3 Makefile

Targets: `make test`, `make run`, `make docker-build`, `make lint`

```makefile
.PHONY: test run docker-build lint

test:
	python -m pytest -v --tb=short

run:
	python -m src.main

docker-build:
	docker compose build

lint:
	python -m ruff check src/ tests/ || true
```

`ruff` als optionale Dev-Dependency hinzufügen (`pyproject.toml` → `[project.optional-dependencies] dev`).

### 2.4 CLAUDE.md Update

Plan 3 als `✅ Abgeschlossen` markieren (Tag `v0.3.0-monitoring`), Plan 4 in die Tabelle eintragen, offene Tasks-Sektion entfernen.

---

## 3. Bereich B — RSI-Strategie

### 3.1 Architektur

Neue Strategie `RsiStrategy` erbt von `BaseStrategy`. RSI wird manuell berechnet (kein pandas-Overhead im Hot Path):

```
RSI = 100 - 100 / (1 + RS)
RS  = Avg(Gewinne über N Perioden) / Avg(Verluste über N Perioden)
```

**Parameter (via `StrategyEntry.params`):**
- `period` (int, default 14) — RSI-Berechnungsfenster
- `oversold` (float, default 30.0) — Kaufsignal unterhalb
- `overbought` (float, default 70.0) — Close-Signal oberhalb

**Signallogik:**
- RSI fällt unter `oversold` → `Signal(side="long", ...)`
- RSI steigt über `overbought` und Position offen → `Signal(side="close", ...)`
- Kein Signal wenn nicht genug Datenpunkte (< `period + 1`)

### 3.2 Datei: `src/strategies/rsi.py`

Strukturell identisch zu `ema_cross.py`: keine externen Deps, nur `collections.deque` für den rollenden Puffer.

### 3.3 Integration

- `STRATEGY_REGISTRY["rsi"] = RsiStrategy` in `src/strategies/registry.py`
- Beispieleintrag in `config/config.yaml` (disabled by default)

### 3.4 Tests

5 neue Tests in `tests/unit/test_strategies.py`:
1. RSI mit konstanten Preisen → kein Signal
2. Fallende Preise → RSI < 30 → Long-Signal
3. Steigende Preise nach Long → RSI > 70 → Close-Signal
4. Zu wenig Datenpunkte → kein Signal
5. `get_state()` gibt RSI-Wert zurück

---

## 4. Bereich C — Dashboard-Erweiterungen

### 4.1 Neuer API-Endpoint: `/api/equity`

Gibt die Equity-Kurve aus der `trades`-Tabelle zurück (kumulierter PnL über Zeit):

```python
@app.get("/api/equity")
async def equity() -> list[dict]:
    # Gibt [{timestamp, equity}, ...] zurück
    # Berechnet kumulativen PnL aus trades-Tabelle
```

Equity wird als `initial_capital + kumulativer_pnl` berechnet. Da die `trades`-Tabelle keinen PnL-Wert pro Trade speichert, wird jeder Trade-Eintrag als abgeschlossene Position behandelt: `pnl_i = (side == "Buy" ? +1 : -1) * qty * avg_price * 0.001 - fee`. Das ist eine Annäherung, reicht aber für die Visualisierung des Equity-Verlaufs.

### 4.2 Equity-Chart (Chart.js)

In `src/monitoring/templates/index.html` — Chart.js via CDN, kein Build-Step:

```html
<canvas id="equity-chart"></canvas>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4/dist/chart.umd.min.js"></script>
<script>
  // Fetch /api/equity, render Line-Chart
</script>
```

HTMX-Polling alle 60s aktualisiert die Daten.

### 4.3 Strategy-Übersicht: `/api/strategies`

Gibt aktive Strategien + Trade-Count aus `trades`-Tabelle zurück:

```python
@app.get("/api/strategies")
async def strategies() -> list[dict]:
    # GROUP BY strategy_id: {name, trade_count, total_pnl}
```

Wird als neue Karte in `index.html` dargestellt.

### 4.4 SSE `/stream` verbessern

Aktuell gibt `/stream` nur einen Platzhalter zurück. Verbesserung: gibt die letzten 5 Trades als initiale Events zurück, dann keepalive alle 30s. Kein echtes Log-Streaming (zu komplex für Plan 4 ohne Redis/Queue).

### 4.5 Neue Tests (6)

In `tests/unit/test_dashboard.py`:
1. `/api/equity` gibt Liste zurück
2. `/api/equity` mit leerem DB → leere Liste
3. `/api/strategies` gibt Liste zurück
4. `/api/strategies` gruppiert korrekt nach `strategy_id`
5. `/api/equity` mit mehreren Trades → korrekte Kumulation
6. `/stream` gibt SSE-Response zurück

---

## 5. Bereich D — Deployment-Vorbereitung

### 5.1 `scripts/setup-vps.sh`

Bash-Skript für Hetzner Ubuntu 22.04. Automatisiert:
1. System-Update (`apt-get update && upgrade`)
2. Docker + Docker Compose installieren (offizieller Install-Pfad)
3. Nicht-Root-User `botuser` anlegen
4. Repo clonen nach `/opt/trading-bot`
5. `config/.env` aus `.env.example` kopieren mit Hinweis auf API-Key-Eintragung
6. `docker compose build`

**Nicht automatisiert** (erfordert manuelle Eingabe):
- API-Keys in `.env`
- Caddy-Passwort-Hash
- `docker compose up -d` (bewusste Entscheidung — nicht blind starten)

### 5.2 `config/config.yaml` Kommentare

Beschreibende Kommentare zu jedem Block hinzufügen damit das File für neue User selbsterklärend ist.

---

## 6. Datenfluss-Erweiterungen

```
Portfolio Tracker (SQLite)
    │
    ├── /api/portfolio   → open_positions, realized_pnl
    ├── /api/trades      → Liste aller Trades (paginiert)
    ├── /api/equity  [NEU] → [{timestamp, equity}]
    └── /api/strategies [NEU] → [{name, trade_count}]
```

Die `RsiStrategy` hängt sich wie alle anderen in den Event Bus:
```
CANDLE_CLOSED → RsiStrategy.on_candle() → SIGNAL_GENERATED (oder None)
```

---

## 7. Testing-Strategie

- TDD für `RsiStrategy`: Tests zuerst, dann Implementierung
- Dashboard-Tests nutzen bestehende `httpx.AsyncClient`-Fixture — DB-Fixture wird um Equity-Daten erweitert
- CI läuft alle Tests auf Python 3.12 (GitHub Actions)
- Kein Mock für CI — dieselbe `python-m pytest`-Zeile wie lokal

---

## 8. Abgrenzung (nicht in Plan 4)

- Keine Integration-Tests gegen Bybit Testnet (erfordert echte API-Keys)
- Kein HTTPS auf VPS (Caddy macht das automatisch, keine Code-Änderung nötig)
- Kein Live-Deployment (Benutzer führt `docker compose up -d` manuell aus)
- Kein MACD (RSI reicht als vierte Strategie)
- Kein Prometheus/Grafana-Monitoring (zu weit vom Scope)
