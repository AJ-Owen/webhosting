# ntfy

Self-hosted push notifications at `https://ntfy.joshowen.uk`.

## How it works

- ntfy container behind nginx reverse proxy
- **Authelia is bypassed** for `ntfy.joshowen.uk` (rule in `nginx/config/configuration.yml`) so phone/CLI clients can authenticate directly with ntfy
- ntfy uses its **own auth** with `auth-default-access: deny-all` — anonymous access is blocked
- Auth DB at `data/auth.db` (created automatically, persists in the data volume)

## Users

| User      | Role  | Purpose                                            |
|-----------|-------|----------------------------------------------------|
| `josh`    | admin | Personal subscribing/publishing, admin tasks       |
| `monitor` | user  | Service account, write-only to `*`, token-based   |

Admin password lives in your password manager (not in this repo).
The `monitor` token is in `.env` (gitignored) and used by Beszel + cron scripts.

## Topics

- `server-alerts` — fail2ban daily summary, threshold alerts from cron scripts
- `beszel*` — anything emitted by Beszel webhook notifications

## Files

- `docker-compose.yml` — single ntfy container on `docker_proxy_network`
- `server.yml` — ntfy config (auth-file, base-url, behind-proxy)
- `.env` — `NTFY_TOKEN`, `NTFY_TOPIC`, `NTFY_URL` for the fail2ban script (gitignored)
- `fail2ban-summary.sh` — daily summary script, runs from **root** crontab at `0 8 * * *`

## Quick reference

### Add / manage users
```bash
# Create a user (admin role grants access to all topics)
docker compose exec -e NTFY_PASSWORD='<pw>' ntfy ntfy user add --role=user <name>

# List all users
docker compose exec ntfy ntfy user list

# Change password
docker compose exec -e NTFY_PASSWORD='<new>' ntfy ntfy user change-pass <name>

# Delete user
docker compose exec ntfy ntfy user del <name>
```

### Access control (ACLs)
```bash
# Show a user's ACLs
docker compose exec ntfy ntfy access <name>

# Grant access — modes: read-write | read-only | write-only | deny
docker compose exec ntfy ntfy access <name> '<topic-or-pattern>' write-only

# Reset all ACLs for a user
docker compose exec ntfy ntfy access --reset <name>

# Patterns: 'topic-name' (exact), 'beszel*' (prefix), '*' (everything)
```

### Tokens
```bash
# Create a token (never expires by default)
docker compose exec ntfy ntfy token add --label "<purpose>" <user>

# List a user's tokens
docker compose exec ntfy ntfy token list <user>

# Revoke a token
docker compose exec ntfy ntfy token remove <user> <token>
```

### Publishing from the CLI
```bash
# With token
curl -H "Authorization: Bearer $NTFY_TOKEN" -d "msg" https://ntfy.joshowen.uk/server-alerts

# With user/pass
curl -u josh:'<pw>' -d "msg" https://ntfy.joshowen.uk/<topic>

# With title / priority / tags
curl -H "Authorization: Bearer $NTFY_TOKEN" \
     -H "Title: Disk full" -H "Priority: 5" -H "Tags: warning,floppy_disk" \
     -d "..." https://ntfy.joshowen.uk/server-alerts
```

### Logs / debugging
```bash
docker compose logs -f ntfy
# auth issues — check that the bypass for ntfy.joshowen.uk is above the wildcard
# rule in nginx/config/configuration.yml
```
