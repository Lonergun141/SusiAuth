# Login

**Method**: `POST`
**URL**: `{{base_url}}/api/v1/auth/login`

## Headers
- `Content-Type`: `application/json`

## Body (JSON)
```json
{
  "email": "test@example.com",
  "password": "StrongPassword123!"
}
```

## Expected Response (200 OK)
```json
{
  "mfa_required": false,
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "refresh_token": "..."
}
```

### If MFA is enabled (200 OK)
No tokens yet — complete the challenge (see `12_mfa.md`):
```json
{
  "mfa_required": true,
  "mfa_token": "<short-lived jwt>"
}
```

## Post-Request Script (Optional)
Save tokens to variables:
```javascript
var jsonData = pm.response.json();
pm.environment.set("access_token", jsonData.access_token);
pm.environment.set("refresh_token", jsonData.refresh_token);
```
