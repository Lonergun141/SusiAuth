# Logout

**Method**: `POST`
**URL**: `{{base_url}}/api/auth/logout`

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
  "message": "Logged out"
}
```
