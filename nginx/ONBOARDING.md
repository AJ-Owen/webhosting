# User Onboarding

How to give someone access to `*.joshowen.uk`.

Authelia is the front door and the source of truth for *who exists*. Where a
service can consume Authelia's identity it does — Calibre-Web and Paperless
both log people in straight from the `Remote-User` header, no second password.
The rest keep their own account lists because they support nothing better.

---

## How access is scoped

`config/configuration.yml` → `access_control`. Rules are **first match wins**,
so anything scoped to specific people sits *above* the `*.joshowen.uk`
catch-all. Current shape:

| Rule | Domains | Who gets in |
|---|---|---|
| bypass | `auth`, `ntfy` | everyone (ntfy has its own auth) |
| admins-only | `dockge`, `obsidian`, `debrid` | `group:admins` — everyone else denied |
| named-users | `docs` (Paperless) | `user:josh`, `user:katie` — everyone else denied |
| catch-all | `*.joshowen.uk` | any authenticated user, 2FA |

Groups today: **josh** is in `admins`; brett, cindy, dan, katie are in `users`.

**Each subject-gated allow is followed by a paired `deny` for the same
domains.** This is not redundant. A rule carrying a `subject:` only matches
users who satisfy that subject — without the `deny`, everyone else simply fails
to match and falls through to the wildcard, which lets them in. The pair is
what actually scopes access.

So: **adding a user grants everything except the domains above.** They land in
books, budget, tools, draw, pdf, uptime, beszel, assistant on first login.

### Verifying rules before you trust them

Authelia can simulate a request. Always do this after editing rules:

```bash
docker exec authelia authelia access-control check-policy \
  --config /config/configuration.yml \
  --url https://dockge.joshowen.uk/ --username dan --groups users
```

It prints which rule number matched and the resulting policy.

---

## Service matrix

| Domain | Upstream | Authelia | Second account needed? |
|---|---|---|---|
| `books.joshowen.uk` | calibre-web-automated:8083 | all users | **Yes — must pre-create**, username must match exactly |
| `books-request.joshowen.uk` | cwa-book-downloader:8084 | all users | Shares Calibre-Web's `app.db` — covered above |
| `docs.joshowen.uk` | paperless:8000 | **josh, katie only** | No — auto-provisioned from `Remote-User` |
| `pdf.joshowen.uk` | pdf_tool:8080 | all users | Yes — Stirling's own login (`/account`) |
| `debrid.joshowen.uk` | rdtclient:6500 | **admins only** | Yes — rdtclient's own login |
| `dockge.joshowen.uk` | dockge:5001 | **admins only** | Yes — own accounts, no SSO support |
| `obsidian.joshowen.uk` | obsidian-remote:8080 | **admins only** | No — Authelia is the only gate |
| `beszel.joshowen.uk` | beszel:8090 | all users | Yes — own accounts (supports OIDC, not wired up) |
| `uptime.joshowen.uk` | uptime-kuma:3001 | all users | Yes — own accounts, no SSO support |
| `budget.joshowen.uk` | actual-budget:5006 | all users | Shared server password, no per-user accounts |
| `tools.joshowen.uk` | it-tools:80 | all users | No |
| `draw.joshowen.uk` | excalidraw stack | all users | No |
| `assistant.joshowen.uk` | assistant | all users, except `/webhook` | No |
| `ntfy.joshowen.uk` | ntfy:80 | **bypassed** | Yes — ntfy's own auth, see `ntfy/README.md` |
| `ha.joshowen.uk` | WireGuard → home HA | **none** | Home Assistant's own login |
| `joshowen.uk`, `dogdaysadventure.xyz` | static webserver | none | Public sites — nothing to do |

Two vhosts carve out unauthenticated paths for machines that can't do a browser
login: `assistant.joshowen.uk/webhook` (own bearer token, rate-limited) and
`beszel.joshowen.uk/api/beszel/agent-connect` + `/api/realtime` (restricted to
the homelab WAN IP). Neither is user-facing.

---

## Adding a user

### 1. Create the Authelia account

`config/` is a **bind mount** (`./config:/config`) — the files in this repo
*are* the live Authelia config. There is no staging copy.

Generate a hash (omit `--password` so it prompts and stays out of shell
history):

```bash
docker exec -it authelia authelia crypto hash generate argon2
```

Append to `config/users_database.yml`. Use a **lowercase, short username** — it
becomes the identity every downstream app sees:

```yaml
    firstname:
        password: $argon2id$v=19$m=65536,t=3,p=4$...
        displayname: First Last
        email: their.real@email.com
        groups:
            - users        # use `admins` for infra access (dockge/obsidian/debrid)
        disabled: false
```

The `email:` must be a real address they can read — password reset and TOTP
enrolment both go through it.

Recommended: set a throwaway password and have them use **Reset password** at
`auth.joshowen.uk`, so you never handle their real one.

### 2. Validate, then restart Authelia

