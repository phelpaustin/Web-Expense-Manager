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

## Moving your data from the old site

**Easiest: the app's own backup.** On the old site go to Settings → App data → *Download full backup*. On the new site register an account (do not add anything yet), then Settings → App data → *Restore a backup* and choose the file. Expenses come back with their bills as containers, plus receipts, budgets, income, recurring items, savings goals and settings. Your Expense Spaces come back too, with your own entries, and you as their only member (invite the others again).

**Exact copy of the whole database** (every account, including other people's entries in shared spaces) is the second way, below.

## Copying the whole database from Render/Supabase

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

The `backup` container writes `expense-YYYYMMDD-HHMM.sql.gz` to `BACKUP_DIR` (default `deploy/onprem/backups`) every night and deletes dumps older than `BACKUP_KEEP_DAYS`. Dumps are readable by their owner only (the folder is mode 700, files 600), since they contain every user's data and password hashes. On Linux, set `BACKUP_USER` in `.env` (see `.env.example`; run `mkdir -p backups` first) so the dumps belong to you instead of root. **Copy that folder to another disk or machine** (Time Machine, a NAS, `rsync`); a backup on the same drive does not survive a drive failure.

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
- **HTTPS:** plain HTTP is fine inside a home network or a VPN. Anything reachable from the internet needs HTTPS (a tunnel provides it). Over HTTPS (a tunnel sends `X-Forwarded-Proto: https`) nginx adds an HSTS header, so browsers then refuse plain HTTP for that address; over plain HTTP no HSTS header is sent. Before using a name over HTTPS, be sure you want it HTTPS-only: browsers remember HSTS for a year.
- **Digest endpoint:** `/api/alerts/send-digest` is blocked at nginx (it answers 404 from outside); the `digest` container calls the backend directly.

## Sign-up, and no email set up

Anyone who can reach the site can create an account. For a private instance, set `ALLOW_REGISTRATION=false` in `.env` once everyone has theirs (existing accounts keep working; new password and Google sign-ups get a 403).

If no email service is configured, verification and password-reset emails are not sent. Instead the backend writes the whole message, including its one-time link, to its log: `docker compose logs backend`. That is how you finish creating the first account without email, but it also means anyone who can read the container logs can read those links, so keep log access to yourself and set up SMTP or Resend when more people use the site.

## Seeing real visitor addresses (Docker on a Mac)

Docker on macOS (Docker Desktop, and some Colima setups) can replace the address of every device on your network with its own internal one before a request reaches the website container ([a long-standing Docker limitation](https://github.com/docker/roadmap/issues/157)). The app then treats all visitors as one: they share one sign-in rate limit (5 a minute, 60 an hour), and Settings → Account → *Sign-in activity* shows the same address for every sign-in, something like `192.168.65.1` or `172.x.x.1`. The backend logs a warning mentioning Docker the first time it sees such an address (`docker compose logs backend`).

**Check:** open the site from a second device (a phone on your Wi-Fi), then run `docker compose logs --tail 5 web`. The second field of each line is the visitor. If it is the phone's address (for example `192.168.1.23`), there is nothing to do. If it is an internal address, pick one:

- **Through a Cloudflare Tunnel** the real address arrives in a header, so it is already right: keep `TRUSTED_PROXY_COUNT=2` and check the same way.
- **Straight over the LAN:** either accept it and make the shared sign-in limit roomier by adding `RATE_LIMIT_LOGIN=20/minute;300/hour` to `.env` (then `docker compose up -d`), or put a small proxy on the Mac itself, outside Docker, where real addresses are visible. For example with Caddy (`brew install caddy`), a `Caddyfile` containing
  ```
  :8081 {
      reverse_proxy 127.0.0.1:8080
  }
  ```
  and `caddy run`, together with `WEB_BIND=127.0.0.1`, `TRUSTED_PROXY_COUNT=2`, and `FRONTEND_URL` / `CORS_ORIGINS` set to `http://<mac address>:8081`. Then check again.

## Keeping it safe

- **Put a login in front of the site** when it is reachable from the internet (Cloudflare Access with only your email allowed). The app has a login of its own, but it lets anyone register; Access keeps strangers from even seeing it.
- **Let only the tunnel reach it.** With a Cloudflare Tunnel or Tailscale running on the same machine, set `WEB_BIND=127.0.0.1` in `.env` and run `docker compose up -d`. Other devices on your Wi-Fi can then no longer bypass the login by opening `http://<mac-mini>:8080`.
- **Protect `.env`:** `chmod 600 deploy/onprem/.env`. It holds the database password, `SECRET_KEY` and email password. Never commit it or paste it anywhere. Changing `SECRET_KEY` signs everybody out.
- **Cloudflare tunnel token:** it is a password for your tunnel. If it ever leaks, open the tunnel in Cloudflare, roll the token, and run the `cloudflared service install` command again with the new one.
- **Disk encryption:** turn on FileVault (System Settings → Privacy & Security) so a stolen Mac mini reveals nothing. FileVault asks for a password after a power cut, so the site stays down until you unlock it; decide which matters more to you.
- **Backups:** copy `deploy/onprem/backups` to another machine or cloud storage, and keep them encrypted if they leave your home (they contain every expense). Test a restore once.
- **Updates:** every few weeks run `git pull`, then `docker compose build --pull` and `docker compose up -d`. This also picks up new versions of the PostgreSQL, Python and nginx base images. Keep macOS updated.
- **Strong passwords:** a long, unique password for the app (12 characters or more is enforced) and for your Cloudflare account, with two-step verification turned on for Cloudflare.
- The database is not published on any port: only the other containers can reach it.

## Who is signing in and visiting

Four places, from most to least specific:

1. **In the app:** Settings → Account → *Sign-in activity* lists recent sign-ins and failed password attempts on your account (time, device, address), and warns when there were failures since your last sign-in. Kept 180 days.
2. **Cloudflare Access log:** every attempt to get through the Access login, with the email, address, country and allowed or denied (Zero Trust dashboard → Logs → Access). This is where strangers show up.
3. **Cloudflare analytics:** the domain's *Analytics* page shows requests, visitors, countries and blocked threats over time; *Security* shows what Cloudflare blocked.
4. **The website's own access log**, one line per request with the real visitor address and country, the path without the query string, the status code and the browser:
   ```bash
   docker compose logs --since 24h web                     # everything in the last day
   docker compose logs -f web                              # follow live
   docker compose logs --no-log-prefix --since 24h web | awk '{print $2}' | sort | uniq -c | sort -rn | head   # busiest addresses
   docker compose logs --no-log-prefix --since 24h web | grep '/api/auth/login" 401'                        # failed logins
   ```
   Logs are rotated (about 50 MB per service), so they go back a few days to weeks.
   The address and country come from Cloudflare's headers only when the request arrives through your tunnel (from this machine or Docker's own networks). A device on your network that sends those headers itself is logged under its own address with country `-`, so nobody can plant a fake visitor in the log. If Docker on a Mac hides your devices' addresses, a device on your network looks like the tunnel too (see the section above), so keep `WEB_BIND=127.0.0.1` whenever you use a tunnel.

## Useful commands

```bash
docker compose logs -f backend     # follow the backend log
docker compose restart backend     # restart one service
docker compose down                # stop everything (data is kept in the db-data volume)
docker compose down -v             # stop and DELETE the database volume
```
