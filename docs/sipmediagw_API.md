## SIP Media Gateway API Documentation

### Overview
The SIPMediaGW API provides endpoints to start, stop, and interact with a media gateway. The API requires Bearer token authentication.

### Authentication
All requests must include an `Authorization` header with a Bearer token:
```
Authorization: Bearer your_token_here
```

### Endpoints

#### Start Gateway
**Endpoint:** `GET /start`

Starts a new SIP media gateway instance.

**Parameters:**
- `room` (required): The room name.
- `from`: The 'from' field.
- `prefix`: The prefix to usefor SIP user name
- `domain`: The domain for WebRTC.
- `rtmpDst`: The RTMP destination.
- `dial`: The dial URI.
- `loop`: Loop option.

**Responses:**
- **200 OK**
  ```json
  {
    "status": "success",
    "details": {
      "res": "ok",
      "app": "baresip",
      "uri": "sip:user@domain"
    }
  }
  ```
- **400 Bad Request**
  ```json
  {
    "Error": "a room name must be specified"
  }
  ```
- **500 Internal Server Error**
  ```json
  {
    "Error": "Internal Server Error"
  }
  ```

#### Stop Gateway
**Endpoint:** `GET /stop`

Stops a running SIP media gateway instance.

**Parameters:**
- `room` (required): The room name.

**Responses:**
- **200 OK**
  ```json
  {
    "status": "success",
    "details": {
      "res": " Container gw0  Stopping =>  Container gw0  Stopped =>  Container gw0  Removing =>  Container gw0  Removed"
    }
  }
  ```
- **400 Bad Request**
  ```json
  {
    "Error": "a room name must be specified"
  }
  ```

#### Chat
**Endpoint:** `GET /chat`

Toggles chat in a specified room.

**Parameters:**
- `room` (required): The room name.
- `toggle` (required): Toggle parameter.

**Responses:**
- **200 OK**
  ```json
  {
    "status": "success",
    "details": {
      "res": "ok"
    }
  }
  ```
- **400 Bad Request**
  ```json
  {
    "Error": "a room name must be specified"
  }
  ```
  ```json
  {
    "Error": "toggle parameter is expected"
  }
  ```

**Endpoint:** `POST /chat`

Sends a chat message to a specified room.

**Request Body:**
```json
{
  "room": "room_name",
  "msg": "message"
}
```

**Responses:**
- **200 OK**
  ```json
  {
    "status": "success",
    "details": {
      "res": "ok"
    }
  }
  ```
- **400 Bad Request**
  ```json
  {
    "Error": "a room name must be specified"
  }
  ```
  ```json
  {
    "Error": "message missing or not readable"
  }
  ```

### Error Handling
- **401 Unauthorized**
  ```json
  {
    "Error": "authorization error"
  }
  ```
  
