# Trading Bot — Plan 4: Production Readiness

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Den Trading-Bot produktionsreif machen: CI/CD, RSI-Strategie, Dashboard-Erweiterungen und Deployment-Vorbereitung.

**Architecture:** RSI-Strategie erbt von BaseStrategy mit `deque`-basiertem Rollenpuffer (kein pandas). Dashboard-Erweiterungen nutzen bestehende aiosqlite-Verbindung. GitHub Actions CI führt `pytest` auf Python 3.12 aus.

**Tech Stack:** Python 3.12, pytest, GitHub Actions, Chart.js 4.4 (CDN), bash

**Voraussetzung:** Plan 3 abgeschlossen (v0.3.0-monitoring), 83 Tests grün.

---

## Task 1: Bereich A — CI/CD + Deployment-Readiness

**Dateien:**
- Erstelle: `data/.gitkeep`
- Modifiziere: `.gitignore`
- Erstelle: `.github/workflows/ci.yml`
- Erstelle: `Makefile`
- Modifiziere: `pyproject.toml`

### Schritte

- [ ] **1.1** `data/.gitkeep` erstellen (leere Datei):

  ```
  (leere Datei — kein Inhalt)
  ```

- [ ] **1.2** `.gitignore` modifizieren — nach dem Block `# Secrets` die Zeile `data/*.db` hinzufügen:

  Bestehende Datei (Anfang):
  ```
  # Secrets
  config/.env
  .env
  ```

  Nach Änderung:
  ```
  # Secrets
  config/.env
  .env

  # Data
  data/*.db
  ```

- [ ] **1.3** `.github/workflows/ci.yml` erstellen (Verzeichnis `.github/workflows/` anlegen falls nicht vorhanden):

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

- [ ] **1.4** `Makefile` erstellen (WICHTIG: Einrückung mit Tabs, nicht Spaces — Make verlangt das!):

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

- [ ] **1.5** `pyproject.toml` modifizieren — `ruff>=0.4` zu `[project.optional-dependencies] dev` hinzufügen:

  Alt:
  ```toml
  [project.optional-dependencies]
  dev = [
      "pytest>=8.0",
      "pytest-asyncio>=0.23",
      "pytest-mock>=3.12",
      "httpx>=0.27",
  ]
  ```

  Neu:
  ```toml
  [project.optional-dependencies]
  dev = [
      "pytest>=8.0",
      "pytest-asyncio>=0.23",
      "pytest-mock>=3.12",
      "httpx>=0.27",
      "ruff>=0.4",
  ]
  ```

- [ ] **1.6** Commit:

  ```bash
  git add data/.gitkeep .gitignore .github/workflows/ci.yml Makefile pyproject.toml
  git commit -m "feat: add CI workflow, Makefile and dev tooling"
  ```

**Verifizierung:**
```bash
python -m pytest -v --tb=short   # 83 passed (keine neuen Tests)
```

---

## Task 2: Bereich B — RSI-Strategie (TDD)

**Dateien:**
- Modifiziere: `tests/unit/test_strategies.py` (5 neue Tests anhängen — zuerst!)
- Erstelle: `src/strategies/rsi.py`
- Modifiziere: `src/strategies/registry.py`
- Modifiziere: `config/config.yaml`

### Schritt 1: Failing Tests schreiben

