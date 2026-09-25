# Manager

Operations console and usage reporting for
[SIPMediaGW](https://github.com/Renater/SIPMediaGW).

Two functions behind one interface and one sign-in:

- **Supervision** — live state of the registered gateways: free slot, waiting
  for a call, IVR, in conference; endpoint, meeting, platform, call duration,
  pairing code. Full-text search and click-to-copy on the values that matter
  when troubleshooting (SIP URI for Homer, gateway address for SSH).
- **Usage report** — volume over a period: calls, communication hours, peak
  concurrency, breakdown by organisational unit and by platform, monthly series
  with trend and running total, session outcomes.
- **Pool consumption** — VM-hours by state (free, idle, IVR, in conference) and
  the share actually serving a conference. The VM is what is billed: a gateway
  reporting `free` is a VM that exists with its container stopped. No figure
  in euros: a VM-hour price leaves out the fixed infrastructure and the
  services around it, and was read as the cost of the service. Whoever holds
  the full cost model multiplies the hours.
- **Call log** — every call over an explicit window (date and time, presets
  from "today" to "last 30 days"), searchable by endpoint, meeting, SIP URI,
  unit or Call-ID, paginated; a click opens the full detail pushed by the
  gateway, media statistics included.
- **SIP trace** — one click from a call to its trace in Homer, when a Homer is
  deployed (`HOMER_BASE` set). Exact by Call-ID from the call log; by calling
  endpoint from the supervision, where the live state carries no Call-ID.

## Two metrics, two sources

Call history cannot cost the pool: a pre-provisioned gateway that waits for
hours and never receives a call pushes nothing. So the Manager uses both:

| Question | Source | Why |
|---|---|---|
| How many calls at once? How long? Which platform, which unit? | end-of-call pushes (`calls`) | exact per-call facts, IVR-only sessions included |
| How many gateways were running, and for how long? | `pool_samples`, one reading of `/admin/statuses` per minute | the proxyAPI sees every gateway from `/register` to its disappearance, calls or not |

Gateway-hours are the integral `sum(count x interval)`. A gap in samples
(Manager down) counts for nothing: it under-estimates rather than invents.

## Where it sits

    SIP endpoints ──▶ Kamailio ──▶ gateways ──▶ conferencing platforms
                                      │  │
                  /register, /status   │  └── logParse: end of call (LOG_PUSH_URL)
                                      ▼                        │
                                  proxyAPI ◀── relay ── Manager ──▶ PostgreSQL
                                  (Redis)      /api/gateways         │  POST /ingest/calls
                                                                     ▼
                                                        browser (session, no token)

The Manager never talks to the gateways: it reads the state of the pool through
the proxyAPI and receives call history pushed at the end of each call. The
proxyAPI admin token and the PostgreSQL credentials stay server-side; the
browser only ever holds a session cookie.

It replaces an earlier setup where Traefik carried both the authentication and
the admin-token injection. Those two responsibilities now live in the
application, which makes a shared TLS reverse proxy optional again.

## Quick start

    ./tools/init-env.sh         # fills the empty secrets of .env, prints the next steps
    docker compose up -d --build
    # console: http://<host>:8200/

`.env` is in the repository with the defaults of `.env.example` and no secret.
`tools/init-env.sh` generates `MANAGER_SESSION_SECRET`, `INGEST_TOKEN` and the
database password, never overwrites a value, and marks the file skip-worktree
so that a filled `.env` stays out of git. `PROXYAPI_ADMIN_TOKEN` is the
proxyAPI's own `PROXY_ADMIN_TOKEN`: copy it by hand. The first sign-in uses the
`admin` account and `MANAGER_DEFAULT_PASSWORD`: change it at once.

On the gateway side, to feed the reporting database:

    LOG_PUSH_URL=http://<manager>:8200/ingest/calls     # lab: the port is published
    LOG_PUSH_TOKEN=<INGEST_TOKEN>

In production the port is published on `MANAGER_BIND`: the loopback when the
reverse proxy is on the same host (the pushes then go through it, which must
relay `/ingest`), the LAN address when the gateways push directly (see
Production).

## Routes

| Route | Who | Purpose |
|---|---|---|
| `GET /` · `/static/*` | anyone | console (front end) |
| `GET /health` | anyone | liveness and database readiness (container healthcheck, page banner) |
| `POST /auth/login` · `POST /auth/logout` · `GET /api/me` | anyone | session: sign in (JSON only), sign out (ends every session of the account), who am I |
| `POST /api/account/password` | signed in | one's own password |
| `GET /api/gateways` | signed in | live pool, states derived server-side |
| `GET /api/reporting/summary` · `monthly` · `platforms` · `org-units` · `concurrency` | signed in | Usage: headline figures, monthly series, platforms, units, daily peaks |
| `GET /api/reporting/outcomes` · `video-states` · `ivr-reasons` · `recomputes` | signed in | Quality: outcomes, picture received, close reasons, recomputation log |
| `GET /api/reporting/pool-profile` · `pool-pressure` · `pool-hours` · `pool-period-hours` · `concurrency/hourly` | signed in | Capacity: hourly profile, tight slots, VM-hours, sizing |
| `GET /api/reporting/calls` · `calls/{id}` · `calls/{id}/media` · `calls/{id}/raw` | signed in | Journal: calls over a window, one call, its media statistics, the payload as pushed |
| `GET/POST /api/users` · `PUT/DELETE /api/users/{name}` · `POST /api/users/{name}/password` · `GET /api/users/audit` | admin | accounts |
| `GET/POST /api/org-units` · `PUT /api/org-units/{code}` · `POST/PUT/DELETE /api/org-unit-rules[/{id}]` · `PUT /api/org-unit-rules-order` · `POST /api/org-unit-rules/test` · `POST /api/org-units/recompute` | admin | units and the rules that classify callers |
| `GET /api/audit` | admin | audit trail: accounts and units, filtered and paginated |
| `POST /ingest/calls` | gateways | end-of-call intake (own bearer token, no session) |

## Layout

    app.py              entry point: sessions, security headers, same-origin writes, routers, front end
    auth.py             single authorisation point: passwords, throttle, sessions (dependency of every /api route)
    origin.py           refuses writes coming from another origin of the same site
    users.py            the account table and its audit, one transaction per change
    db.py               PostgreSQL pool, session time zone, errors logged and neutralised
    sampler.py          background task: pool occupancy sample every POOL_SAMPLE_INTERVAL seconds
    homer.py            Homer deep links (exact by Call-ID, by room, by endpoint); HOMER_FLAVOR selects the URL shape
    sources.py          registry of external APIs (proxyAPI only for now)
    requestid.py        a request id on every log line and response
    api/
      park.py             live pool relay, operational state derived server-side
      periods.py          periods, windows, the scope of Usage and Quality (user calls, units)
      usage.py            summary, monthly series, platforms, units
      quality.py          outcomes, video states, close reasons, recompute log
      pool.py             hourly profile, pressure, VM-hours, sizing
      calls.py            call search and detail
      users.py            own password, account administration
      org_units.py        units, classification rules, replay over the history
      audit.py            the audit trail of accounts and units
    ingest/
      mapping.py          logParse payload -> columns (no database dependency, tested alone)
      router.py           POST /ingest/calls: token, size cap, transactional insert
    db/                 SQL schema, applied in the order of db/apply_order.txt
    deploy/traefik/     an example of the reverse proxy rules
    brand/              logo and tab icon: SIPMediaGW's, and the deployment's (out of git)
    front/
      index.html          shell: sign-in, top bar, navigation, view container
      views/*.html        one fragment per view (supervision, report, quality, capacity, calls,
                          account, users, orgunits, audit)
      css/                base (tokens, typography), layout, components, print
      js/main.js          bootstrap: session, navigation, view loading, branding
      js/api.js           HTTP access, parallel reads     js/i18n.js       fr/en dictionaries
      js/format.js        formatting, esc()               js/prefs.js      stored preferences
      js/ui.js            toast, copy, dialogs, months    js/charts.js     inline SVG charts
      js/datepicker.js    calendar and date windows       js/platforms.js  connector names and icons
      js/journal-link.js  links from Quality to the Journal
      js/password.js      password rules shown while typing
      js/views/*.js       one module per view, each with mount() and unmount()
    tools/              migrate, backup, restore check, account rescue, backfill, demo data,
                        tests, lint, export for review
    tests/              pytest suite (fixtures/*.json are captured calls); e2e/ needs a browser

Adding a view means: a fragment in `front/views/`, a module in `front/js/views/`,
an entry in `VIEWS` and a button in the navigation.

## Configuration

Every variable the code reads is in `.env.example`, with its default and what
it does. An unset secret closes the door, it never opens it: an empty
`INGEST_TOKEN` disables intake, an empty `PROXYAPI_ADMIN_TOKEN` leaves the
supervision empty.

The service's name, tagline, logo and tab icon belong to the deployment, as
interact's do (its `brand.js`): `MANAGER_BRAND_NAME`, `MANAGER_BRAND_TAGLINE`,
and `MANAGER_BRAND_LOGO` / `MANAGER_BRAND_FAVICON`, file names in `brand/` —
the only two files of that directory served (`/brand/<name>`). `.env.example`
names SIPMediaGW's own, shipped in `brand/`; a deployment adds its files there
(kept out of git). See `brand/README.md`.

The tools read their own variables, all with defaults:

| Variable | Default | Read by |
|---|---|---|
| `PG_CONTAINER`, `PG_USER`, `PG_DB` | `postgres`, `gw_manager`, `gw_manager` | migrate.sh, backup.sh, restore-check.sh |
| `PG_SUPERUSER`, `RESTORE_DB` | `root`, `gw_manager_restore` | restore-check.sh |
| `BACKUP_DIR`, `KEEP_INTRADAY_HOURS`, `KEEP_NIGHTLY_DAYS` | `/var/backups/gw_manager`, 48, 30 | backup.sh |
| `PG_EXEC` | `docker exec -i $PG_CONTAINER` | backup.sh, restore-check.sh (the tests replace it) |
| `DATABASE_URL_TEST` | unset: database tests skip | tests |

## Homer integration

Optional. With `HOMER_BASE` unset, no trace button is ever shown. The URL shape
was validated empirically on Homer 7 (homer-app 1.5.20), including by negative
control — an impossible value must return zero rows, because an unrecognised
filter name is silently ignored by Homer and would show every call in the
window. Three filters are in use: `callid` (array, exact),
`data_header.to_user` (room) and `data_header.from_user` (calling endpoint).
`HOMER_FLAVOR=v11` switches to the Homer 11 URL shape; `HOMER_RETENTION_DAYS`
hides the button for calls older than the capture retention.

## Development loop

| Changed file | What to do |
|---|---|
| `front/**` (html, css, js, icons) | nothing, refresh (mounted volume; the page is `no-store`, the assets `no-cache`, revalidated on every load) |
| `*.py` | nothing with `MANAGER_RELOAD=--reload`, otherwise `docker compose restart manager` |
| `.env`, `docker-compose.yml` | `docker compose up -d` |
| `requirements.txt`, `Dockerfile` | `docker compose up -d --build` |

## Accounts and roles

Two roles. `admin` writes (accounts, units and the rules that classify
callers); `operator` reads. Accounts live in the database
(`manager_users`) and are managed from Settings by an administrator: create
with a role and an initial password (to be changed at first sign-in), reset
a password, change a role, disable and re-enable, delete (`user_audit` keeps
every line naming a deleted account). Everyone changes their own password from
"My account". `MANAGER_PASSWORD` and `MANAGER_OPERATORS` are no longer read;
the console names them at startup while they are still in `.env`.

On an empty table the first sign-in creates `admin` with
`MANAGER_DEFAULT_PASSWORD` (`manager123$`), to be changed at once.
`PASSWORD_MIN_LENGTH` (11) is the only password rule, as the ANSSI advises:
length over composition. A password change, a role change, a lock-out or a
sign-out ends every other session of the account: the cookie is signed, not
stored, so a copy of it would otherwise outlive the sign-out. A session also
ends `MANAGER_SESSION_HOURS` (10) after sign-in, however busy — the cookie is
re-issued on every response, and the park view polls.

Every account change from the console is written together with its line in
`user_audit`, in one transaction: a refused request writes nothing.

Writes (POST, PUT, PATCH, DELETE) are refused with 403 when the browser says
they come from another origin (`Sec-Fetch-Site`, `Origin`): interact and Homer
share the console's site, so `SameSite=Lax` alone lets their pages post with
the administrator's cookie. `/ingest` has its own token and is not checked.
A wrong password is logged with the name tried and the address.

When the console cannot help (the only administrator forgot the password):

    docker compose exec manager python tools/user.py reset admin

Accounts from ProConnect will carry `source = proconnect` and no password
here; the local `admin` stays as the way in when the identity provider is
not. Each administrator sign-in is logged as a warning.

## Static checks

    docker run --rm -v "$PWD:/repo:ro" -w /repo --entrypoint sh gw-manager-tests tools/lint.sh

Ruff (bugs, not style), mypy (permissive; the strict flags are commented in
`pyproject.toml` to be turned on per module) and pip-audit on the runtime
dependencies. Build the test image first: `./tools/test.sh` does.

## Database

    docker exec -i postgres psql -U <admin> -d postgres < db/bootstrap.sql
    # Order matters: db/apply_order.txt lists the files in dependency order,
    # which is not alphabetical order. The script reads it; --dry-run lists.
    ./tools/migrate.sh

`db/org_units.sample.sql` shows how calls are attached to organisational units;
the real rules belong to the deployment, not to this repository.

## What is counted where

Usage and Quality count **user calls**: recording and streaming sessions
(`main_app`) hold a gateway but carry no caller, so they count in Capacity
(the pool) and never in the usage tiles, charts, platforms, units, outcomes or
video states — one rule, `is_user_call()`, read by every one of those figures.
The Journal lists every session; its exact filters (outcome, video, close
reason — the links from Quality) keep to user calls, so a Quality figure and
the list it opens agree. The concurrency peak of the summary is swept over the
period's calls, units included.

## Reading the capacity views

**What costs is the VM, not the container.** The state vocabulary says so:
`created` is a VM provisioned whose container has been stopped, `deleted` is a
VM torn down. A gateway reporting `free` is therefore a VM that exists and is
billed — it simply is not running anything.

| State | VM | Container | Billed | Serves |
|---|---|---|---|---|
| `free` | up | stopped | yes | no |
| `idle` | up | running | yes | no |
| `ivr` | up | running | yes | yes |
| `in_call` | up | running | yes | yes |

- **provisioned** = `free + idle + ivr + in_call` — the cost basis. This is the
  only gateway-hours figure the Manager publishes: the earlier pair of views
  counting running containers was removed, because two answers to "what did the
  pool cost" is worse than one imperfect answer.
- **busy** = `ivr + in_call` — what is served.
- **spare** = `free + idle` — provisioned and serving nothing, the lever.
- **running** = `idle + ivr + in_call` — warm containers, a readiness figure.
  Never the denominator of utilisation: computed against it, the rate flatters
  the result by ignoring the VMs that were up with nothing on them.

`pool_profile` averages say what a slot cost, the peak and p95 say whether it
sufficed: an hour averaging two gateways but peaking at nine has been sized for
nine.

The console reads these through `<view>_between(since, until)`: one row per
day type and hour over the whole period, however many months it spans. The
views themselves keep one row per month, for reading by hand and for the
restore check.

`pool_pressure` reports two degrees of tightness. `no_spare` is nothing at all
left — no warm container, no provisioned VM — so a caller waits for a VM to be
created. `cold_start` is a free VM but nothing warm, where the call is taken in
the time a container starts. Neither is a refusal, both justify raising a floor.

`monthly_pool_hours` publishes `coverage_pct` next to the hours: a Manager that
was down produces no samples, and the hours it missed are simply absent. A month
at 80 % coverage is not a month with fewer gateway hours.

Out of scope: the scaler's planned floor (`unlockedMin`, `maxGw`, `loadMax`)
lives in `deploy/scaler/config/scaler.json` and is not reachable from here.
These views say what happened, not whether it matched the plan — that comparison
waits for the scaler to expose an API.

## Reclassifying history

Two rules are applied at ingestion and can be replayed over the whole history:

    SELECT * FROM recompute_outcomes('added Connection reset by peer to the whitelist');
    SELECT * FROM recompute_org_units('rule 12 added');

Both return the rows examined and the rows that actually changed, and both write
to `recompute_log` — visible on `GET /api/reporting/recomputes`. That trail is
what lets a gap between a published slide and the tool be explained: the monthly
deliverable is a slide deck, frozen the day it is sent, while the database keeps
one single classification for the whole history.

Run `recompute_outcomes()` after every change to `is_technical_failure()`.
Without it, the months before the change keep the old classification and the
monthly series stop being comparable.

`GET /api/reporting/ivr-reasons` lists the close reasons of the period with
their outcome: the candidates for the whitelist are the reasons of `ivr_only`
calls that are in fact faults.

## Production

    docker compose -f docker-compose.prod.yml up -d

A complete file rather than an override — removing a volume through an override
needs Compose 2.24. It leaves out the source mount — the image is what was tested, the
working directory is not — sets `MANAGER_ENV=production`, which makes the
process refuse to start without a session secret and a Secure cookie, and
publishes the port on `MANAGER_BIND` — the loopback by default, so that a
reverse proxy on the same host is the only client.

Which address the forwarded headers are believed from is easy to get wrong
behind Docker: depending on its userland proxy, a connection published on the
loopback can reach the container from the bridge gateway (172.17.0.1 or the
compose network's) rather than from 127.0.0.1. Check it once after deploying: sign in with a wrong password from
your workstation and read the log line `wrong password for 'x' from <address>`.
It must name your workstation. If it names the proxy or the bridge, set
`FORWARDED_ALLOW_IPS` to that address — otherwise the throttle counts every
attempt against one address, and five failures lock the console for everyone.

`TRUST_PROXY=1` is set there because a reverse proxy is assumed: the login
throttle then keys on the address the proxy appended to `X-Forwarded-For`, and
uvicorn accepts forwarded headers from `FORWARDED_ALLOW_IPS` only (default
127.0.0.1, the proxy on the same host). Without a proxy, unset both, or a
client could forge the header and step around the throttle.

### A proxy on another machine

`deploy/traefik/manager.example.yml` is an example of that set-up: Traefik on
its own machine, the Manager reached over the LAN. On the Manager's side:
`MANAGER_BIND=<its LAN address>` and a firewall rule keeping 8200 to the
proxy and the gateways, `TRUST_PROXY=1`, `FORWARDED_ALLOW_IPS=<the proxy's address>`,
`MANAGER_COOKIE_SECURE=1`, `PROXYAPI_PUBLIC_URL` and `HOMER_BASE` on their
public names. The port stays reachable on the LAN for the gateways' pushes;
`X-Forwarded-For` is believed from the declared proxy only. The page polls
`/health`: a rule that hides it shows "Manager unreachable" (a test checks
every path the front calls against the rule).

### What the reverse proxy must relay

| Path | Client | Note |
|---|---|---|
| `/`, `/static/*`, `/api/*`, `/auth/*` | operators' browsers | the console |
| `/ingest/calls` | every gateway (`LOG_PUSH_URL`) | **without it, call history silently stops** |
| `/health` | monitoring, optional | 200 or 503 |

A push refused by the proxy is retried by the gateway only at its next call
end, and its history file keeps growing meanwhile: check `/ingest/calls`
through the proxy with a bad token (expect 401 from the Manager, not 404 from
the proxy) before pointing gateways at it.

### Deploying a change

    git pull
    ./tools/backup.sh manual                             # a dump to come back to
    ./tools/migrate.sh --dry-run && ./tools/migrate.sh   # schema first, one transaction
    docker compose -f docker-compose.prod.yml up -d --build
    docker compose -f docker-compose.prod.yml ps          # STATUS must read (healthy)
    curl -s http://127.0.0.1:8200/health                  # {"status":"ok"}

A forgotten migration surfaces as `503 Reporting database unavailable` on one
route, not as a startup error: the health line above and a glance at each
tab after a deploy are the check. `unhealthy` in `ps` means the probe fails;
nothing restarts the container for it — that is a call, not an event.

## Backup and restore

The call history exists nowhere else: a gateway pushes each call once, at its
end, and keeps no copy (a repeated push is recognised and ignored).
`tools/backup.sh` takes a logical dump (`pg_dump -Fc`) of `gw_manager`, checks
it lists the data of `calls` before keeping it, records the row counts next
to it (`<dump>.counts`) and rotates the old ones — only after a success, so a
failing backup never deletes the last good dump.

| Kind | When (crontab) | Kept |
|---|---|---|
| `intraday` | 8h to 20h every two hours, Monday to Friday | 48 hours |
| `nightly` | 2h, every day | 30 days |
| `manual` | by hand, before a migration | until deleted |

    sudo install -d -m 700 -o "$USER" -g "$USER" /var/backups/gw_manager   # once
    ./tools/backup.sh --install-cron      # the two lines above, idempotent
    ./tools/backup.sh manual              # a dump now
    tail /var/backups/gw_manager/backup.log

Dumps hold the account table, password hashes included: the directory is
0700 and each file 0600. `BACKUP_DIR` moves it; in production, point it at
what the backup server collects. A VM snapshot by the host does not replace
this: it brings back the whole machine at one date, Homer included, where a
dump brings back this database alone. What to monitor: the age of
`/var/backups/gw_manager/last-success` (older than 25 hours is a failure).

### Proving a dump restores

    ./tools/restore-check.sh                       # the newest dump
    ./tools/restore-check.sh <file.dump> --keep    # keep gw_manager_restore to look at

It restores into a scratch database, `gw_manager_restore`, compares each
table with the counts recorded at dump time, reads every reporting view, and
drops the scratch database. The live database is only read; any target not
named `*_restore` is refused. Run it after installing the backup, after any
change of PostgreSQL or TimescaleDB image, and before a go-live.

### TimescaleDB

The database carries the TimescaleDB extension, unused today and kept on
purpose for the in-call media series. Two consequences:

- a dump restores only on an instance with **the same TimescaleDB version**
  (`SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'`);
- the restore is wrapped in `timescaledb_pre_restore()` and
  `timescaledb_post_restore()`, as below. `restore-check.sh` does it.

In production, set `timescaledb.telemetry_level = off` on the instance: by
default the extension reports usage to its vendor.

### Restoring over the live database

The live database is renamed, not dropped: it stays there to compare with
until the restore is accepted. `root` is the instance's superuser.

    docker compose stop manager
    docker exec -i postgres psql -U root -d postgres -c "ALTER DATABASE gw_manager RENAME TO gw_manager_before_restore"
    docker exec -i postgres psql -U root -d postgres -c "CREATE DATABASE gw_manager OWNER gw_manager"
    docker exec -i postgres psql -U root -d gw_manager -c "CREATE EXTENSION IF NOT EXISTS timescaledb" -c "SELECT timescaledb_pre_restore()"
    docker exec -i postgres pg_restore -U root -d gw_manager < /var/backups/gw_manager/<file>.dump
    docker exec -i postgres psql -U root -d gw_manager -c "SELECT timescaledb_post_restore()" -c "ANALYZE"
    docker compose start manager
    # once the console reads right:
    docker exec -i postgres psql -U root -d postgres -c "DROP DATABASE gw_manager_before_restore"

`pg_restore` may report errors on TimescaleDB's own catalog
(`_timescaledb_*`, rows the extension already wrote): those are expected.
An error on any other object means the restore is not complete — run
`restore-check.sh` on the same dump first, it tells the two apart.

Calls pushed between the dump and the restore are lost: the gateways do not
push them again. Pool samples of that interval are lost too.

## Tests

    ./tools/test.sh                      # everything
    ./tools/test.sh tests/test_front.py  # one file, arguments go to pytest

The container carries Python and Node. Node matters: the front-end checks parse
each module with `node --check`, and that is the only thing that catches a
template literal cut in half — counting braces does not, and the module then
fails to load with the whole interface behind it.

Without Node those checks skip rather than fail, so a bare `pytest` still runs;
it just covers less.

None of this needs a browser, and almost none a database: `fetch` is replaced by
a recorder, so the routes run against no PostgreSQL, and the front is read as
files. The few modules that check SQL behaviour for real (`*_db.py`) run when
`DATABASE_URL_TEST` names a database, and skip otherwise — they write test rows
and remove them, on a test database preferably.

One check does need a browser, and is run by hand: `tests/e2e/escaping.mjs`
feeds every screen API answers whose text fields carry markup, and fails if
any element is created from them (`npm install playwright`, then
`node tests/e2e/escaping.mjs`). Every value the front writes into HTML goes
through `esc()`; this is what shows it.

## Exporting the code for a review

    ./tools/export-for-review.sh           # writes /tmp/manager-review-<date>.tar.gz

The archive leaves out `.env` (every `.env.*` but `.env.example`), keys and
certificates, dumps, logs, archives and caches, and lists their names in
`REVIEW-EXPORT.txt`. It is not written if a kept file holds the value of a
secret of `.env` or a private key or token; the value is never printed, only
the file and the key's name. `user:password@` in a URL and private addresses
outside `tests/` are listed as warnings. The script header gives the full list.


## Deployment

    docker compose up -d --build      # first run, and after requirements.txt changes
    docker compose up -d              # afterwards

## Licence

Apache License 2.0, like [SIPMediaGW](https://github.com/Renater/SIPMediaGW):
see `LICENSE`.
