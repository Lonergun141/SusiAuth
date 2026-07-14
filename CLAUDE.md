# CLAUDE.md

Guidance for working in this repository.

## What this is

**SusiAuth** is a reusable, centralized authentication service (identity provider) built with
**Django 5 + Django Ninja**. It issues **RS256 JWTs** and exposes a REST API. Other
apps/microservices verify tokens statelessly via the published JWKS endpoint.

> **API prefix:** despite the `api/v1/` package name and `api_v1` NinjaAPI object, `config/urls.py`
> mounts it at `path("api/", ...)`, so live routes are under **`/api`** (e.g. `/api/auth/login`,
> `/api/health`, `/api/.well-known/jwks.json`) — *not* `/api/v1`. Wiring the real `/v1` prefix is
> part of the still-pending API-design workstream.

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
    routers/            auth.py, health.py, webhooks.py (Resend)
  apps/
    accounts/           User (custom, email login), UserSession, RegistrationField, EmailOTP
    tokens/             RefreshToken, OneTimeToken + services.py (token lifecycle)
    mfa/                TOTPDevice, RecoveryCode + services.py (TOTP enroll/verify)
    oauth/              validators.py (custom OIDC claims for django-oauth-toolkit)
    notifications/      EmailProvider, OutboundEmail/WebhookEvent, Celery task, templates
    common/             security.py (JWT/JWKS/hashing), pwned.py (HIBP check)
    audit/              audit models/services (stubs)
  config/celery.py      Celery app (config/__init__.py exposes celery_app)
  infrastructure/, utils/
