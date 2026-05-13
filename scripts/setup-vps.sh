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