- [ ] **2.1** An `tests/unit/test_strategies.py` anhängen (nach dem letzten bestehenden Test `test_bb_generates_close_signal_when_price_returns_to_sma`):

  ```python
  # --- RSI Strategy ---
  from src.strategies.rsi import RsiStrategy


  def _make_candle_rsi(symbol: str, close: float) -> Candle:
      from datetime import datetime, timezone
      return Candle(
          symbol=symbol, interval="15",
          open_time=datetime.now(tz=timezone.utc),
          open=close, high=close * 1.001, low=close * 0.999,
          close=close, volume=1.0, is_closed=True,
      )


  async def test_rsi_insufficient_data_no_signal():
      cfg = StrategyEntry(name="rsi", params={"period": 14, "oversold": 30.0, "overbought": 70.0})
      strategy = RsiStrategy(config=cfg)
      result = await strategy.on_candle(_make_candle_rsi("BTCUSDT", 50000.0))
      assert result is None


  async def test_rsi_falling_prices_generates_long():
      cfg = StrategyEntry(name="rsi", params={"period": 3, "oversold": 30.0, "overbought": 70.0})
      strategy = RsiStrategy(config=cfg)
      sig = None
      for price in [50000, 49000, 48000, 47000]:
          sig = await strategy.on_candle(_make_candle_rsi("BTCUSDT", float(price)))
      assert sig is not None
      assert sig.side == "long"
      assert sig.strategy_id == "rsi"


  async def test_rsi_rising_prices_closes_position():
      cfg = StrategyEntry(name="rsi", params={"period": 3, "oversold": 30.0, "overbought": 70.0})
      strategy = RsiStrategy(config=cfg)
      strategy._in_position = True
      sig = None
      for price in [47000, 48000, 49000, 50000]:
          sig = await strategy.on_candle(_make_candle_rsi("BTCUSDT", float(price)))
      assert sig is not None
      assert sig.side == "close"


  async def test_rsi_constant_prices_no_signal():
      cfg = StrategyEntry(name="rsi", params={"period": 3, "oversold": 30.0, "overbought": 70.0})
      strategy = RsiStrategy(config=cfg)
      sig = None
      for _ in range(5):
          sig = await strategy.on_candle(_make_candle_rsi("BTCUSDT", 50000.0))
      assert sig is None


  async def test_rsi_get_state_returns_rsi_value():
      cfg = StrategyEntry(name="rsi", params={"period": 3})
      strategy = RsiStrategy(config=cfg)
      state = strategy.get_state()
      assert "rsi" in state
      assert "in_position" in state
      assert state["period"] == 3
  ```

- [ ] **2.2** Bestätigen dass die Tests fehlschlagen (ImportError erwartet):

  ```bash
  python -m pytest tests/unit/test_strategies.py -v --tb=short 2>&1 | tail -20
  ```

### Schritt 2: Implementierung

- [ ] **2.3** `src/strategies/rsi.py` erstellen:

  ```python
  from __future__ import annotations

  from collections import deque

  import structlog

  from src.core.config import StrategyEntry
  from src.core.types import Candle, Signal
  from src.strategies.base import BaseStrategy

  log = structlog.get_logger(__name__)


  class RsiStrategy(BaseStrategy):
      def __init__(self, config: StrategyEntry) -> None:
          super().__init__(config)
          self._period = int(config.params.get("period", 14))
          self._oversold = float(config.params.get("oversold", 30.0))
          self._overbought = float(config.params.get("overbought", 70.0))
          self._prices: deque[float] = deque(maxlen=self._period + 1)
          self._rsi: float = 50.0
          self._in_position = False

      async def on_candle(self, candle: Candle) -> Signal | None:
          self._prices.append(candle.close)
          if len(self._prices) < self._period + 1:
              return None

          prices = list(self._prices)
          changes = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
          gains = [c for c in changes if c > 0]
          losses = [-c for c in changes if c < 0]

          avg_gain = sum(gains) / len(changes) if gains else 0.0
          avg_loss = sum(losses) / len(changes) if losses else 0.0

          if avg_gain == 0 and avg_loss == 0:
              self._rsi = 50.0
          elif avg_loss == 0:
              self._rsi = 100.0
          else:
              rs = avg_gain / avg_loss
              self._rsi = 100.0 - 100.0 / (1.0 + rs)

          size_pct = float(self._config.params.get("size_pct", 1.0))

          if self._rsi < self._oversold and not self._in_position:
              self._in_position = True
              return Signal(
                  symbol=candle.symbol,
                  side="long",
                  size_pct=size_pct,
                  entry_price=None,
                  stop_loss=None,
                  take_profit=None,
                  strategy_id=self.id,
              )

          if self._rsi > self._overbought and self._in_position:
              self._in_position = False
              return Signal(
                  symbol=candle.symbol,
                  side="close",
                  size_pct=0.0,
                  entry_price=None,
                  stop_loss=None,
                  take_profit=None,
                  strategy_id=self.id,
              )

          return None

      async def on_fill(self, fill) -> None:
          pass

      def get_state(self) -> dict:
          return {
              "rsi": round(self._rsi, 2),
              "in_position": self._in_position,
              "period": self._period,
          }
  ```

