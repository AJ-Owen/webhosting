#!/usr/bin/env bash
# Daily fail2ban summary → ntfy.
# Reads creds from /home/josh/repos/apps/ntfy/.env (NTFY_USER, NTFY_PASS, NTFY_TOPIC).
# Run via cron as root (needs to read fail2ban socket).

set -euo pipefail

ENV_FILE="/home/josh/repos/apps/ntfy/.env"
# shellcheck disable=SC1090
[ -f "$ENV_FILE" ] && . "$ENV_FILE"

: "${NTFY_TOKEN:?NTFY_TOKEN not set}"
: "${NTFY_TOPIC:=server-alerts}"
: "${NTFY_URL:=https://ntfy.joshowen.uk}"

JAILS=$(fail2ban-client status | awk -F'Jail list:' '/Jail list/ {print $2}' | tr -d ',\t')

total_currently=0
total_ever=0
lines=()

for jail in $JAILS; do
  status=$(fail2ban-client status "$jail")
  curr=$(echo "$status" | awk -F'\t' '/Currently banned:/ {print $NF+0}')
  ever=$(echo "$status" | awk -F'\t' '/Total banned:/ {print $NF+0}')
  failed=$(echo "$status" | awk -F'\t' '/Currently failed:/ {print $NF+0}')
  total_currently=$((total_currently + curr))
  total_ever=$((total_ever + ever))
  lines+=("$jail: ${curr} banned now (${ever} total, ${failed} failing)")
done

uptime_str=$(uptime -p)
host=$(hostname)
priority=3
[ "$total_currently" -gt 10 ] && priority=4

body="Host: ${host}\nUptime: ${uptime_str}\nCurrently banned: ${total_currently}\nTotal bans (since restart): ${total_ever}\n\n"
for l in "${lines[@]}"; do body+="• ${l}\n"; done

curl -sS -H "Authorization: Bearer ${NTFY_TOKEN}" \
  -H "Title: fail2ban daily summary — ${host}" \
  -H "Priority: ${priority}" \
  -H "Tags: shield" \
  -d "$(printf '%b' "$body")" \
  "${NTFY_URL}/${NTFY_TOPIC}" > /dev/null
