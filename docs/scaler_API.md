## Scaler API Documentation

### Overview
The SIP Media Gateway Scaler API provides endpoints to manage scaling operations for media gateways. The API requires Bearer token authentication.

### Authentication
All requests must include an `Authorization` header with a Bearer token:
```
Authorization: Bearer your_token_here
```

### Endpoints

#### Scale Gateway
**Endpoint:** `GET /scale`

Scales the SIP media gateway instance.

**Parameters:**
- `auto` (optional): Triggers an automatic scaling operation.
- `up` (optional): Triggers a scaling up operation.
- `roomId`: The room ID (optional).
- `dialOut`: The dial-out parameter (optional).

**Responses:**
- **200 OK**
  ```json
  {
    "status": "success",
    "message": "The scaler iteration succeed"
  }
  ```
  ```json
  {
    "status": "success",
    "instance": {
      "id":instanceId,
      "ip":pubIp
    }
  }
  ```
- **400 Bad Request**
  ```json
  {
    "Error": "Missing required parameters"
  }
  ```
- **500 Internal Server Error**
  ```json
  {
    "Error": "The scaler iteration failed: error details"
  }
  ```
  ```json
  {
    "Error": "Instance creation failed: error details"
  }
  ```

### Error Handling
- **401 Unauthorized**
  ```json
  {
    "Error": "authorization error"
  }
  ```