### Schritt 3: Registry aktualisieren

- [ ] **2.4** `src/strategies/registry.py` modifizieren — `RsiStrategy` importieren und in `STRATEGY_REGISTRY` eintragen:

  Alt:
  ```python
  from __future__ import annotations

  from src.core.config import StrategyEntry
  from src.strategies.base import BaseStrategy
  from src.strategies.bb_reversion import BollingerReversionStrategy
  from src.strategies.ema_cross import EmaCrossStrategy
  from src.strategies.grid import GridStrategy

  STRATEGY_REGISTRY: dict[str, type[BaseStrategy]] = {
      "ema_cross": EmaCrossStrategy,
      "grid": GridStrategy,
      "bb_reversion": BollingerReversionStrategy,
  }
  ```

  Neu:
  ```python
  from __future__ import annotations

  from src.core.config import StrategyEntry
  from src.strategies.base import BaseStrategy
  from src.strategies.bb_reversion import BollingerReversionStrategy
  from src.strategies.ema_cross import EmaCrossStrategy
  from src.strategies.grid import GridStrategy
  from src.strategies.rsi import RsiStrategy

  STRATEGY_REGISTRY: dict[str, type[BaseStrategy]] = {
      "ema_cross": EmaCrossStrategy,
      "grid": GridStrategy,
      "bb_reversion": BollingerReversionStrategy,
      "rsi": RsiStrategy,
  }
  ```

### Schritt 4: config.yaml RSI-Beispieleintrag

- [ ] **2.5** `config/config.yaml` — RSI-Beispieleintrag am Ende der `strategies`-Liste anhängen:

  ```yaml
    - name: rsi
      enabled: false
      symbols: ["BTCUSDT"]
      interval: "15"
      params:
        period: 14
        oversold: 30.0
        overbought: 70.0
  ```

- [ ] **2.6** Commit:

  ```bash
  git add src/strategies/rsi.py src/strategies/registry.py tests/unit/test_strategies.py config/config.yaml
  git commit -m "feat: add RSI strategy with TDD (5 new tests)"
  ```

**Verifizierung:**
```bash
python -m pytest tests/unit/test_strategies.py -v   # 5 neue Tests grün
python -m pytest -v --tb=short                       # ~88 passed gesamt
```

---

## Task 3: Bereich C — Dashboard-Erweiterungen (TDD)

**Dateien:**
- Modifiziere: `tests/unit/test_dashboard.py` (6 neue Tests anhängen — zuerst!)
- Modifiziere: `src/monitoring/dashboard.py`
- Erstelle: `src/monitoring/templates/partials/strategies.html`
- Modifiziere: `src/monitoring/templates/index.html`

### Schritt 1: Failing Tests schreiben

