# SusiAuth

> “Susi sa imong sistema.”
> The key to your ecosystem.

SusiAuth is a reusable authentication service (identity provider) built with **Django 5 +
Django Ninja**. It issues **RS256 JWTs** and is designed to be plugged into multiple apps or
microservices as a centralized identity provider — downstream services verify tokens statelessly
via the published JWKS endpoint.

## Features

- RS256 JWT access tokens + JWKS endpoint for downstream verification
- Refresh-token rotation with reuse detection (tokens stored hashed)
- Email verification (OTP) and forgot/reset/change password
- Logout (single session and all sessions)
- Per-IP rate limiting, HaveIBeenPwned password check
- PostgreSQL, Dockerized, liveness/readiness health probes

> **API prefix:** routes are served under **`/api`** (e.g. `/api/auth/login`) — not `/api/v1`
> despite the internal `api/v1/` package name. Interactive docs: **`/api/docs`**.

---

## Prerequisites

- **Docker + Docker Compose** (recommended path), **or**
- **Python 3.12+**, **PostgreSQL 14+**, and **OpenSSL** (for the non-Docker path)

---

## 1. Get the code and configure env

```bash
git clone git@github.com:Lonergun141/SusiAuth.git
cd SusiAuth
cp .env.example .env          # then edit values as needed
```

