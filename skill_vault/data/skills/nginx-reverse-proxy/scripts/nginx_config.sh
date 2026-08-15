#!/usr/bin/env bash
# nginx reverse proxy setup script - validates and applies a server block
# Usage: ./nginx_config.sh <domain> <backend_port>
set -euo pipefail

DOMAIN="${1:-}"
PORT="${2:-}"

if [[ -z "$DOMAIN" || -z "$PORT" ]]; then
    echo "Usage: $0 <domain> <backend_port>" >&2
    echo "Example: $0 api.example.com 8080" >&2
    exit 2
fi

CONF_FILE="/etc/nginx/sites-available/${DOMAIN}.conf"
ENABLED_LINK="/etc/nginx/sites-enabled/${DOMAIN}.conf"

echo "==> Generating config for $DOMAIN -> 127.0.0.1:$PORT"

sudo tee "$CONF_FILE" > /dev/null <<EOF
server {
    listen 80;
    server_name ${DOMAIN};

    # Redirect HTTP to HTTPS (remove if not using TLS yet)
    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl http2;
    server_name ${DOMAIN};

    # Cert paths (placeholder - certbot will replace these)
    ssl_certificate     /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;

    # Modern TLS settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;

    location / {
        proxy_pass http://127.0.0.1:${PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        # WebSocket/SSE support
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeouts
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }

    # Health check endpoint (no auth, no logging noise)
    location /healthz {
        proxy_pass http://127.0.0.1:${PORT}/healthz;
        access_log off;
    }
}
EOF

echo "==> Testing configuration..."
if sudo nginx -t; then
    sudo ln -sf "$CONF_FILE" "$ENABLED_LINK"
    sudo systemctl reload nginx
    echo "==> Config applied and nginx reloaded"
else
    echo "==> Config test FAILED - file saved but NOT enabled" >&2
    exit 1
fi

echo "==> To get TLS: sudo certbot --nginx -d ${DOMAIN}"