- [ ] **3.1** An `tests/unit/test_dashboard.py` anhängen (nach dem letzten bestehenden Test `test_trades_partial_returns_html`):

  ```python
  @pytest.fixture
  def temp_db_multi(tmp_path) -> Path:
      """DB mit 2 Trades fuer Equity-Kumulations-Test."""
      db_path = tmp_path / "test_multi.db"
      conn = sqlite3.connect(db_path)
      conn.execute("""
          CREATE TABLE trades (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              order_id TEXT, symbol TEXT, side TEXT,
              qty REAL, avg_price REAL, fee REAL,
              strategy_id TEXT, timestamp TEXT
          )
      """)
      conn.execute("""
          CREATE TABLE positions (
              symbol TEXT PRIMARY KEY, side TEXT, qty REAL,
              entry_price REAL, strategy_id TEXT, opened_at TEXT
          )
      """)
      conn.execute("INSERT INTO trades VALUES (1,'O1','BTCUSDT','Buy',0.001,50000,0.027,'ema_cross','2024-01-01T10:00:00')")
      conn.execute("INSERT INTO trades VALUES (2,'O2','ETHUSDT','Buy',0.01,3000,0.054,'rsi','2024-01-01T11:00:00')")
      conn.commit()
      conn.close()
      return db_path


  @pytest.fixture
  async def client_multi(temp_db_multi):
      original = dashboard_module.DB_PATH
      dashboard_module.DB_PATH = temp_db_multi
      from src.monitoring.dashboard import app
      async with httpx.AsyncClient(
          transport=httpx.ASGITransport(app=app),
          base_url="http://test",
      ) as c:
          yield c
      dashboard_module.DB_PATH = original


  async def test_equity_api_returns_list(client):
      resp = await client.get("/api/equity")
      assert resp.status_code == 200
      data = resp.json()
      assert isinstance(data, list)
      assert len(data) == 1
      assert "timestamp" in data[0]
      assert "equity" in data[0]


  async def test_equity_api_empty_db(tmp_path):
      original = dashboard_module.DB_PATH
      dashboard_module.DB_PATH = tmp_path / "nonexistent.db"
      from src.monitoring.dashboard import app
      async with httpx.AsyncClient(
          transport=httpx.ASGITransport(app=app),
          base_url="http://test",
      ) as c:
          resp = await c.get("/api/equity")
      dashboard_module.DB_PATH = original
      assert resp.status_code == 200
      assert resp.json() == []


  async def test_equity_cumulative_sum(client_multi):
      resp = await client_multi.get("/api/equity")
      assert resp.status_code == 200
      data = resp.json()
      assert len(data) == 2
      assert data[0]["equity"] == pytest.approx(250.0 - 0.027, abs=0.001)
      assert data[1]["equity"] == pytest.approx(250.0 - 0.027 - 0.054, abs=0.001)


  async def test_strategies_api_returns_list(client):
      resp = await client.get("/api/strategies")
      assert resp.status_code == 200
      data = resp.json()
      assert isinstance(data, list)
      assert len(data) == 1
      assert data[0]["strategy_id"] == "ema_cross"
      assert data[0]["trade_count"] == 1


  async def test_strategies_api_groups_by_strategy(client_multi):
      resp = await client_multi.get("/api/strategies")
      assert resp.status_code == 200
      data = resp.json()
      assert len(data) == 2
      ids = {d["strategy_id"] for d in data}
      assert ids == {"ema_cross", "rsi"}


  async def test_strategies_partial_returns_html(client):
      resp = await client.get("/partials/strategies")
      assert resp.status_code == 200
      assert "text/html" in resp.headers["content-type"]
  ```

- [ ] **3.2** Bestätigen dass die Tests fehlschlagen (404/AttributeError erwartet):

  ```bash
  python -m pytest tests/unit/test_dashboard.py -v --tb=short 2>&1 | tail -20
  ```

### Schritt 2: dashboard.py erweitern

- [ ] **3.3** `src/monitoring/dashboard.py` modifizieren — nach dem bestehenden `import os` Block die Konstante und nach dem `/partials/trades`-Endpoint die 3 neuen Endpoints einfügen:

  **Konstante** nach `DB_PATH = ...` hinzufügen:
  ```python
  INITIAL_CAPITAL = float(os.environ.get("DASHBOARD_INITIAL_CAPITAL", "250.0"))
  ```

  **3 neue Endpoints** nach dem `/partials/trades`-Endpoint (Zeile 61, nach der schließenden Klammer) einfügen:

  ```python
  @app.get("/api/equity")
  async def equity() -> list[dict]:
      if not DB_PATH.exists():
          return []
      async with aiosqlite.connect(DB_PATH) as db:
          db.row_factory = aiosqlite.Row
          cursor = await db.execute(
              "SELECT timestamp, fee FROM trades ORDER BY timestamp ASC"
          )
          rows = await cursor.fetchall()
      result = []
      running_equity = INITIAL_CAPITAL
      for row in rows:
          running_equity -= row["fee"]
          result.append({"timestamp": row["timestamp"], "equity": round(running_equity, 4)})
      return result


  @app.get("/api/strategies")
  async def strategies_summary() -> list[dict]:
      if not DB_PATH.exists():
          return []
      async with aiosqlite.connect(DB_PATH) as db:
          db.row_factory = aiosqlite.Row
          cursor = await db.execute(
              "SELECT strategy_id, COUNT(*) as trade_count FROM trades GROUP BY strategy_id"
          )
          rows = await cursor.fetchall()
          return [dict(row) for row in rows]


  @app.get("/partials/strategies", response_class=HTMLResponse)
  async def strategies_partial(request: Request) -> HTMLResponse:
      data = await strategies_summary()
      return templates.TemplateResponse(
          request, "partials/strategies.html", {"strategies": data}
      )
  ```

