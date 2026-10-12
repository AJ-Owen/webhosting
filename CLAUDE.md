# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture Overview

This is a monorepo containing multiple dockerized services that run on a home server. Each service is self-contained with its own `docker-compose.yml` file and can be managed independently. Key design patterns:

- **Nginx reverse proxy** (`nginx/`) routes all external traffic and handles SSL/TLS via certbot
- **Authelia** (`nginx/`) provides authentication/authorization for services that need it
- **Docker network** (`docker_proxy_network`) allows inter-service communication
- **Watchtower** monitors services for updates and auto-upgrades labeled containers
- **Persistent data** is stored in each service's `data/` directory, which is gitignored

## Common Commands

### Service Management
```bash
# In a service directory, e.g., cd actual-budget/
docker compose up -d              # Start service in background
docker compose down               # Stop and remove containers
docker compose ps                 # Check running containers
docker compose logs -f            # Stream logs (Ctrl+C to exit)
docker compose logs <service>     # View specific service logs
docker compose restart <service>  # Restart a container
```

### Viewing Configuration
```bash
# Check what will be deployed (dry-run)
docker compose config

# View environment variables loaded from .env
cat .env
```

### Troubleshooting
```bash
# Access a running container
docker compose exec <service> /bin/bash

# Check container health
docker compose ps  # STATUS column shows health status

# Rebuild image if Dockerfile changed
docker compose build --no-cache <service>
```

## Directory Structure

```
apps/
├── nginx/                    # Reverse proxy, SSL certs, Authelia auth
│   ├── docker-compose.yml
│   ├── nginx.conf           # Main nginx config (routes all traffic)
│   ├── data/certbot/        # Let's Encrypt certificates
│   └── config/              # Authelia configuration
├── actual-budget/           # Personal finance app
├── calibre-web-automated/   # Book library
├── paperless/               # Document management
├── n8n/                     # Automation engine
├── nginx/                   # (nginx acts as reverse proxy for all)
└── [other-services]/        # Each service has same structure
```

## Important Services

### Nginx (Reverse Proxy)
- Entry point for all external traffic
- Routes subdomains to individual services
- Handles SSL/TLS certificate renewal with certbot
- **Before adding a new service**: Add domain routing in `nginx.conf`
- Run `domain_list.sh` if you add new domains to update SSL certificates

### Authelia (Authentication)
- Runs inside nginx service
- Protects services that need login
- Configuration is in `nginx/config/configuration.yml`
- Secrets (JWT, session) in `nginx/data/authelia/secrets/`

### Actual-Budget (Personal Finance)
- Complex data structure with SQLite databases and blob files
- Special skill available: see `actual-budget/` for advanced database operations
- Data path: `actual-budget/data/user-files/`
- Note: Manual database operations require careful backup/restore

## Working with Configuration

### Environment Variables
Each service loads from `.env` file (gitignored for secrets):
```bash
# View current env
cat <service>/.env

# Set environment variable
echo "VARIABLE=value" >> <service>/.env
```

### Adding a New Service
1. Create directory: `mkdir <service-name>`
2. Add `docker-compose.yml` with service definition
3. Add routing in `nginx/nginx.conf` if service needs external access
4. If using new domain: update `nginx/domain_list.sh` and run it
5. Test: `docker compose up -d` in service directory

## Key Gotchas

- **.gitignore patterns**: Data directories, `.env` files, and `*.sqlite*` files are ignored — changes to these won't be tracked
- **Watchtower labels**: Services tagged with `com.centurylinklabs.watchtower.enable=true` auto-upgrade — check if intentional before adding
- **Shared networks**: Services on `docker_proxy_network` can communicate by hostname, but other networks are isolated
- **Docker socket access**: Some services (nginx, certbot) have access to `/var/run/docker.sock` for container management — be careful with this privilege
- **Health checks**: Some services define health checks; check `docker compose ps` to see if STATUS shows "unhealthy"

## Deployment Workflow

Typical workflow when changing a service:
1. Edit `docker-compose.yml` or configuration files
2. Test locally: `docker compose up -d && docker compose logs -f`
3. Verify service is healthy: `docker compose ps`
4. If database changes: backup existing data first with `sudo cp -r data/ data.backup-<date>/`
5. Commit changes: `git add . && git commit -m "service-name: description"`

## Useful Git Patterns

```bash
# See what changed in a service
git log --oneline nginx/

# Diff nginx config changes
git diff HEAD~1 nginx/nginx.conf

# Check which commits modified data volumes (should be none)
git log -- actual-budget/data/  # Should show nothing since data/ is gitignored
```
