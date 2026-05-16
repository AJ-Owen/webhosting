# Beszel

Lightweight host + container metrics dashboard at `https://beszel.joshowen.uk`.

## How it works

- **Hub** (`beszel` container) — web UI + central DB, listens on `:8090` (proxied by nginx, gated by Authelia like other services)
- **Agent** (`beszel-agent` container) — collects host metrics, runs `network_mode: host`, listens on `:45876`
- Hub connects to each agent over **SSH** using an ed25519 keypair generated automatically on first hub start (stored in `data/hub/id_ed25519`)
- The public key is cached in `.env` as `BESZEL_AGENT_KEY` and passed to the agent via the `KEY` env var — both ends must match

## Why this networking setup

- Agent needs `network_mode: host` to see real host CPU/mem/disk/network (not container ones)
- Hub is on `docker_proxy_network` so nginx can reach it by name
- Hub reaches the agent via `host.docker.internal` (mapped to docker bridge gateway, `172.17.0.1`)
- **UFW rules** were added on the VPS to allow `172.17.0.0/16` and `172.18.0.0/16` → `:45876`. Port 45876 is **not** exposed to the internet, only to docker.

## Files

- `docker-compose.yml` — hub + local agent
- `.env` — `BESZEL_AGENT_KEY` (gitignored, regenerate from `data/hub/id_ed25519` if lost)
- `data/hub/` — hub SQLite DB + keypair (gitignored)
- `data/agent/` — agent state (gitignored)

## Adding the first system in the hub UI

1. Log into `https://beszel.joshowen.uk` (first signup becomes admin)
2. **Add System**:
   - Name: `cloud-vps` (or whatever)
   - Host: `host.docker.internal`
   - Port: `45876`
3. Public key is pre-filled — save.

## Adding remote hosts (proxmox node, raspberry pi)

On the remote host, install the agent as a container or systemd binary. Container example:

```yaml
services:
  beszel-agent:
    image: henrygd/beszel-agent:latest
    container_name: beszel-agent
    restart: unless-stopped
    network_mode: host
    volumes:
      - ./data:/var/lib/beszel-agent
      - /var/run/docker.sock:/var/run/docker.sock:ro
    environment:
      LISTEN: 45876
      KEY: "ssh-ed25519 AAAA...<same pubkey from cloud VPS .env>..."
```

Then on the hub, **Add System** with that host's IP/hostname and port 45876.
**Important**: agent port should NOT be open to the internet — restrict via firewall to the cloud VPS IP only, or (better) put the hosts on a Tailscale/WireGuard mesh and use those IPs.

## Wiring alerts to ntfy

In the hub UI → **Settings → Notifications**:

- URL: `https://ntfy.joshowen.uk/server-alerts`
- Custom header: `Authorization: Bearer <NTFY_TOKEN from apps/ntfy/.env>`

Or use shoutrrr URL form (if Beszel's notifications use shoutrrr):
```
generic://ntfy.joshowen.uk/server-alerts?Authorization=Bearer+<token>
```

Then per-system, set thresholds (CPU %, mem %, disk %, status).

## Quick reference

```bash
# Status
docker compose ps
docker compose logs -f beszel
docker compose logs -f beszel-agent

# Recreate after config changes
docker compose up -d

# Pull new images
docker compose pull && docker compose up -d

# Backup hub DB (SQLite, WAL — copy with sqlite cli or shut down first)
docker compose stop beszel
sudo cp -r data/hub data/hub.backup-$(date +%Y%m%d)
docker compose up -d beszel

# Reissue agent key (e.g. on key compromise)
# 1. Stop hub, delete data/hub/id_ed25519, restart hub (regenerates)
# 2. Refresh BESZEL_AGENT_KEY in .env from the new pubkey
# 3. Restart agent(s) so they accept the new key
sudo ssh-keygen -y -f data/hub/id_ed25519   # print pubkey
```

## Troubleshooting

- **System shows "down"**: check (a) agent container running on remote host, (b) port 45876 reachable from hub (test from any sibling container: `nc -zv <host> 45876`), (c) `KEY` env on agent matches hub's `id_ed25519.pub`.
- **Hub can't reach `host.docker.internal`**: check UFW allows the docker subnet → port 45876 on the VPS.
- **Wrong disk being reported**: agent picks the disk holding `/` by default; set `FILESYSTEM=<device>` in the agent env if it picks the wrong one.