### Schritt 3: Template erstellen

- [ ] **3.4** `src/monitoring/templates/partials/strategies.html` erstellen:

  ```html
  {% if strategies %}
  <table>
    <thead>
      <tr><th>Strategie</th><th>Trades</th></tr>
    </thead>
    <tbody>
      {% for s in strategies %}
      <tr>
        <td>{{ s.strategy_id }}</td>
        <td>{{ s.trade_count }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <p style="color:#8b949e">Keine Strategie-Daten.</p>
  {% endif %}
  ```

### Schritt 4: index.html erweitern

- [ ] **3.5** `src/monitoring/templates/index.html` modifizieren — vor `</body>` einfügen:

  ```html
    <h2>Strategien</h2>
    <div class="card"
         hx-get="/partials/strategies"
         hx-trigger="load, every 30s"
         hx-swap="innerHTML">
      <span style="color:#8b949e">Lade&#8230;</span>
    </div>

    <h2>Equity-Kurve</h2>
    <div class="card">
      <canvas id="equity-chart" style="max-height:300px"></canvas>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4/dist/chart.umd.min.js"></script>
    <script>
      let equityChart = null;
      async function loadEquityChart() {
        const data = await fetch('/api/equity').then(r => r.json());
        if (equityChart) { equityChart.destroy(); equityChart = null; }
        if (!data.length) return;
        equityChart = new Chart(document.getElementById('equity-chart'), {
          type: 'line',
          data: {
            labels: data.map(d => d.timestamp.slice(0, 16)),
            datasets: [{
              label: 'Equity (USDT)',
              data: data.map(d => d.equity),
              borderColor: '#58a6ff',
              backgroundColor: 'rgba(88,166,255,0.1)',
              fill: true,
              tension: 0.3,
              pointRadius: 2,
            }]
          },
          options: {
            responsive: true,
            plugins: { legend: { labels: { color: '#e6edf3' } } },
            scales: {
              y: { ticks: { color: '#e6edf3' }, grid: { color: '#30363d' } },
              x: { ticks: { color: '#8b949e', maxTicksLimit: 8 }, grid: { color: '#30363d' } }
            }
          }
        });
      }
      loadEquityChart();
      setInterval(loadEquityChart, 60000);
    </script>
  ```

  Das vollständige `</body></html>` bleibt am Ende erhalten.

- [ ] **3.6** Commit:

  ```bash
  git add src/monitoring/dashboard.py src/monitoring/templates/partials/strategies.html src/monitoring/templates/index.html tests/unit/test_dashboard.py
  git commit -m "feat: add equity chart and strategies dashboard endpoints (6 new tests)"
  ```

**Verifizierung:**
```bash
python -m pytest tests/unit/test_dashboard.py -v   # 6 neue Tests grün
python -m pytest -v --tb=short                      # ~94 passed gesamt
```

---

## Task 4: Bereich D — Deployment-Vorbereitung

**Dateien:**
- Erstelle: `scripts/setup-vps.sh`
- Modifiziere: `config/config.yaml`

### Schritt 1: setup-vps.sh erstellen

