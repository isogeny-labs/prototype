# Hosting: GitHub login, PostgreSQL, Redis and file storage

Added 21 November 2026. Everything here is **off by default**: with none of these settings, `./run-demo.sh` starts
the same demo as before (SQLite in `data/`, the password login, a cache in memory, no file copies anywhere).

## Run the whole stack on one computer

You need Docker.

```
cp .env.example .env          # optional: fill in the GitHub App (below)
docker compose up --build
```

Open **http://localhost:8000**. Without a GitHub App in `.env`, the app asks you to create a password as usual.

| Service | What it is | Where |
| --- | --- | --- |
| `app` | Evidence Lab (demo mode) | http://localhost:8000, health at `/api/health` |
| `postgres` | the database | inside the stack only |
| `redis` | the cache | inside the stack only |
| `s3` | S3-compatible file storage (SeaweedFS), access keys from `.env` | inside the stack only |
| `s3-bucket` | makes the bucket once, then stops | |

`docker compose down` stops it; `docker compose down -v` also deletes the data.

The app runs in **demo mode** in its container: isolated mode starts containers of its own and needs Docker on the
host, which the container does not have. Otto's harness is not in the image (it is private and fetched by
`./run-demo.sh`), so the app says "Otto is not installed" there, as it does on any computer without it.

## Run it on AWS

`deploy/terraform/aws/` creates one copy on AWS: ECS Fargate behind a load balancer (HTTPS on your own address),
RDS PostgreSQL, ElastiCache Redis, an S3 bucket, EFS for the data folder, and the secrets in Secrets Manager. Its
README has the three steps. The database password then comes from Secrets Manager as `EVIDENCE_LAB_DATABASE_PASSWORD`
and is put into `EVIDENCE_LAB_DATABASE_URL`, which holds none.

## The settings

| Setting | What it does | Default |
| --- | --- | --- |
| `EVIDENCE_LAB_DATABASE_URL` | `postgresql://user:password@host:5432/db` (PostgreSQL 14 or newer), or `sqlite:///path` | the SQLite file in the data folder |
| `EVIDENCE_LAB_DATABASE_PASSWORD` | the database password, kept apart from the URL (a secret store hands it over) | |
| `EVIDENCE_LAB_REDIS_URL` | `redis://host:6379/0` | a cache in memory (one process) |
| `EVIDENCE_LAB_STORAGE_URL` | `s3://bucket/prefix`, `gs://bucket/prefix`, or a folder | none: no copies are made |
| `EVIDENCE_LAB_S3_ENDPOINT_URL` | another S3-compatible server (SeaweedFS, MinIO, R2; GCS through `https://storage.googleapis.com` with HMAC keys) | AWS |
| `EVIDENCE_LAB_PUBLIC_URL` | the address people open, e.g. `https://lab.example.com`; with `https://` the cookies are Secure | the address of the request |
| `EVIDENCE_LAB_ALLOWED_HOSTS` | more host names the app answers to, comma-separated | `localhost`, `127.0.0.1`, and the public URL's host |
| `EVIDENCE_LAB_GITHUB_CLIENT_ID`, `..._CLIENT_SECRET` | the GitHub App used to log in | not set: no GitHub login |
| `EVIDENCE_LAB_GITHUB_APP_SLUG` | the App's name in `github.com/apps/<slug>` | not set |
| `EVIDENCE_LAB_GITHUB_ALLOWED_USERS` | GitHub logins or numeric account ids that may log in | |
| `EVIDENCE_LAB_GITHUB_ALLOWED_ORGS` | organizations whose active members may log in (the App needs "Members: read-only") | |
| `EVIDENCE_LAB_GITHUB_ALLOW_ANYONE` | `on`: every GitHub account may log in | `off`; one of these three is required with the GitHub login |
| `EVIDENCE_LAB_GITHUB_WEB_URL`, `..._API_URL` | GitHub Enterprise Server, or the stand-in below | github.com |
| `EVIDENCE_LAB_PASSWORD_LOGIN` | the password login; a session made with a login that is switched off stops working | `off` with the GitHub login, `on` without |
| `EVIDENCE_LAB_BIND_HOST`, `EVIDENCE_LAB_PORT` | where `python -m app` listens | `127.0.0.1`, `8000` |

S3 credentials come from the usual AWS variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`) or the
host's role; Google Cloud Storage uses the host's Google credentials (`GOOGLE_APPLICATION_CREDENTIALS` or the
workload identity). The packages for these (`psycopg`, `redis`, `boto3`, `google-cloud-storage`) are in
`backend/requirements-infra.lock`, which the Docker image installs and `./run-demo.sh` does not. To use them outside
Docker: `cd backend && .venv/bin/python -m pip install --require-hashes --no-deps -r requirements-infra.lock`.

## The GitHub App

1. On GitHub: **Settings → Developer settings → GitHub Apps → New GitHub App** (or the same under an organization's
   settings).
2. **Callback URL**: your public URL + `/api/auth/github/callback`, for example
   `http://localhost:8000/api/auth/github/callback`. Leave "Expire user authorization tokens" as it is.
