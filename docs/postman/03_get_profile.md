# Get Current User Profile (Me)

**Method**: `GET`
**URL**: `{{base_url}}/api/auth/me`

## Headers
- `Content-Type`: `application/json`
- `Authorization`: `Bearer {{access_token}}`

## Body
None

## Expected Response (200 OK)
```json
{
  "id": 1,
  "email": "test@example.com",
  "first_name": "John",
  "last_name": "Doe",
  "is_email_verified": false
}
```
