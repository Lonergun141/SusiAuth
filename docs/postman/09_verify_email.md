# Verify Email

**Method**: `POST`
**URL**: `{{base_url}}/api/auth/verify-email`

## Headers
- `Content-Type`: `application/json`

## Body (JSON)
```json
{
  "token": "<token_from_console_log>"
}
```

## Expected Response (200 OK)
```json
{
  "message": "Email verified"
}
```
**Note**: The registration endpoint prints a verification link/token to the console (when using Console Email Backend). Use that token here.
