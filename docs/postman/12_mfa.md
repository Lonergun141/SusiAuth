# MFA (TOTP)

Two-factor authentication using a TOTP authenticator app (Google Authenticator,
1Password, Authy, ...), with single-use recovery codes.

`{{access}}` is a bearer access token; `{{base_url}}` the API root.

---

## Enroll — begin

**POST** `{{base_url}}/api/auth/mfa/setup`  ·  Auth: `Bearer {{access}}`

### Response (200)
```json
{
  "secret": "JBSWY3DPEHPK3PXP",
  "otpauth_uri": "otpauth://totp/SusiAuth:user@example.com?secret=...&issuer=SusiAuth"
}
```
Render `otpauth_uri` as a QR code, or enter `secret` manually in the app. Not
active until confirmed.

---

## Enroll — confirm

**POST** `{{base_url}}/api/auth/mfa/confirm`  ·  Auth: `Bearer {{access}}`

```json
{ "code": "123456" }
```

### Response (200) — recovery codes are shown only once
```json
{ "recovery_codes": ["ab12-cd34-ef56", "..."] }
```

---

## Login with MFA

**POST** `{{base_url}}/api/auth/login` returns a challenge instead of tokens when
2FA is enabled:
```json
{ "mfa_required": true, "mfa_token": "<short-lived jwt>" }
```

Then exchange it:

**POST** `{{base_url}}/api/auth/mfa/verify`  ·  no auth
```json
{ "mfa_token": "<from login>", "code": "123456" }
```
`code` may be a TOTP code **or** a recovery code.

### Response (200)
```json
{ "access_token": "<jwt>", "refresh_token": "<opaque>" }
```
- **401** — invalid/expired challenge or wrong code

---

## Status

**GET** `{{base_url}}/api/auth/mfa/status`  ·  Auth: `Bearer {{access}}`
```json
{ "enabled": true, "recovery_codes_remaining": 9 }
```

## Disable / regenerate recovery codes

**POST** `{{base_url}}/api/auth/mfa/disable`  ·  Auth: `Bearer {{access}}`
**POST** `{{base_url}}/api/auth/mfa/recovery-codes`  ·  Auth: `Bearer {{access}}`

Both require re-authentication:
```json
{ "password": "current-password", "code": "123456" }
```
- `disable` → `{"message": "MFA disabled"}`
- `recovery-codes` → a fresh `{"recovery_codes": [...]}` (old codes invalidated)
