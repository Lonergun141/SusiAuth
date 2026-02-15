# Register User

**Method**: `POST`
**URL**: `{{base_url}}/api/auth/register`

## Headers
- `Content-Type`: `application/json`

## Body (JSON)
```json
{
  "email": "test@example.com",
  "password": "StrongPassword123!",
  "confirm_password": "StrongPassword123!",
  "first_name": "John",
  "last_name": "Doe"
}
```

## Expected Response (201 Created)
```json
{
  "message": "Registered. Please verify your email."
}
```
