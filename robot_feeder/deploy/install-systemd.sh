#!/usr/bin/env bash
# Install care-robot-feeder.service on Jetson. Run as root or with sudo.
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
FEEDER_DIR="${FEEDER_DIR:-$REPO_ROOT/robot_feeder}"
UNIT_SRC="$FEEDER_DIR/deploy/care-robot-feeder.service"
UNIT_DST=/etc/systemd/system/care-robot-feeder.service

if [[ ! -f "$UNIT_SRC" ]]; then
  echo "Missing $UNIT_SRC" >&2
  exit 1
fi

sed "s|/home/jetson/C.A.R.E/robot_feeder|$FEEDER_DIR|g" "$UNIT_SRC" > /tmp/care-robot-feeder.service
sudo cp /tmp/care-robot-feeder.service "$UNIT_DST"
sudo systemctl daemon-reload
echo "Installed $UNIT_DST"
echo "  sudo systemctl enable --now care-robot-feeder"
echo "  journalctl -u care-robot-feeder -f"
