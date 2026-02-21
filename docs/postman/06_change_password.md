# Change Password

**Method**: `POST`
**URL**: `{{base_url}}/api/auth/change-password`

## Headers
- `Content-Type`: `application/json`
- `Authorization`: `Bearer {{access_token}}`

## Body (JSON)
```json
{
  "current_password": "StrongPassword123!",
  "new_password": "NewSecurePass456!",
  "confirm_new_password": "NewSecurePass456!"
}
```

## Expected Response (200 OK)
```json
{
  "message": "Password changed"
}
```
