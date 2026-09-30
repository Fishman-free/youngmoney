#!/usr/bin/env bash
# bnbot Tokyo VPS bootstrap — Ubuntu 22.04/24.04, run as root:
#
#   curl -fsSL https://raw.githubusercontent.com/Fishman-free/youngmoney/master/scripts/vps-bootstrap.sh -o /tmp/b.sh
#   sudo bash /tmp/b.sh
#
# Installs the runtime, clones the repo, seeds config, installs two systemd
# units (three-sleeve paper loop + read-only status server) and prints the
# latency check. It NEVER asks for or writes API keys — you add .env yourself.
set -euo pipefail

REPO="${REPO:-https://github.com/Fishman-free/youngmoney.git}"
APP_DIR="${APP_DIR:-/opt/bnbot}"
USER_NAME="${USER_NAME:-trader}"

echo "== 1/6 packages =="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git curl ufw

echo "== 2/6 user =="
id -u "$USER_NAME" >/dev/null 2>&1 || adduser --disabled-password --gecos "" "$USER_NAME"
mkdir -p "$APP_DIR"
chown "$USER_NAME":"$USER_NAME" "$APP_DIR"

echo "== 3/6 clone =="
if [ -d "$APP_DIR/.git" ]; then
  sudo -u "$USER_NAME" git -C "$APP_DIR" pull --ff-only
else
  sudo -u "$USER_NAME" git clone "$REPO" "$APP_DIR"
fi

echo "== 4/6 venv + deps =="
sudo -u "$USER_NAME" python3 -m venv "$APP_DIR/.venv"
sudo -u "$USER_NAME" "$APP_DIR/.venv/bin/pip" install -q --upgrade pip
# core platform is pure stdlib; laya is the optional probabilistic judgment layer
sudo -u "$USER_NAME" "$APP_DIR/.venv/bin/pip" install -q laya || \
  echo "   (laya install skipped — judgment layer will degrade to pass-through)"

if [ ! -f "$APP_DIR/.env" ]; then
  cat > "$APP_DIR/.env" <<'EOF'
# Fill these in, then: chmod 600 .env
BN_API_KEY=
BN_API_SECRET=
EOF
  chown "$USER_NAME":"$USER_NAME" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
  echo "   seeded $APP_DIR/.env — you MUST fill it in"
fi

echo "== 5/6 systemd =="
cat > /etc/systemd/system/bnbot-paper.service <<EOF
[Unit]
Description=bnbot three-sleeve paper loop
After=network-online.target
Wants=network-online.target
[Service]
User=$USER_NAME
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python -m bnbot.live --sleeves
Restart=always
RestartSec=30
[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/bnbot-status.service <<EOF
[Unit]
Description=bnbot status dashboard (read-only)
After=network-online.target
[Service]
User=$USER_NAME
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python -m bnbot.server --port 8787
Restart=always
[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now bnbot-paper bnbot-status
sleep 2
systemctl --no-pager --lines=3 status bnbot-paper || true

echo "== 6/6 latency =="
sudo -u "$USER_NAME" "$APP_DIR/.venv/bin/python" "$APP_DIR/scripts/vps-latency-check.py" || true

cat <<'NEXT'

Done. Next steps:
  1. edit /opt/bnbot/.env  (BN_API_KEY / BN_API_SECRET), chmod 600
  2. whitelist THIS machine's static IP in Binance API settings
  3. dashboard: ssh -L 8787:localhost:8787 trader@<vps-ip>  then open http://127.0.0.1:8787/dashboard
  4. gate report: python -m bnbot.gate --sleeve C
NEXT
