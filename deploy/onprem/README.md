# Self-hosting with Docker (Mac mini, Linux server, any machine with Docker)

One command starts the whole app on your own machine: PostgreSQL, the backend, the website, a daily alert-email job and a nightly backup. Nothing here changes how the app runs on Render and Vercel.

```
browser ──► web (nginx, port 8080) ──┬─ /      the React site
                                      └─ /api  ──► backend (FastAPI) ──► db (PostgreSQL)
digest  ── daily 07:00 UTC ──► backend            backup ── nightly 02:00 UTC ──► ./backups
```

## First start

1. Install Docker Desktop (or OrbStack/Colima on a Mac) and check that `docker compose version` works.
2. `git clone` the repository on the machine, then:
   ```bash
   cd deploy/onprem
   cp .env.example .env
   ```
3. Edit `.env`:
   - `POSTGRES_PASSWORD` and `SECRET_KEY` (`openssl rand -hex 32`) — required.
   - `FRONTEND_URL` and `CORS_ORIGINS` — the exact address you type in the browser, e.g. `http://192.168.1.50:8080`, no trailing slash.
   - Email settings (SMTP or Resend) if people sign up with a password.
4. Start it:
   ```bash
   docker compose up -d --build
   docker compose ps          # db, backend and web should be "running"/"healthy"
   ```
5. Open `http://<machine address>:8080` and create your account. Database migrations run on their own at backend start-up.

## Moving your data from Render/Supabase

On the old setup, dump the database (Supabase: Project Settings → Database → connection string), then load it into the new one **before** first use:

```bash
pg_dump --no-owner --no-privileges "<old DATABASE_URL>" > old.sql
docker compose up -d db
docker compose exec -T db psql -U expense expense < old.sql
docker compose up -d
```

If you uploaded receipts to Supabase Storage, they stay there only while `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are still set in `.env`; without them, new receipts are stored in the database (and are therefore in the backups).

## Updating

```bash
git pull
cd deploy/onprem
docker compose up -d --build
```

## Backups and restore

The `backup` container writes `expense-YYYYMMDD-HHMM.sql.gz` to `BACKUP_DIR` (default `deploy/onprem/backups`) every night and deletes dumps older than `BACKUP_KEEP_DAYS`. **Copy that folder to another disk or machine** (Time Machine, a NAS, `rsync`); a backup on the same drive does not survive a drive failure.

Restore into an empty database:

```bash
docker compose stop backend digest
docker compose exec -T db psql -U expense -c "DROP DATABASE expense;" postgres
docker compose exec -T db psql -U expense -c "CREATE DATABASE expense;" postgres
gunzip -c backups/expense-YYYYMMDD-HHMM.sql.gz | docker compose exec -T db psql -U expense expense
docker compose start backend digest
```

Test a restore once before you need it.

## Daily alert emails

Set `CRON_SECRET` in `.env` (and working email settings). The `digest` container then calls the backend every day at 07:00 UTC; the GitHub workflow is not needed. Without `CRON_SECRET` the container idles.

## Mac mini checklist

- **Keep it awake:** System Settings → Energy → turn on "Prevent automatic sleeping when the display is off" and "Start up automatically after a power failure".
- **Start after a reboot:** Docker Desktop only starts when someone logs in. Enable automatic login (System Settings → Users & Groups → Automatic login) and in Docker Desktop settings turn on "Start Docker Desktop when you sign in". The containers use `restart: unless-stopped`, so they come back by themselves once Docker is up. (OrbStack and Colima can start without a login.)
- **Fixed address:** give the Mac mini a DHCP reservation in your router, or a static IP, so `FRONTEND_URL` stays correct.
- **Firewall:** allow incoming connections for Docker if macOS asks.
- **Outside the home network:** do not forward port 8080 to the internet. Use a VPN such as Tailscale (use the Tailscale address or name in `FRONTEND_URL`/`CORS_ORIGINS`), or a Cloudflare Tunnel pointing at `http://localhost:8080`, which also gives you HTTPS. With a tunnel, set `TRUSTED_PROXY_COUNT=2`.
- **HTTPS:** plain HTTP is fine inside a home network or a VPN. Anything reachable from the internet needs HTTPS (a tunnel provides it).

## Useful commands

```bash
docker compose logs -f backend     # follow the backend log
docker compose restart backend     # restart one service
docker compose down                # stop everything (data is kept in the db-data volume)
docker compose down -v             # stop and DELETE the database volume
```