`.env` is loaded by `config/settings/base.py` and is gitignored. See
[Environment variables](#environment-variables) for the full list.

## 2. Generate JWT signing keys

The service signs tokens with an RSA keypair in `keys/` (gitignored). Generate it once:

```bash
bash scripts/generate_keys.sh          # writes keys/jwt_private.pem + keys/jwt_public.pem
```

No Bash/OpenSSL script? Run OpenSSL directly:

```bash
mkdir -p keys
openssl genrsa -out keys/jwt_private.pem 2048
openssl rsa -in keys/jwt_private.pem -pubout -out keys/jwt_public.pem
```

> The filenames must match `JWT_PRIVATE_KEY_PATH` / `JWT_PUBLIC_KEY_PATH`
> (default `keys/jwt_private.pem` and `keys/jwt_public.pem`).

---

## Run with Docker (recommended)

```bash
docker compose up --build
```

This starts PostgreSQL and the web service, runs migrations, and serves the dev server on
**http://localhost:8000**. Compose overrides `DB_HOST` to the `db` service automatically.

Create an admin user (custom user model — logs in by **email**):

```bash
docker compose exec web python manage.py createsuperuser
```

Stop with `Ctrl+C`; `docker compose down` to remove containers (add `-v` to drop the DB volume).

---

## Run without Docker

You need a running PostgreSQL with the credentials from your `.env` (and `DB_HOST=localhost`).

```bash
# 1. Virtual environment + dependencies
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt  # or requirements.txt for runtime only

# 2. Create the database (example, adjust to your Postgres setup)
createdb authdb

# 3. Migrate and run (manage.py puts src/ on the path and defaults to dev settings)
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

> **`src/` layout:** the `authsvc` package lives under `src/`. `manage.py` appends `src/` to the
> path automatically. If you invoke Django another way, set `PYTHONPATH=src`.

The dev settings use the **console email backend**, so verification codes and reset links print to
the terminal instead of being emailed.

---

## Verify it's up

```bash
curl http://localhost:8000/api/health          # {"status": "ok"}
curl http://localhost:8000/api/health/ready     # DB + signing-key readiness
open  http://localhost:8000/api/docs            # interactive API docs
```

### Key endpoints (under `/api`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/auth/register` | – | Register (creates inactive user, emails OTP) |
| POST | `/api/auth/verify-email` | – | Verify OTP, activate, return tokens |
| POST | `/api/auth/login` | – | Login, return access + refresh tokens |
| POST | `/api/auth/refresh` | – | Rotate refresh token, return new pair |
| GET  | `/api/auth/me` | Bearer | Current user profile |
| POST | `/api/auth/change-password` | Bearer | Change password |
| POST | `/api/auth/forgot-password` | – | Send reset link |
| POST | `/api/auth/reset-password` | – | Reset via single-use token |
| POST | `/api/auth/logout` / `/logout-all` | –/Bearer | Revoke session(s) |
| GET  | `/api/.well-known/jwks.json` | – | Public keys for downstream verification |
| GET  | `/api/health` · `/live` · `/ready` | – | Health / liveness / readiness |

Per-endpoint request/response examples live in [`docs/postman/`](docs/postman/).

---

## Running tests

```bash
pip install -r requirements-dev.txt
pytest                       # in-memory sqlite; no Postgres needed
ruff check src tests         # lint
```

- Tests use `config/settings/test.py` and generate an ephemeral RSA keypair, so they need neither a
  database server nor committed keys.
- The refresh-rotation **concurrency** test needs real row locking, so it is Postgres-only and skips
  on sqlite. To run it: `TEST_DATABASE=postgres pytest` with a Postgres reachable via the `DB_*` env.
- CI (`.github/workflows/ci.yml`) runs ruff, a migration check, `manage.py check`, and pytest against
  a Postgres service.

---

## Environment variables

| Variable | Default | Notes |
|----------|---------|-------|
| `DJANGO_SECRET_KEY` | `dev-secret` | **Set a real value**; prod refuses the default |
| `DJANGO_DEBUG` | `0` | `1` to enable debug |
| `DJANGO_ALLOWED_HOSTS` | `*` | Comma-separated; prod refuses `*` |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` | `authdb` / `authuser` / `authpass` | |
| `DB_HOST` / `DB_PORT` | `db` / `5432` | Use `localhost` off-Docker |
| `DEFAULT_FROM_EMAIL` | `no-reply@musngi.com` | Sender for auth emails |
| `EMAIL_*` | SMTP defaults | Dev uses the console backend |
| `JWT_ISSUER` / `JWT_AUDIENCE` | `auth-service` / `your-apps` | Validated by downstream |
| `JWT_ACCESS_TTL_SECONDS` | `600` | Access-token lifetime |
| `JWT_REFRESH_TTL_SECONDS` | `2592000` | Refresh-token lifetime (30d) |
| `OTP_TTL_MINUTES` / `ONETIMETOKEN_TTL_MINUTES` | `5` / `15` | Email OTP / reset-token TTL |
| `JWT_PRIVATE_KEY_PATH` / `JWT_PUBLIC_KEY_PATH` | `keys/jwt_private.pem` / `keys/jwt_public.pem` | RSA keypair |
| `FRONTEND_RESET_PASSWORD_URL` / `FRONTEND_VERIFY_EMAIL_URL` | `http://localhost/...` | `{token}` is substituted |

Production adds fail-fast validation and security headers — see `config/settings/prod.py` and
`docker-compose.prod.yml`.

---

## Project layout

See [`CLAUDE.md`](CLAUDE.md) for a fuller tour of the architecture, token-flow invariants, and gotchas.

```
src/authsvc/
  config/settings/   base.py + dev.py (default) + test.py + prod.py
  api/v1/            NinjaAPI (api_v1), AuthBearer, schemas, routers/{auth,health}
  apps/accounts/     User (email login), UserSession, RegistrationField, EmailOTP
  apps/tokens/       RefreshToken, OneTimeToken + services.py (token lifecycle)
  apps/common/       security.py (JWT/JWKS/hashing), emailer.py, pwned.py
docs/postman/        Per-endpoint request/response docs
keys/                RSA keypair (gitignored)
tests/               pytest suite
```

## Troubleshooting

- **`ImproperlyConfigured` / JWT errors** — generate the keys (step 2) and confirm the paths.
- **DB connection refused (off-Docker)** — Postgres isn't running or `DB_HOST` isn't `localhost`.
- **`ModuleNotFoundError: authsvc`** — set `PYTHONPATH=src` (or use `manage.py`).
- **A stray `python` resolves to Django 4.2** — use the venv from `requirements-dev.txt`; the project targets Django 5.