- [ ] **4.1** Verzeichnis `scripts/` anlegen und `scripts/setup-vps.sh` erstellen:

  ```bash
  #!/usr/bin/env bash
  # Trading Bot VPS Setup-Skript fuer Ubuntu 22.04 (Hetzner CX22)
  # Verwendung: bash setup-vps.sh [REPO_URL]
  set -euo pipefail

  REPO_URL="${1:-https://github.com/DEIN_GITHUB_USER/trading-bot}"
  INSTALL_DIR="/opt/trading-bot"

  echo "=== Trading Bot VPS Setup ==="
  echo "Repo: $REPO_URL"
  echo "Ziel: $INSTALL_DIR"
  echo ""

  # 1. System aktualisieren
  apt-get update -q && apt-get upgrade -yq

  # 2. Docker installieren (offizieller Pfad)
  if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
  fi

  # 3. docker compose plugin pruefen
  docker compose version || apt-get install -y docker-compose-plugin

  # 4. Bot-User anlegen
  if ! id botuser &>/dev/null; then
    useradd --create-home --shell /bin/bash botuser
    usermod -aG docker botuser
  fi

  # 5. Repo clonen
  if [ -d "$INSTALL_DIR" ]; then
    echo "Verzeichnis $INSTALL_DIR existiert bereits -- ueberspringe clone"
  else
    git clone "$REPO_URL" "$INSTALL_DIR"
    chown -R botuser:botuser "$INSTALL_DIR"
  fi

  # 6. .env vorbereiten
  if [ ! -f "$INSTALL_DIR/config/.env" ]; then
    cp "$INSTALL_DIR/config/.env.example" "$INSTALL_DIR/config/.env"
    echo ""
    echo "=== AKTION ERFORDERLICH ==="
    echo "Trage deine API-Keys in $INSTALL_DIR/config/.env ein:"
    echo "  BYBIT_API_KEY=..."
    echo "  BYBIT_API_SECRET=..."
    echo "  TELEGRAM_TOKEN=... (optional)"
    echo "  TELEGRAM_CHAT_ID=... (optional)"
  fi

  # 7. Docker-Image bauen
  cd "$INSTALL_DIR"
  docker compose build

  echo ""
  echo "=== Setup abgeschlossen ==="
  echo "Naechste Schritte:"
  echo "  1. API-Keys in config/.env eintragen"
  echo "  2. Caddy-Passwort: caddy hash-password --plaintext <passwort>"
  echo "     -> Hash in config/Caddyfile bei 'admin' eintragen"
  echo "  3. docker compose up -d"
  echo "  4. docker compose logs -f trading-bot"
  ```

### Schritt 2: config.yaml kommentieren

- [ ] **4.2** `config/config.yaml` vollständig ersetzen mit kommentierten Blocks:

  ```yaml
  # Bybit-Verbindung: true = Testnet (paper trading), false = Echtgeld
  bybit_testnet: true

  # Risikomanagement-Einstellungen
  risk:
    # Maximaler Drawdown in % bevor alle neuen Trades gesperrt werden
    max_drawdown_pct: 20.0
    # Maximale Positionsgrösse pro Trade in % des Gesamtkapitals
    max_position_size_pct: 10.0
    # Maximale Anzahl gleichzeitig offener Positionen
    max_open_positions: 3
    # Tagesverlust-Limit in % — bei Überschreitung wird der Bot pausiert
    daily_loss_limit_pct: 5.0
    # Hebel (Leverage) für alle Positionen
    leverage: 3

  # Backtesting-Parameter (verwendet von /backtest Telegram-Command)
  backtesting:
    # Bybit Maker-Fee (0.055%)
    fee_rate: 0.00055
    # Simulierter Slippage in %
    slippage_pct: 0.05
    # Startkapital für Backtests in USDT
    initial_capital: 250.0

  # Strategien — enabled: false = deaktiviert, ändere auf true zum Aktivieren
  strategies:
    # EMA-Crossover: Golden Cross (Long) / Death Cross (Short)
    - name: ema_cross
      enabled: false
      symbols: ["BTCUSDT"]
      interval: "5"
      params:
        fast_ema: 9
        slow_ema: 21

    # Grid-Trading: Kaufen/Verkaufen an vordefinierten Preis-Levels
    - name: grid
      enabled: false
      symbols: ["ETHUSDT"]
      interval: "15"
      params:
        grid_count: 10
        grid_spacing_pct: 0.5

    # Bollinger-Band Mean-Reversion: Long unter Lower Band, Short über Upper Band
    - name: bb_reversion
      enabled: false
      symbols: ["BTCUSDT"]
      interval: "15"
      params:
        period: 20
        std_dev: 2.0

    # RSI-Strategie: Long bei Überverkauf, Close bei Überkauf
    - name: rsi
      enabled: false
      symbols: ["BTCUSDT"]
      interval: "15"
      params:
        period: 14
        oversold: 30.0
        overbought: 70.0
  ```

