#!/usr/bin/env bash
# Sets up the always-on Avalon tracker on a fresh Raspberry Pi OS (or any Debian-based Linux).
#
#   curl -fsSL https://raw.githubusercontent.com/theartcher/avalon-trip-log/main/pi/install.sh -o install.sh
#   sudo bash install.sh
#
# Safe to run again: it updates the code and restarts the service, keeping the key and deploy key.
set -euo pipefail

REPO="theartcher/avalon-trip-log"
APP_DIR="/opt/avalon-trip-log"
DATA_DIR="$APP_DIR/logbook"
SVC_USER="avalon"
SVC_HOME="/var/lib/avalon"
ENV_FILE="/etc/avalon-tracker.env"
UNIT_FILE="/etc/systemd/system/avalon-tracker.service"

if [ "$(id -u)" -ne 0 ]; then
  exec sudo bash "$0" "$@"
fi

as_svc() { sudo -u "$SVC_USER" -H "$@"; }

echo "==> Installing packages"
apt-get update -qq
apt-get install -y -qq git python3-venv openssh-client >/dev/null

echo "==> Creating the '$SVC_USER' service user"
id "$SVC_USER" >/dev/null 2>&1 ||
  useradd --system --create-home --home-dir "$SVC_HOME" --shell /usr/sbin/nologin "$SVC_USER"

echo "==> Getting the code"
if [ ! -d "$APP_DIR/.git" ]; then
  git clone -q "https://github.com/$REPO.git" "$APP_DIR"
fi
chown -R "$SVC_USER:$SVC_USER" "$APP_DIR"
as_svc git -C "$APP_DIR" pull -q --ff-only origin main
as_svc git -C "$APP_DIR" config user.name "Avalon tracker (Raspberry Pi)"
as_svc git -C "$APP_DIR" config user.email "$SVC_USER@$(hostname)"

echo "==> Setting up the deploy key used to push positions"
if [ ! -f "$SVC_HOME/.ssh/id_ed25519" ]; then
  as_svc mkdir -p "$SVC_HOME/.ssh"
  as_svc ssh-keygen -q -t ed25519 -N "" -C "avalon-tracker@$(hostname)" -f "$SVC_HOME/.ssh/id_ed25519"
fi
ssh-keyscan -t ed25519 github.com 2>/dev/null | as_svc tee "$SVC_HOME/.ssh/known_hosts" >/dev/null
as_svc git -C "$APP_DIR" remote set-url --push origin "git@github.com:$REPO.git"

echo "==> Checking out the data branch"
if [ ! -d "$DATA_DIR" ]; then
  if as_svc git -C "$APP_DIR" ls-remote --exit-code --heads origin data >/dev/null; then
    as_svc git -C "$APP_DIR" fetch -q origin data
    as_svc git -C "$APP_DIR" worktree add -q -B data "$DATA_DIR" FETCH_HEAD
  else
    # Raspberry Pi OS's git is too old for `worktree add --orphan`, so start detached and orphan it.
    as_svc git -C "$APP_DIR" worktree add -q --detach "$DATA_DIR"
    as_svc git -C "$DATA_DIR" checkout -q --orphan data
    as_svc git -C "$DATA_DIR" rm -rfq .
  fi
fi

echo "==> Installing Python dependencies"
[ -d "$APP_DIR/.venv" ] || as_svc python3 -m venv "$APP_DIR/.venv"
as_svc "$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

if [ ! -f "$ENV_FILE" ]; then
  echo "==> aisstream.io API key"
  read -rsp "Paste your aisstream.io API key (input is hidden): " AIS_KEY </dev/tty
  echo
  umask 077
  cat >"$ENV_FILE" <<EOF
AISSTREAM_API_KEY=$AIS_KEY
MMSI=244000052
SYNC_MINUTES=10
DATA_DIR=$DATA_DIR
EOF
  chown "root:$SVC_USER" "$ENV_FILE"
  chmod 640 "$ENV_FILE"
fi

echo "==> Installing the systemd service"
cat >"$UNIT_FILE" <<EOF
[Unit]
Description=Avalon AIS tracker
Wants=network-online.target
After=network-online.target

[Service]
User=$SVC_USER
EnvironmentFile=$ENV_FILE
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python scripts/tracker.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable -q avalon-tracker
systemctl restart avalon-tracker

cat <<EOF

Done. The tracker is running and starts on every boot.

One step left, so the Pi can push positions to GitHub:
  1. Open https://github.com/$REPO/settings/keys/new
  2. Title: Raspberry Pi tracker
  3. Key:   $(cat "$SVC_HOME/.ssh/id_ed25519.pub")
  4. Tick "Allow write access" and click "Add key".

Useful commands:
  journalctl -u avalon-tracker -f      # live log
  sudo systemctl restart avalon-tracker
  sudo bash $APP_DIR/pi/install.sh     # update to the latest code
EOF
