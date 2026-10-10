#!/usr/bin/env bash
# Установка бота на чистый сервер (Ubuntu/Debian).
# Запускать из корня распакованного архива: sudo bash deploy/install.sh
set -euo pipefail

APP_DIR=/opt/baltika_bot
APP_USER=botuser
DB_NAME=baltika_bot
DB_USER=baltika

echo "==> Пакеты"
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip postgresql redis-server

echo "==> Пользователь $APP_USER"
id -u "$APP_USER" &>/dev/null || useradd -r -s /usr/sbin/nologin -d "$APP_DIR" "$APP_USER"

echo "==> База данных"
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1 || {
  DB_PASS=$(openssl rand -hex 16)
  sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';"
  sudo -u postgres createdb -O "$DB_USER" "$DB_NAME"
  echo "Пароль БД: $DB_PASS  (впиши его в .env)"
}

echo "==> Код в $APP_DIR"
mkdir -p "$APP_DIR"
cp -r app deploy requirements.txt README.md "$APP_DIR"/
[ -f "$APP_DIR/.env" ] || cp .env.example "$APP_DIR/.env"

echo "==> Виртуальное окружение"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chmod 600 "$APP_DIR/.env"

echo "==> systemd"
cp deploy/baltika-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable baltika-bot

cat <<MSG

Готово. Осталось:
  1. nano $APP_DIR/.env      — вписать BOT_TOKEN и пароль БД
  2. systemctl start baltika-bot
  3. journalctl -u baltika-bot -f

MSG
