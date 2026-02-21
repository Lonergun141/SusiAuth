# Request Password Reset (Forgot Password)

**Method**: `POST`
**URL**: `{{base_url}}/api/auth/forgot-password`

## Headers
- `Content-Type`: `application/json`

## Body (JSON)
```json
{
  "email": "test@example.com"
}
```

## Expected Response (200 OK)
```json
{
  "message": "If the account exists, we sent an email."
}
```
**Note**: Check the server console (since `EMAIL_BACKEND` is set to console) for the reset link and token.
