# Excalidraw

Self-hosted Excalidraw whiteboard with **live collaboration** and **persistent
scene storage**, for architecture prototyping and homelab documentation diagrams.

Everything is served from a single domain, **`https://draw.joshowen.uk`**, behind
Authelia. nginx splits traffic across three containers:

| Path | Container | Purpose |
|------|-----------|---------|
| `/`           | `excalidraw` (nginx SPA)              | the app |
| `/socket.io/` | `excalidraw-room`                    | real-time collaboration relay |
| `/api/v2/`    | `excalidraw-storage` (SQLite/Keyv)   | persistent "save to link" scenes |

Routing lives in `nginx/nginx.d/nginx.conf` (the `draw.joshowen.uk` server block).

## How collaboration works

**Share → "Live collaboration"** in the app. Excalidraw generates a link with the
room key in the URL fragment (`#room=<id>,<key>`). Share it; everyone editing sees
changes live.

`excalidraw-room` is a **Socket.IO relay only** — it forwards end-to-end-encrypted
diffs between connected clients. The key is in the URL fragment and never reaches
the server, so the relay can't read your drawings, and it keeps nothing on disk.
When the last person leaves a room, that room's live state is gone.

## How persistence works

Three layers, in order of durability:

1. **Local canvas** — auto-saved to the browser's localStorage (per browser).
2. **Server-side scenes** — **Share → shareable link** POSTs the encrypted scene
   to `excalidraw-storage`, which writes it to SQLite on the `./data` volume and
   returns a `#json=<id>,<key>` link. These persist across browsers/devices and
   survive container restarts. This is explicit save-to-link, **not** auto-save of
   every edit.
3. **Files** — **Menu → Save to… / Export** writes `.excalidraw` (JSON). Best for
   documentation diagrams you want versioned in git.

> Collaborative *image* files (binary pastes inside a live session) would need a
> Firebase config in the official frontend; that edge case is not wired up. Shapes,
> text, arrows, and link/file persistence all work.

### Storage backend

`excalidraw-storage` is `kiliandeca/excalidraw-storage-backend` (Keyv). We use
`STORAGE_URI=sqlite:///data/excalidraw.sqlite`, so the entire store is one file
under `./data`. To move onto a shared Postgres later, just change `STORAGE_URI`
to `postgres://…` — no other changes needed.

**Permissions gotcha:** the container runs as uid **1000**, so the host `./data`
dir must be owned by 1000 or SQLite fails with `SQLITE_CANTOPEN`. If you wipe and
recreate `./data`, re-run: `sudo chown -R 1000:1000 data`.

## The build-time URL patch (important)

The official `excalidraw/excalidraw` image bakes its backend URLs into the JS
bundle **at build time**:

- collab/room  → `https://oss-collab.excalidraw.com`
- scene GET    → `https://json.excalidraw.com/api/v2/`
- scene POST   → `https://json.excalidraw.com/api/v2/post/`

Rather than maintain a custom build, the compose `entrypoint` sed-patches the built
assets on every start to point at our own stack (collab → `https://draw.joshowen.uk`,
scenes → `https://draw.joshowen.uk/api/v2/scenes/`; note the storage backend's
route is `/api/v2/scenes`, not `/post/`). The patch re-runs each start, so
Watchtower image updates are picked up automatically.

To change the domain, edit `VITE_APP_WS_SERVER_URL` in `docker-compose.yml`.

If the share spinner hangs forever: hard-refresh (stale cached bundle), then check
`docker compose logs excalidraw` for the `collab -> … scenes -> …` line.

## Diagrams (`diagrams/`)

Version-controlled `.excalidraw` scenes live in `excalidraw/diagrams/`. To open one
in the app: hamburger menu (top-left) → **Open** and pick the file, or just
drag-and-drop it onto the canvas. The file must be on the machine running the
browser, so `git pull` first if you're not on the server. Once open, **Share →
shareable link** persists it server-side (the browser does the encryption natively).

- `homelab-edge.excalidraw` — Hetzner edge box: services, docker networks,
  nginx→authelia→upstream flow, storage mounts, and the WireGuard-to-home tunnel
  with a placeholder zone for the homelab server.

## AI agent read/write (stretch goal — not built yet)

`.excalidraw` files are a flat JSON array of elements — no SDK needed. To let an
agent read/write diagrams, decide on a canonical store first (a git repo of
`.excalidraw` files is simplest), then point the agent at that path. This is
independent of the live-collab relay and the SQLite link store above.

## Deploy

```bash
cd excalidraw
sudo chown -R 1000:1000 data   # first time only (storage runs as uid 1000)
docker compose up -d
docker compose ps
```

New domains need a cert — from `nginx/`, run `./domain_list.sh` (already includes
`draw.joshowen.uk` and pins `--cert-name joshowen.uk-0001`), then
`docker exec nginx nginx -s reload`.