The file backend has no `watch:` key, so changes are only read at startup. A
config that won't parse means Authelia doesn't come back — and every protected
vhost fails its `auth_request` while it's down. So validate first:

```bash
docker exec authelia authelia validate-config
cd nginx && docker compose restart authelia
```

Verify in a **private window while keeping your current session open**, so you
still have a working login if something's wrong.

### 3. Create the Calibre-Web account (if they get books)

Calibre-Web's reverse-proxy login **does not auto-provision**. It reads
`Remote-User` and looks for an existing account with that exact username; no
match means no login.

Create it at `https://books.joshowen.uk/admin/user` — not by editing `app.db`,
which has live WAL files and cached app state.

- **Username must equal the Authelia key exactly**, lowercase.
- The form requires a password; it is never used under header auth. Put in
  anything random.
- Set upload/download/edit permissions while you're there.

### 4. Paperless — nothing to do, but access is opt-in

Paperless auto-creates the account on first visit. Because of that, access is
restricted **by name** in `access_control`. To grant someone docs access, add
them to the `subject:` list on the `docs.joshowen.uk` rule and restart Authelia:

```yaml
    - domain: docs.joshowen.uk
      policy: two_factor
      subject:
        - "user:josh"
        - "user:katie"
        - "user:newperson"    # <- add here
```

They'll be provisioned as a normal (non-staff) user seeing zero documents.
Paperless documents are visible per-owner, but **documents with no owner are
visible to every authenticated user** — all 393 currently have owners; if that
ever stops being true, this rule is what's protecting them.

### 5. Any other per-service accounts

From the matrix — only for what they actually need. `dockge`, `obsidian` and
`debrid` are denied at the proxy unless they're in `admins`.

### 6. Walk them through first login

1. Go to any protected URL, e.g. `https://books.joshowen.uk`.
2. Redirected to `auth.joshowen.uk` — username + password. (Login is
   case-insensitive and accepts the email address too — `search:` in
   `configuration.yml`.)
3. Policy is `two_factor` everywhere, so they're prompted to **enrol TOTP**.
   Authelia emails an enrolment link via the GMX SMTP notifier.
4. **Checkpoint: confirm that email actually arrived.** This is the step most
   likely to fail silently. If it doesn't:
   ```bash
   docker compose logs authelia | grep -i "smtp\|notif"
   ```
   Check the address in `users_database.yml`, and that `GMX_APP_PASSWORD` is
   set in `nginx/.env`.
5. They scan the QR in their authenticator app, then land on the service.

### 7. Back up the user database

`users_database.yml` is **gitignored** (`.gitignore:4`) — it holds password
hashes, so there's no version history and no safety net:

```bash
sudo cp -p nginx/config/users_database.yml \
   nginx/config/users_database.yml.bak-$(date +%Y%m%d-%H%M%S)
```

Commit only if you changed `configuration.yml` or `nginx.d/nginx.conf` — those
*are* tracked.

---

## Removing a user

1. Set `disabled: true` on their entry in `users_database.yml` (or delete the
   block).
2. `docker compose restart authelia`. Sessions are in-memory (no
   `session.redis`), so the restart also drops their live session immediately —
   at the cost of logging everyone else out. Otherwise it survives up to
   `expiration: 12h` / `inactivity: 90m`.
3. Delete their Calibre-Web account, their Paperless account (it does *not*
   disappear on its own), and any other per-service accounts. Those are
   independent and would still work if a service were ever reachable without
   the proxy.

---

## Gotchas

- **A denied user gets a bare 403, not a login page.** `snippets/authelia.conf`
  only maps `error_page 401` to the Authelia redirect; a `deny` policy returns
  403 from the auth subrequest and nginx passes it straight through. This is
  correct behaviour, not a broken proxy.
- **`users_database.yml` is rewritten by Authelia itself** on password reset,
  and it's gitignored so git won't warn you. Always re-read the current file
  before editing; never paste in an older copy or a `.bak` or you'll silently
  roll back someone's password.
- **Header auth means container access is impersonation.** Anything that can
  reach `calibre-web-automated:8083` or `paperless:8000` on
  `docker_proxy_network` can become any user by setting `Remote-User`. Never
  publish those ports to the host or LAN.
- **fail2ban on the edge box bans across all services.** If a new user can't
  reach anything at all, check the ban list before debugging the proxy.
- **Regulation**: 3 failed logins in 2 minutes = 60 minute ban.
- **Usernames are case-sensitive downstream.** Authelia login is
  case-insensitive, but it forwards the canonical (lowercase) key, and
  Calibre-Web and Django both match it exactly. Keep everything lowercase.

---

## Still duplicated

- **Beszel** supports OIDC and Authelia can act as an OIDC provider
  (`identity_providers.oidc` — needs a client registration, HMAC key and
  secrets). Not wired up; the biggest remaining win.
- **Dockge, Uptime Kuma, rdtclient, Stirling** support neither header auth nor
  OIDC. They stay manual — an argument for keeping the first three admin-only.
- **Actual Budget** has no user model at all, just one shared server password.
