# Login

**Method**: `POST`
**URL**: `{{base_url}}/api/auth/login`

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
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "refresh_token": "..."
}
```

## Post-Request Script (Optional)
Save tokens to variables:
```javascript
var jsonData = pm.response.json();
pm.environment.set("access_token", jsonData.access_token);
pm.environment.set("refresh_token", jsonData.refresh_token);
```
