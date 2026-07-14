# OAuth 2.1 / OIDC

Third-party client authorization via django-oauth-toolkit, mounted at `/o/`.
First-party login (`/api/auth/*`) is separate — this is for OAuth **clients**.

Register a client first (admin or CLI):
```bash
python manage.py createapplication confidential authorization-code \
  --name "My App" --redirect-uris "https://myapp.example/callback" --algorithm RS256
```

## Discovery

**GET** `{{base_url}}/o/.well-known/openid-configuration` → issuer, endpoints, `jwks_uri`, scopes.
**GET** `{{base_url}}/o/.well-known/jwks.json` → public keys for verifying id_tokens.

---

## Authorization Code + PKCE (users)

1. Build a PKCE pair: `code_verifier` (random), `code_challenge = BASE64URL(SHA256(verifier))`.
2. Redirect the browser to:
   ```
   {{base_url}}/o/authorize/?response_type=code
     &client_id=<id>
     &redirect_uri=https://myapp.example/callback
     &scope=openid%20email%20profile
     &state=<random>
     &code_challenge=<challenge>&code_challenge_method=S256
     &nonce=<random>
   ```
   The user signs in (`/accounts/login/`) and consents; the browser is redirected back with `?code=`.
3. Exchange the code:

   **POST** `{{base_url}}/o/token/`  (form-encoded)
   ```
   grant_type=authorization_code
   code=<code>
   redirect_uri=https://myapp.example/callback
   client_id=<id>
   code_verifier=<verifier>
   ```
   → `{ "access_token", "refresh_token", "id_token", "token_type": "Bearer", "expires_in", "scope" }`

   PKCE is **required** — a request without `code_challenge` is rejected.

## Client Credentials (service-to-service)

**POST** `{{base_url}}/o/token/`
```
grant_type=client_credentials
client_id=<id>
client_secret=<secret>
scope=read
```
→ `{ "access_token", "token_type": "Bearer", "expires_in", "scope" }`

## UserInfo

**GET** `{{base_url}}/o/userinfo/`  ·  Header: `Authorization: Bearer <access_token>`
→ `{ "sub", "email", "email_verified", "name", ... }` (claims gated by granted scopes).

## Notes
- **Access tokens are opaque** (validate via `/o/introspect/` or `/o/userinfo/`); the **id_token** is a
  JWT verifiable against `/o/.well-known/jwks.json`.
- Revoke: **POST** `{{base_url}}/o/revoke_token/`. The password (ROPC) grant is not supported.
