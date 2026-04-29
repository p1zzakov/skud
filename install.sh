#!/bin/bash
# ================================================================
# СКУД ЭРА-500 — Установка на Ubuntu
# Использование: sudo bash install.sh
# ================================================================
set -e

SERVER_IP="192.168.1.53"
APP_DIR="/opt/skud"
DATA_DIR="/opt/skud/data"
FRONT_DIR="/opt/skud/frontend"
BACK_DIR="/opt/skud/backend"
SERVICE_USER="skud"
PYTHON="python3"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

[ "$EUID" -ne 0 ] && error "Запустите с sudo: sudo bash install.sh"

info "=== Установка СКУД ЭРА-500 ==="

# ── 1. Система ──────────────────────────────────────────────────
info "Обновление пакетов..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv nodejs npm nginx curl

# ── 2. Пользователь и директории ────────────────────────────────
info "Создание пользователя и директорий..."
id -u $SERVICE_USER &>/dev/null || useradd -r -s /bin/false $SERVICE_USER
mkdir -p $APP_DIR $DATA_DIR $FRONT_DIR $BACK_DIR
chown -R $SERVICE_USER:$SERVICE_USER $APP_DIR

# ── 3. Бэкенд ───────────────────────────────────────────────────
info "Установка Python зависимостей..."
python3 -m venv $APP_DIR/venv
$APP_DIR/venv/bin/pip install -q --upgrade pip
$APP_DIR/venv/bin/pip install -q fastapi uvicorn[standard] aiosqlite pydantic

# Копируем бэкенд
cp -r backend/* $BACK_DIR/
chown -R $SERVICE_USER:$SERVICE_USER $BACK_DIR

# ── 4. Фронтенд ─────────────────────────────────────────────────
info "Сборка фронтенда..."
cd /tmp
mkdir -p skud_front
cd skud_front

# Создаём Vite проект
cat > package.json << 'PKGJSON'
{
  "name": "skud-frontend",
  "version": "1.0.0",
  "scripts": {
    "build": "vite build",
    "dev": "vite"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.0.0",
    "vite": "^5.0.0",
    "tailwindcss": "^3.4.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0"
  }
}
PKGJSON

cat > vite.config.js << 'VITECONF'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({
  plugins: [react()],
  build: { outDir: '/opt/skud/frontend' },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws':  { target: 'ws://localhost:8000', ws: true }
    }
  }
})
VITECONF

cat > tailwind.config.js << 'TWCONF'
export default { content: ["./index.html","./src/**/*.{js,jsx}"] }
TWCONF

cat > postcss.config.js << 'PCCONF'
export default { plugins: { tailwindcss: {}, autoprefixer: {} } }
PCCONF

mkdir -p src
cat > index.html << 'HTML'
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>СКУД ЭРА-500</title>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/main.jsx"></script>
</body>
</html>
HTML

cat > src/main.jsx << 'MAIN'
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'
ReactDOM.createRoot(document.getElementById('root')).render(<App/>)
MAIN

cat > src/index.css << 'CSS'
@tailwind base;
@tailwind components;
@tailwind utilities;
CSS

# Копируем App.jsx
cp /opt/skud/backend/../App.jsx src/App.jsx 2>/dev/null || \
  cp /home/*/skud/frontend/src/App.jsx src/App.jsx 2>/dev/null || true

# Если App.jsx не нашёлся — создаём заглушку
if [ ! -f src/App.jsx ]; then
  warn "App.jsx не найден, создаём заглушку..."
  cat > src/App.jsx << 'APPJS'
export default function App() {
  return <div style={{padding:40,fontFamily:"sans-serif"}}>
    <h1>СКУД ЭРА-500</h1>
    <p>Бэкенд запущен. Скопируйте App.jsx и пересоберите.</p>
  </div>
}
APPJS
fi

npm install --silent
npm run build

info "Фронтенд собран в $FRONT_DIR"
chown -R $SERVICE_USER:$SERVICE_USER $FRONT_DIR

# ── 5. Nginx ────────────────────────────────────────────────────
info "Настройка Nginx..."
cat > /etc/nginx/sites-available/skud << NGINX
server {
    listen 80;
    server_name $SERVER_IP _;

    # Фронтенд
    root $FRONT_DIR;
    index index.html;

    # API → бэкенд
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    # WebSocket
    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }

    # SPA fallback
    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/skud /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# ── 6. Systemd сервис ───────────────────────────────────────────
info "Создание systemd сервиса..."
cat > /etc/systemd/system/skud.service << SERVICE
[Unit]
Description=SKUD ERA-500 Backend
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$BACK_DIR
Environment="DB_PATH=$DATA_DIR/skud.db"
ExecStart=$APP_DIR/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable skud
systemctl start skud

# ── 7. Firewall ─────────────────────────────────────────────────
info "Настройка firewall..."
if command -v ufw &>/dev/null; then
    ufw allow 80/tcp    comment "SKUD web"  2>/dev/null || true
    ufw allow 7714/udp  comment "ERA-500 controllers" 2>/dev/null || true
    ufw allow 7715/udp  comment "ERA-500 commands"    2>/dev/null || true
fi

# ── 8. Проверка ─────────────────────────────────────────────────
sleep 3
if systemctl is-active --quiet skud; then
    info "✅ Сервис запущен успешно!"
else
    warn "Сервис не запустился. Проверьте: journalctl -u skud -n 50"
fi

echo ""
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}  СКУД ЭРА-500 установлена!${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo ""
echo "  Веб-интерфейс: http://$SERVER_IP"
echo "  Логин:         admin"
echo "  Пароль:        admin"
echo ""
echo "  Логи:          journalctl -u skud -f"
echo "  Статус:        systemctl status skud"
echo ""
echo "  Миграция из ЭНТ:"
echo "  $APP_DIR/venv/bin/python $BACK_DIR/migrate_from_ent.py \\"
echo "    --host 192.168.1.54 --show-tables"
echo ""
