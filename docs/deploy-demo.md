# Deploying Jamasp to the demo server

## Is the code mounted or volumed?

**No.** This is not like `drilling` or `datacatalog`, where nginx mounts a built
frontend directory and serves the files itself.

Jamasp ships as **three container images** with the code already inside them:

| image | what it is |
| --- | --- |
| `ghcr.io/itsmadson/jamasp-web` | Next.js **server** — it runs, it is not static files |
| `ghcr.io/itsmadson/jamasp-api` | FastAPI backend |
| `ghcr.io/itsmadson/jamasp-worker` | background jobs (scans, report builds) |

So there is **nothing to add to the nginx volume list.** nginx proxies to the web
container; it does not serve Jamasp files.

The only thing that persists is the Postgres volume `jamasp_jamasp-pgdata`. That
holds the metadata database: sources, table descriptions, approvals, saved queries
and reports. It is not your data — your databases stay where they are, and Jamasp
only ever reads from them.

To deploy a new version you pull new images and restart. You never copy code to
the server.

## 1. Files

```
/root/jamasp/
    compose.demo.yml     ← from docker/compose.demo.yml in the repo
    .env                 ← you create this, see below
```

```bash
mkdir -p /root/jamasp && cd /root/jamasp
# copy compose.demo.yml here
```

## 2. Secrets

```bash
cd /root/jamasp
cat > .env <<'ENV'
# Public URL, used for the CORS allowlist.
JAMASP_PUBLIC_URL=https://jamasp.geotajak.ir

# Host port nginx proxies to. Must be free on the server.
JAMASP_WEB_PORT=9210

# Postgres password for Jamasp's own metadata database.
JAMASP_PG_PASSWORD=CHANGE_ME

# First admin, created on startup.
JAMASP_ADMIN_EMAIL=admin@geotajak.ir
JAMASP_ADMIN_PASSWORD=CHANGE_ME

# Encrypts stored database connection strings. Losing it means every saved
# source must be re-entered.
JAMASP_SECRET_KEY=CHANGE_ME
# Signs session cookies. Changing it logs everyone out.
JAMASP_JWT_SECRET=CHANGE_ME

# At least one model provider.
JAMASP_OPENROUTER_API_KEY=
JAMASP_GAPGPT_API_KEY=
ENV
chmod 600 .env
```

Generate the two cryptographic values:

```bash
python3 -c "import base64,os;print('JAMASP_SECRET_KEY='+base64.urlsafe_b64encode(os.urandom(32)).decode())"
python3 -c "import secrets;print('JAMASP_JWT_SECRET='+secrets.token_urlsafe(48))"
```

`JAMASP_SECRET_KEY` must be 32 bytes, base64url-encoded — the command above
produces exactly that. Back both values up somewhere outside the server.

## 3. Check the port is free

```bash
ss -lntp | grep 9210 || echo "9210 is free"
```

Pick another and set `JAMASP_WEB_PORT` if it is taken. Whatever you choose must
match the `proxy_pass` port in the nginx config.

## 4. Start it

```bash
cd /root/jamasp
docker login ghcr.io          # once, if this server has never pulled from GHCR
docker compose -f compose.demo.yml pull
docker compose -f compose.demo.yml up -d
docker compose -f compose.demo.yml ps
```

The API runs migrations and seeds the admin user on first start. Watch it:

```bash
docker compose -f compose.demo.yml logs -f api
```

Check it directly before involving nginx:

```bash
curl -s localhost:9210/api/health   # {"status":"ok"}
```

## 5. nginx

Copy `deploy/nginx/jamasp.conf` to `/root/nginx_config/conf.d/jamasp.conf`,
adjust `server_name` and the port if needed, then:

```bash
docker exec nginx nginx -t      # test before reloading
docker exec nginx nginx -s reload
```

Nothing in `/root/docker-compose.yml` changes. No new volume, no new mount.

### Two things this config does that the other apps do not need

**SSE is unbuffered.** Scans and report builds stream their progress. With
nginx's default buffering the browser receives nothing until the job ends, so the
step-by-step progress would appear frozen and then jump to done.

**The API has a 600-second read timeout.** A scan of a large database and a report
that makes several model calls both run far past the default 60s. This one is from
experience: a 300-second proxy limit produced a browser error while the work
completed successfully in the background, which looks exactly like a crash.

## 6. DNS

Point `jamasp.geotajak.ir` at the server. The wildcard certificate the other
`*.geotajak.ir` apps use covers it, so `includes/ssl-geotajak.conf` needs no
change.

## 7. First run

1. Open `https://jamasp.geotajak.ir`, sign in as the admin from `.env`.
2. **منابع داده** → add a database. Test the connection before saving.
3. Run a scan. Progress streams live.
4. **بازبینی** — approve the tables. Nothing can be queried until a human approves
   it; this is deliberate and is what keeps the model inside known ground.
5. **کارگاه** — ask questions, or switch to گزارش to build a report.

## Updating

```bash
cd /root/jamasp
docker compose -f compose.demo.yml pull
docker compose -f compose.demo.yml up -d
```

Migrations run automatically on API start. The data volume is untouched.

## Security notes for a public demo

- `JAMASP_WEB_PORT` is published on all interfaces so the nginx container can
  reach it via the host IP, the same as your other apps. **Close it at the
  firewall** so only nginx reaches it:
  `ufw deny 9210` (or the equivalent on this host).
- Postgres and Redis are deliberately not published at all.
- Connect Jamasp with a **read-only database user**. It refuses to emit anything
  but SELECT, but a read-only grant means that guarantee does not rest on the
  application alone. The add-source dialog shows the SQL to create one.

### Alternative: no published port at all

Cleaner, slightly more intrusive. Put nginx on Jamasp's network and address the
container by name instead of via the host IP.

In `/root/docker-compose.yml`, add to the nginx service:

```yaml
    networks:
      - default
      - jamasp_default

networks:
  jamasp_default:
    external: true
```

Then drop the `ports:` block from the `web` service in `compose.demo.yml`, and in
the nginx config use `proxy_pass http://jamasp-web-1:3000;` in all three
locations. Nothing is exposed on the host at all.