- [ ] **4.3** Commit:

  ```bash
  git add scripts/setup-vps.sh config/config.yaml
  git commit -m "feat: add VPS setup script and annotate config.yaml"
  ```

**Verifizierung:**
```bash
bash -n scripts/setup-vps.sh   # kein Syntaxfehler (Bash Syntax-Check)
python -m pytest -v --tb=short  # ~94 passed (keine neuen Tests)
```

---

## Task 5: CLAUDE.md aktualisieren + Tag setzen

**Dateien:**
- Modifiziere: `CLAUDE.md`

### Schritt 1: Plan-Tabelle updaten

- [ ] **5.1** In `CLAUDE.md` die Plan-Tabelle aktualisieren:

  Alt:
  ```markdown
  | Plan 3 – Monitoring & Deployment (Backtesting, Telegram, Dashboard, Docker) | (noch kein Tag) | 83 | ⏳ Tasks 1–4 fertig, Tasks 5–7 offen |
  ```

  Neu:
  ```markdown
  | Plan 3 – Monitoring & Deployment (Backtesting, Telegram, Dashboard, Docker) | `v0.3.0-monitoring` | 83 | ✅ Abgeschlossen |
  | Plan 4 – Production Readiness (CI/CD, RSI, Dashboard, Deployment) | `v0.4.0-production-ready` | ~94 | ✅ Abgeschlossen |
  ```

- [ ] **5.2** Aktualisierten Test-Stand in `CLAUDE.md` anpassen:

  Alt:
  ```markdown
  **Aktueller Test-Stand:** `83 passed` — letzter Commit: `7c1f93e`
  ```

  Neu:
  ```markdown
  **Aktueller Test-Stand:** `~94 passed` — Plan 4 abgeschlossen
  ```

- [ ] **5.3** Den gesamten Abschnitt `## Offene Tasks (Plan 3)` aus `CLAUDE.md` entfernen (von `## Offene Tasks (Plan 3)` bis zum Ende des letzten Task-7-Blocks, vor `## Architektur-Überblick`).

- [ ] **5.4** Fertige Dateien-Tabelle in CLAUDE.md für Plan 4 ergänzen (nach dem Plan-3-Block in der "Fertige Dateien"-Sektion):

  ```markdown
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
  ```

- [ ] **5.5** Commit:

  ```bash
  git add CLAUDE.md
  git commit -m "docs: update CLAUDE.md for Plan 4 completion"
  ```

### Schritt 2: Abschluss-Verifikation + Tag

- [ ] **5.6** Finale Test-Suite laufen lassen:

  ```bash
  python -m pytest -v --tb=short
  ```

  Erwartetes Ergebnis: **~94 passed**, 0 failed, 0 errors

- [ ] **5.7** Git-Tag setzen:

  ```bash
  git tag v0.4.0-production-ready
  git log --oneline -5
  ```

---

## Zusammenfassung

| Task | Bereich | Neue Tests | Neue Dateien | Status |
|---|---|---|---|---|
| Task 1 | CI/CD + Tooling | 0 | `data/.gitkeep`, `.github/workflows/ci.yml`, `Makefile` | - [ ] |
| Task 2 | RSI-Strategie | 5 | `src/strategies/rsi.py` | - [ ] |
| Task 3 | Dashboard-Erweiterungen | 6 | `src/monitoring/templates/partials/strategies.html` | - [ ] |
| Task 4 | Deployment-Vorbereitung | 0 | `scripts/setup-vps.sh` | - [ ] |
| Task 5 | Abschluss + Tag | 0 | – | - [ ] |

**Test-Progression:** 83 → 88 → 94 → 94 → 94 passed

**Git-Tags nach diesem Plan:** `v0.4.0-production-ready`