docs/postman/           Per-endpoint request/response docs (source of truth for the API surface)
keys/                   RSA keypair lives here (gitignored except .gitkeep)
tests/                  pytest suite (token flow, health, prod settings, notifications)
```

## Running

Docker is the primary path:

```bash
docker compose up --build      # DEV: runs migrate + runserver on :8000; Postgres on :5432
```

The image itself is production-oriented: multi-stage build, non-root `app` user, and a Gunicorn
`CMD` defaulting to `DJANGO_SETTINGS_MODULE=authsvc.config.settings.prod`. The dev `docker-compose.yml`
overrides that with runserver + dev settings + a source mount. `docker-compose.prod.yml` is a
production-shaped example: a one-off `migrate` service (the web container never migrates on boot),
DB not published to the host, read-only key mount, healthchecks, restart policies.

**Health endpoints:** `/api/health` (basic), `/api/health/live` (liveness, no deps),
`/api/health/ready` (readiness — checks DB + JWT signing keys, returns 503 if unavailable).

**Production settings fail fast:** `config/settings/prod.py` raises `ImproperlyConfigured` on import
if `DJANGO_SECRET_KEY` is missing/default, `DJANGO_ALLOWED_HOSTS` is empty/wildcard, JWT key files are
missing, the frontend URLs are localhost, or (when `EMAIL_PROVIDER=resend`) `RESEND_API_KEY` /
`RESEND_WEBHOOK_SECRET` are missing. It also sets HSTS, secure/HttpOnly cookies, SSL redirect,
proxy SSL header, and nosniff/frame/referrer headers.

## OAuth 2.1 / OIDC (`django-oauth-toolkit`, mounted at `/o/`)

Third-party client authorization is handled by **django-oauth-toolkit (DOT)** — a mature library, not
a hand-rolled server (per the brief). First-party auth (`/api/auth/*`, RS256 JWTs) is unchanged; DOT
is for *clients* (web/mobile/service integrations).

- **Endpoints** (`/o/`): `authorize`, `token`, `revoke_token`, `introspect`, `userinfo`,
  `.well-known/openid-configuration`, `.well-known/jwks.json`. Use `reverse("oauth2_provider:<name>")`.
- **Flows:** Authorization Code **+ PKCE** (`PKCE_REQUIRED=True`, OAuth 2.1) and Client Credentials.
  The **password (ROPC) grant is not used**. Redirect URIs are enforced by DOT; secrets are hashed.
- **OIDC:** `OIDC_ENABLED`, id_tokens signed **RS256 with the same key as our first-party JWTs**
  (`OIDC_RSA_PRIVATE_KEY` loaded from `JWT_PRIVATE_KEY_PATH`). Per-client, set `algorithm="RS256"` for
  signed id_tokens. Custom claims (email/profile) come from `apps/oauth/validators.py`.
- **Access tokens are opaque** (validated via `userinfo`/introspection); the **id_token** is the JWT
  downstreams verify via `/o/.well-known/jwks.json`. First-party access tokens remain RS256 JWTs.
- **Clients** are created via Django admin or `python manage.py createapplication`. The authorization
  (consent) flow needs a browser session — a minimal `/accounts/login/` page is provided.
- **Known limitations:** two JWKS endpoints exist (`/api/.well-known/jwks.json` for first-party,
  `/o/.well-known/jwks.json` for OIDC) — same key, different URLs; no consent-screen customization yet.

## MFA (`apps/mfa`) — TOTP

- **Enroll:** `POST /api/auth/mfa/setup` (auth) returns a secret + `otpauth://` URI (render as QR);
  `POST /api/auth/mfa/confirm` verifies the first code, sets `User.mfa_enabled`, and returns
  **recovery codes once**. Secrets are **encrypted at rest** (`crypto.py`, Fernet keyed off
  `MFA_SECRET_ENCRYPTION_KEY`/`SECRET_KEY`); recovery codes are stored **SHA-256 hashed, single-use**.
- **Login challenge:** when `mfa_enabled`, `/api/auth/login` returns `{mfa_required: true, mfa_token}`
  instead of tokens (schema `LoginOut`). `mfa_token` is a short-lived signed JWT with `purpose="mfa"`
  (`make_mfa_challenge`/`verify_mfa_challenge` in `common/security.py`) — NOT a bearer credential.
  `POST /api/auth/mfa/verify {mfa_token, code}` accepts a TOTP **or** a recovery code and issues tokens.
- **Manage:** `/disable` and `/recovery-codes` (regenerate) require re-auth (password + a current code).
  `verify_factor()` tries TOTP (`pyotp`, ±1 window) then a recovery code. Enable/disable/recovery-use
  send notification emails. Structured so WebAuthn can be added as a sibling factor.

## Email / notifications (`apps/notifications`)

All auth email goes through this app — never `send_mail`/an SDK directly.

- **Flow:** `services.send_*` renders the template **in the web process** (where the secret exists),
  writes a **secret-free** `OutboundEmail` record, and enqueues delivery on `transaction.on_commit`.
  The Celery task `tasks.send_outbound_email` sends via the provider and records status/provider id.
- **Providers** (`providers.py`): selected by `EMAIL_PROVIDER` — `console` (dev), `resend`
  (Anymail backend), `inmemory` (tests, `InMemoryEmailProvider.outbox`). Resend specifics stay here.
- **Never persisted/logged:** OTP codes, reset links/tokens, rendered bodies. Sensitive content is
  passed to the task transiently as arguments, not stored on `OutboundEmail`.
- **Idempotency:** `OutboundEmail.idempotency_key` (unique) dedupes; an already sent/delivered record
  is not re-sent. **Celery** runs eager (inline, no broker) in dev/test via `CELERY_TASK_ALWAYS_EAGER`;
  a real worker + Redis run it in Docker/prod.
- **Webhooks:** `POST /api/webhooks/resend` verifies the **Svix signature over the raw body** before
  trusting JSON (`webhooks.py`), is idempotent on `svix-id` (`WebhookEvent`), and applies delivery
  status with an out-of-order rank guard. Requires `RESEND_WEBHOOK_SECRET`.
- **On-commit + tests:** dispatch happens on commit, so tests use the
  `django_capture_on_commit_callbacks(execute=True)` fixture.

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