3. **Webhook**: untick *Active* (the app uses no webhooks). **Permissions**: none are needed to log in by user list;
   for an organization list, give **Organization permissions → Members: Read-only**.
4. Create it, then on its page copy the **Client ID** and **Generate a new client secret**. Put both in `.env`.
5. Say who may log in (the app refuses to start without it; everyone who logs in shares the same assessments):
   `EVIDENCE_LAB_GITHUB_ALLOWED_ORGS=<org>` lets in the organization's **active** members (install the App on the
   organization, with the permission above; outside collaborators and pending invitations do not count), and
   `EVIDENCE_LAB_GITHUB_ALLOWED_USERS` lists people by login or, safer against renamed accounts, by numeric id
   (`https://api.github.com/users/<login>` shows it). `EVIDENCE_LAB_GITHUB_ALLOW_ANYONE=on` lets every GitHub
   account in.

The login screen then shows **Log in with GitHub** (and no password, unless `EVIDENCE_LAB_PASSWORD_LOGIN=on`: on
a hosted copy, the first visitor would otherwise choose the password). The app asks GitHub who the person is (and,
with an organization list, whether they are an active member), keeps their GitHub id, login, name and picture in
`github_users`, and drops the GitHub token straight away: it is never stored, logged or shown. The one-time `state`
of each login is kept in the cache for 10 minutes and in a cookie of the browser that started it, and works once.

### Trying the GitHub login without a real App

`backend/tools/fake_github.py` stands in for GitHub on one computer: it sends the browser straight back with a code,
as GitHub does after **Authorize**. Its docstring has the command and the settings
(`EVIDENCE_LAB_GITHUB_WEB_URL` and `EVIDENCE_LAB_GITHUB_API_URL` point the app at it; they also serve GitHub
Enterprise Server).

## What is kept where

- **The database** holds every record, as before. On PostgreSQL the same rules are enforced by triggers: the
  append-only tables refuse `UPDATE`, `DELETE` and `TRUNCATE`; folders, projects and assessments refuse `DELETE`.
  Tables and triggers are made when the app starts (several processes may start at once).
- **The cache** holds only short-lived things that are safe to lose (the login `state`). No result is read from it.
- **The file store**, when one is named, gets a copy of each scanner file brought in (`imports/<sha256>/<name>`) and of each evidence
  download (`evidence/<plan>/<fingerprint>.json` and `.html`). The database stays the record: a copy that could not
  be written is logged and changes no answer.
- `/api/health` (no login, any host name, so a load balancer's probe by address works) says which kind of database, cache and store is used and whether each answers: 200 when
  all do, 503 otherwise. It shows no address, name or secret.

## Checks

- `cd backend && .venv/bin/python -m pytest -q tests/hosting`: the GitHub login (GitHub is a stand-in; no test reaches
  it), the cache, the file store (S3 through the `moto` stand-in, when installed), the settings and the health check.
- The whole suite on PostgreSQL (tests that open the SQLite file itself or use SQLite's own SQL fail there by design; on
  21 November 2026 that was 9 tests, every other one passed): `EVIDENCE_LAB_TEST_DATABASE_URL=postgresql://user@host/postgres` before the usual
  pytest command; every data folder a test makes gets its own database on that server, dropped at the end. With
  `EVIDENCE_LAB_TEST_REDIS_URL=redis://host:6379/0` the Redis test runs too.

## Not in this version, and for the owner to decide

- **More than one login.** The product rules say the app has one login and does not check who is at the keyboard,
  and it says so on screen. With GitHub, several people can log in to the same assessments. Those sentences are
  left as they are until the owner decides how they should read.
- **Outside services.** The GitHub login makes requests to github.com, and a named file store receives the scanner
  files and evidence. Both happen only when their settings are given; the Safety section names osv.dev as the one
  outside service, and should say so if these are kept.
- **Addresses a hosted copy reaches.** Checks make TLS handshakes to the addresses a person confirms. On a hosted
  copy those handshakes start inside the host's network (for example a cloud metadata address). Before letting
  people outside your team in, decide which addresses a hosted copy may reach.
- Text with a NUL character (`\0`) is stored by SQLite but refused by PostgreSQL.

- A person's GitHub login is not yet the name a decision is recorded under: decisions still use the name typed once
  (Settings, **Who decides**) or "You", as the product rules say. Whether it should be is the owner's choice.
- There is a `POST /api/logout`, but no Log out button (a new button needs the owner's OK).
- Reading code from GitHub repositories (the App's repository permissions) is not built: only the bundled demo
  repository is connected, as before.
