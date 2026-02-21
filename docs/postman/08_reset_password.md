# Reset Password

**Method**: `POST`
**URL**: `{{base_url}}/api/auth/reset-password`

## Headers
- `Content-Type`: `application/json`

## Body (JSON)
```json
{
  "token": "<token_from_console_log>",
  "new_password": "NewSecurePass456!",
  "confirm_new_password": "NewSecurePass456!"
}
```

## Expected Response (200 OK)
```json
{
  "message": "Password reset successful"
}
```
