#!/usr/bin/env bash
# One-time setup on the VM: deploy main automatically after every merge.
#
#     cd ~/hp && deploy/install-autodeploy.sh
#
# Installs a systemd timer that runs deploy/autodeploy.sh every two minutes as
# the current user (who must be able to run docker). Re-running is harmless.
#
#     systemctl list-timers hp-autodeploy.timer   # next run
#     journalctl -u hp-autodeploy -f              # what it did
#     sudo systemctl disable --now hp-autodeploy.timer   # turn it off

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_AS="$(id -un)"

[[ "$RUN_AS" != root ]] || { echo "run as the deploy user, not root"; exit 1; }
docker info >/dev/null 2>&1 || { echo "$RUN_AS cannot run docker"; exit 1; }
chmod +x "$REPO/deploy/deploy.sh" "$REPO/deploy/autodeploy.sh"

sudo tee /etc/systemd/system/hp-autodeploy.service >/dev/null <<EOF
[Unit]
Description=Deploy origin/main of HP Account Intelligence once CI has passed
Wants=network-online.target
After=network-online.target docker.service

[Service]
Type=oneshot
User=$RUN_AS
Environment=HOME=$HOME
ExecStart=$REPO/deploy/autodeploy.sh
# A deploy builds both images on a small VM.
TimeoutStartSec=45min
EOF

sudo tee /etc/systemd/system/hp-autodeploy.timer >/dev/null <<EOF
[Unit]
Description=Check for a new commit on main every two minutes

[Timer]
OnBootSec=2min
OnUnitInactiveSec=2min

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now hp-autodeploy.timer
systemctl list-timers hp-autodeploy.timer --no-pager
