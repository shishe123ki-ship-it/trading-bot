# Design: Dashboard Live-Steuerung (Verbindungsstatus + Strategie-Toggle)

**Datum:** 2026-05-14  
**Status:** Genehmigt

---

## Ziel

Das bestehende Dashboard um drei Features erweitern:
1. **Verbindungsstatus** — zeigt ob der Bot mit Bybit WebSocket verbunden ist (grün/rot)
2. **Strategie ein/ausschalten** — Toggle-Button pro Strategie, wirksam innerhalb ~30 Sekunden
3. Keine Parameter-Änderungen (Scope bewusst begrenzt)

---

## Architektur

Die bestehende `portfolio.db` SQLite-Datei (bereits als Docker-Volume zwischen Bot und Dashboard geteilt) dient als IPC-Brücke.

```
Bot (main.py)
├── _heartbeat_loop()          → schreibt bot_status (alle 10s)
└── _strategy_watcher_loop()   → liest strategy_overrides (alle 30s)

Dashboard (dashboard.py)
├── GET  /api/status                        → liest bot_status
├── GET  /partials/status                   → HTMX-Partial (Verbindungsanzeige)
├── POST /api/strategies/{id}/toggle        → schreibt strategy_overrides
└── GET  /partials/strategies               → liest strategy_overrides für Toggle-Status
```

---

## Datenbankschema (Ergänzungen zu portfolio.db)

```sql
-- Einzige Zeile (id=1), wird alle 10s überschrieben (UPSERT)
CREATE TABLE IF NOT EXISTS bot_status (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    timestamp   TEXT    NOT NULL,
    ws_connected INTEGER NOT NULL DEFAULT 0
);

-- Eine Zeile pro Strategie
CREATE TABLE IF NOT EXISTS strategy_overrides (
    strategy_id TEXT    PRIMARY KEY,
    enabled     INTEGER NOT NULL DEFAULT 1,
    updated_at  TEXT    NOT NULL
);
```

Tabellen werden in `PortfolioTracker.initialize()` angelegt (bestehender Ort für alle DDL-Statements).

---

## Bot-Änderungen (src/main.py + src/data/feed.py + src/portfolio/tracker.py)

### tracker.py
- `CREATE TABLE IF NOT EXISTS bot_status` in `initialize()`
- `CREATE TABLE IF NOT EXISTS strategy_overrides` in `initialize()`

### feed.py
- Neues Property `connected: bool` — gibt den internen WebSocket-Verbindungsstatus zurück

### main.py

**`_init_strategy_overrides(db_path, strategies)`**  
Beim Start: INSERT OR IGNORE für jede Strategie mit `enabled = strategy.config.enabled`.  
Stellt sicher dass das Dashboard von Beginn an Daten hat.

**`_heartbeat_loop(db_path, feed)`**  
- Läuft als `asyncio.create_task()` in der Hauptschleife
- Alle 10 Sekunden: UPSERT in `bot_status` mit aktuellem Zeitstempel + `feed.connected`
- Endet wenn `stop_event` gesetzt wird

**`_strategy_watcher_loop(db_path, strategy_enabled)`**  
- Läuft als `asyncio.create_task()`
- Alle 30 Sekunden: liest alle Zeilen aus `strategy_overrides`
- Aktualisiert das Dict `strategy_enabled: dict[str, bool]`
- Endet wenn `stop_event` gesetzt wird

**`_dispatch_candle` (geändert)**  
```python
async def _dispatch_candle(event: Event) -> None:
    candle = event.data
    for strategy in strategies:
        if not strategy_enabled.get(strategy.id, True):
            continue  # Strategie deaktiviert
        if candle.symbol in strategy.config.symbols:
            sig = await strategy.on_candle(candle)
            ...
```

**`BaseStrategy`** — keine Änderungen nötig.

---

## Dashboard-Änderungen (src/monitoring/dashboard.py)

### Neue Endpoints

**`GET /api/status`**
```python
# Liest bot_status; wenn kein Eintrag oder älter als 60s → connected: False
{"connected": bool, "last_seen": str | None}
```

**`GET /partials/status`**  
HTMX-Partial: rendert `partials/status.html` mit den Status-Daten.

**`POST /api/strategies/{strategy_id}/toggle`**  
- Liest aktuellen `enabled`-Wert aus `strategy_overrides`
- Flippt den Wert (0→1 oder 1→0)
- Schreibt zurück mit aktuellem Zeitstempel
- Gibt die aktualisierte `<tr>`-Zeile als HTML zurück; HTMX tauscht sie via `hx-target="closest tr" hx-swap="outerHTML"` direkt aus

### Geänderter Endpoint

**`GET /partials/strategies`**  
- Liest weiterhin Trade-Counts aus `trades`
- Liest zusätzlich `enabled`-Status aus `strategy_overrides`
- Merged beide Datenquellen: Strategien ohne Trades aber mit Override werden trotzdem angezeigt

---

## Templates

### Neu: `partials/status.html`
```
● Verbunden  (grüner Punkt, last_seen vor Xs)
● Offline    (roter Punkt, last_seen vor Xs / nie gesehen)
```

### Geändert: `partials/strategies.html`
Spalte "An/Aus" mit Toggle-Button per HTMX:
```html
<button hx-post="/api/strategies/{{ s.strategy_id }}/toggle"
        hx-target="closest tr"
        hx-swap="outerHTML">
  {% if s.enabled %}✅{% else %}⬜{% endif %}
</button>
```

### Geändert: `index.html`
Status-Bereich oben einfügen:
```html
<div hx-get="/partials/status"
     hx-trigger="load, every 15s"
     hx-swap="innerHTML">
</div>
```

---

## Tests

Bestehende Test-Datei: `tests/unit/test_dashboard.py`

Neue Tests:
- `test_status_no_db` → gibt `connected: False` zurück wenn DB fehlt
- `test_status_connected` → gibt `connected: True` bei frischem Heartbeat
- `test_status_stale` → gibt `connected: False` wenn Heartbeat > 60s alt
- `test_toggle_strategy` → POST flippt `enabled` in `strategy_overrides`
- `test_strategies_partial_shows_enabled_state` → Partial enthält Toggle-Buttons

Bestehende Test-Datei: `tests/unit/test_portfolio_tracker.py`

Neue Tests:
- `test_creates_bot_status_table` → Tabelle existiert nach `initialize()`
- `test_creates_strategy_overrides_table` → Tabelle existiert nach `initialize()`

---

## Nicht im Scope

- Parameter-Änderungen (EMA-Werte, Period, etc.)
- Symbol- oder Interval-Änderungen (würde Feed-Neuabonnement erfordern)
- Bot-Neustart über Dashboard
- Authentifizierung für Toggle-Endpoint (Dashboard läuft hinter Caddy basicauth)
