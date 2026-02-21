# Logout All Sessions

**Method**: `POST`
**URL**: `{{base_url}}/api/auth/logout-all`

## Headers
- `Content-Type`: `application/json`
- `Authorization`: `Bearer {{access_token}}`

## Body
None

## Expected Response (200 OK)
```json
{
  "message": "Logged out of all sessions"
}
```
