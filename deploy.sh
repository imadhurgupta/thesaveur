#!/bin/bash
# ─── The Saveur – One-command deploy script ───────────────────────────────
# Usage: bash deploy.sh yourdomain.com your@email.com
# Run this on your Oracle Cloud / VPS server

set -e  # Exit on any error

DOMAIN=$1
EMAIL=$2

if [ -z "$DOMAIN" ] || [ -z "$EMAIL" ]; then
    echo "Usage: bash deploy.sh yourdomain.com your@email.com"
    exit 1
fi

echo ""
echo "========================================="
echo "  Deploying The Saveur to $DOMAIN"
echo "========================================="
echo ""

# ── 1. Install Docker ────────────────────────────────────────────────────────
echo ">>> Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker $USER
    echo "Docker installed."
else
    echo "Docker already installed."
fi

# ── 2. Install Docker Compose ────────────────────────────────────────────────
if ! command -v docker compose &> /dev/null; then
    apt-get install -y docker-compose-plugin
fi

# ── 3. Replace YOUR_DOMAIN placeholder in all config files ──────────────────
echo ">>> Configuring domain: $DOMAIN"
sed -i "s/YOUR_DOMAIN.com/$DOMAIN/g" nginx/nginx.conf
sed -i "s/YOUR_DOMAIN.com/$DOMAIN/g" nginx/nginx_temp.conf
sed -i "s/YOUR_DOMAIN.com/$DOMAIN/g" docker-compose.certbot.yml
sed -i "s/YOUR_EMAIL@gmail.com/$EMAIL/g" docker-compose.certbot.yml

# ── 4. Create .env if missing ────────────────────────────────────────────────
if [ ! -f .env ]; then
    echo ""
    echo "!!! .env file not found. Creating from template..."
    cp .env.example .env
    echo ">>> IMPORTANT: Edit .env now with your real secrets!"
    echo "    nano .env"
    echo "    Then re-run this script."
    exit 1
fi

# ── 5. Create required directories ───────────────────────────────────────────
mkdir -p nginx/certs nginx/certbot-webroot

# ── 6. Get SSL certificate ───────────────────────────────────────────────────
echo ">>> Getting SSL certificate for $DOMAIN..."
docker compose -f docker-compose.certbot.yml up --abort-on-container-exit

# Copy certs to the nginx/certs folder expected by main docker-compose
CERT_SRC="./nginx/certs/live/$DOMAIN"
if [ -d "$CERT_SRC" ]; then
    cp "$CERT_SRC/fullchain.pem" ./nginx/certs/fullchain.pem
    cp "$CERT_SRC/privkey.pem"   ./nginx/certs/privkey.pem
    echo "SSL certificates copied."
else
    echo "ERROR: Certificates not found at $CERT_SRC"
    echo "Make sure your domain DNS is pointing to this server's IP."
    exit 1
fi

# ── 7. Build and start all containers ────────────────────────────────────────
echo ">>> Building Docker images..."
docker compose build

echo ">>> Starting all services..."
docker compose up -d

# ── 8. Done ──────────────────────────────────────────────────────────────────
echo ""
echo "========================================="
echo "  ✅ The Saveur is LIVE!"
echo "  https://$DOMAIN"
echo "========================================="
echo ""
echo "Useful commands:"
echo "  docker compose logs -f         # View live logs"
echo "  docker compose restart web     # Restart Flask app"
echo "  docker compose down            # Stop everything"
echo "  docker compose up -d --build   # Rebuild after code changes"
