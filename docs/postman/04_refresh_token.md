# Refresh Access Token

**Method**: `POST`
**URL**: `{{base_url}}/api/auth/refresh`

## Headers
- `Content-Type`: `application/json`

## Body (JSON)
```json
{
  "refresh_token": "{{refresh_token}}"
}
```

## Expected Response (200 OK)
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "refresh_token": "..."
}
```
**Note**: This endpoint returns a *new* refresh token (Rotation). Update your saved `refresh_token` with the new one.
