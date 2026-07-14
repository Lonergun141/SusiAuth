# CLAUDE.md

Guidance for working in this repository.

## What this is

**SusiAuth** is a reusable, centralized authentication service (identity provider) built with
**Django 5 + Django Ninja**. It issues **RS256 JWTs** and exposes a versioned REST API under
`/api/v1`. Other apps/microservices verify tokens statelessly via the published JWKS endpoint.

## Layout

Uses a `src/` layout — the `authsvc` package lives under `src/`, so anything run outside Docker
needs `src` on the path (`PYTHONPATH=src`, or use `manage.py`, which appends it automatically).

```
src/authsvc/
  config/               Django project (settings, urls, wsgi/asgi)
    settings/           base.py + dev.py + prod.py (dev is the manage.py default)
  api/v1/
    api.py              NinjaAPI instance (api_v1); mounts routers + /.well-known/jwks.json
    auth.py             AuthBearer (HttpBearer) — verifies JWT, sets request.jwt = payload
    schemas.py          Ninja request/response schemas
    routers/            auth.py (all auth endpoints), health.py
  apps/
    accounts/           User (custom, email login), UserSession, RegistrationField, EmailOTP
    tokens/             RefreshToken, OneTimeToken + services.py (token lifecycle)
    common/             security.py (JWT/JWKS/hashing), emailer.py, pwned.py (HIBP check)
    audit/              audit models/services
  infrastructure/, utils/
docs/postman/           Per-endpoint request/response docs (source of truth for the API surface)
keys/                   RSA keypair lives here (gitignored except .gitkeep)
tests/                  pytest stubs (conftest + test_auth_flow are currently placeholders)
```

## Running

Docker is the primary path:

```bash
docker compose up --build      # runs migrate + runserver on :8000; Postgres on :5432
```

Local (without Docker):

```bash
export PYTHONPATH=src                       # required (src/ layout)
export DB_HOST=localhost                     # base.py defaults DB_HOST to "db" (the compose service)
python manage.py migrate
python manage.py runserver
```

Config is env-driven via `.env` at the repo root (loaded in `config/settings/base.py`). Not committed.

## Testing

```bash
python -m venv .venv && . .venv/Scripts/activate   # (Windows) or .venv/bin/activate
pip install -r requirements-dev.txt
pytest                                             # sqlite, DJANGO_SETTINGS_MODULE from pytest.ini
```

- `config/settings/test.py` uses in-memory **sqlite** by default. Set `TEST_DATABASE=postgres`
  (+ `DB_*` env) to run against Postgres — required for the concurrency test.
- `tests/conftest.py` generates an **ephemeral RSA keypair** per session and points the JWT settings
  at it, so tests need no committed/generated keys.
- The refresh-rotation **concurrency test** (`test_concurrent_rotation_only_one_wins`) is
  Postgres-only (`select_for_update` is a no-op on sqlite); it **skips** locally and **runs in CI**.
- Lint/CI: `ruff check src tests`. CI (`.github/workflows/ci.yml`) runs ruff, `makemigrations --check`,
  `manage.py check`, and pytest against a Postgres service.

## Auth model / conventions

- **Access tokens**: short-lived RS256 JWTs (`JWT_ACCESS_TTL_SECONDS`, default 600s). Claims include
  `sub` (user UUID, not PK), `email`, `roles`, `sid` (session id), `jti`. Signed/verified in
  `apps/common/security.py`. `jwt_verify_rs256` enforces `iss`/`aud`/`exp`.
- **Refresh tokens**: opaque random strings, **stored hashed** (SHA-256) in the DB. The raw token is
  only available on the in-memory instance via `.raw_token` right after creation — the DB never holds
  it. Rotation is in `apps/tokens/services.py` with **family tracking + reuse detection**: presenting
  an already-revoked token revokes the whole session/family.
- **Protected endpoints** use `auth=auth` (the `AuthBearer`). Read the user with
  `User.objects.get(uuid=request.jwt["sub"])`.
- **Downstream verification**: consumers fetch `GET /api/v1/.well-known/jwks.json` and verify locally.
- **Email verification** uses 6-digit OTPs (`EmailOTP`, hashed, attempt-limited). **Password
  reset** uses single-use `OneTimeToken`s. Users are created `is_active=False` until email is verified.
- **Password policy**: min length 10 + Django validators + HaveIBeenPwned k-anonymity check
  (`apps/common/pwned.py`, fails open if HIBP is unreachable).
- Endpoints are **rate-limited** with `@ratelimit` (per IP) in `routers/auth.py`.

The Postman docs in `docs/postman/` mirror the live endpoints — update them alongside API changes.

## Token flow (invariants — do not regress)

- `issue_token_pair` (login / verify-email) creates **one** new session and returns the **raw**
  refresh token (`.raw_token`), never the stored hash.
- `rotate_refresh_token` (`/refresh`) is `transaction.atomic()` + `select_for_update()`, continues
  the **same** session, revokes the presented token, and issues exactly one replacement token + one
  access token. The router must **not** also call `issue_token_pair` (that mints a phantom session).
- Reuse detection: presenting an already-revoked token calls `_revoke_family` and kills the whole
  session/family. Two concurrent rotations of the same token → exactly one succeeds.

## Gotchas (verify before assuming the app runs clean)

- **`django-ratelimit` still isn't in `INSTALLED_APPS`.** It's now in `requirements.txt`, and the
  decorator works without app registration, but production needs a shared (Redis) cache — the
  default `LocMemCache` gives per-process counters that don't throttle across replicas.
- `manage.py` defaults `DJANGO_SETTINGS_MODULE` to `authsvc.config.settings.dev`.
- Local env note: this repo targets Django 5, but a bare `python` on the dev box may resolve to
  Django 4.2 with no project deps — use Docker or a venv from `requirements-dev.txt` to run/verify.
