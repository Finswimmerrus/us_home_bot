#!/usr/bin/env bash
set -euo pipefail

exec 9>/run/lock/us-home-bot-deploy.lock
flock -n 9 || exit 0

app_dir=/opt/us_home_bot
service_name=us-home-bot.service
marker_file=$app_dir/.deployed-commit
cd "$app_dir"

runuser -u us-home-bot -- git fetch --quiet origin main
current_commit=$(runuser -u us-home-bot -- git rev-parse HEAD)
target_commit=$(runuser -u us-home-bot -- git rev-parse origin/main)
deployed_commit=$(cat "$marker_file" 2>/dev/null || true)

if [ "$deployed_commit" = "$target_commit" ]; then
  exit 0
fi

systemctl stop "$service_name"
restart_needed=1
previous_commit=$current_commit

rollback() {
  runuser -u us-home-bot -- git reset --hard "$previous_commit"
  runuser -u us-home-bot -- .venv/bin/python -m pip install --quiet . || true
  systemctl start "$service_name" || true
}

trap 'if [ "${restart_needed:-0}" = 1 ]; then rollback; fi' EXIT

if [ -f couple_bot.db ]; then
  cp -p couple_bot.db couple_bot.db.pre-deploy
  chown us-home-bot:us-home-bot couple_bot.db.pre-deploy
  chmod 600 couple_bot.db.pre-deploy
fi

runuser -u us-home-bot -- git reset --hard "$target_commit"
runuser -u us-home-bot -- .venv/bin/python -m pip install --quiet .
chown -R us-home-bot:us-home-bot "$app_dir"
systemctl start "$service_name"
systemctl is-active --quiet "$service_name"
printf '%s\n' "$target_commit" > "$marker_file"
chown us-home-bot:us-home-bot "$marker_file"
restart_needed=0
trap - EXIT
logger -t us-home-bot-deploy "Deployed $target_commit"
