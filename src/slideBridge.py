"""slideBridge.py — WebSocket to MJPEG bridge

Lightweight bridge: receive binary frames over WebSocket and
serve them as an MJPEG multipart stream.
"""

import asyncio
from aiohttp import web, WSMsgType

BOUNDARY = "frame"
lastFrame = None

async def wsHandler(request):
    """Handle incoming WebSocket connections and store last frame."""
    global lastFrame
    wsConnection = web.WebSocketResponse()
    await wsConnection.prepare(request)
    print("browser connected", flush=True)

    async for msg in wsConnection:
        if msg.type == WSMsgType.BINARY:
            lastFrame = msg.data
        elif msg.type == WSMsgType.ERROR:
            print(f"ws error: {wsConnection.exception()}", flush=True)

    print("browser disconnected", flush=True)
    return wsConnection

async def mjpegHandler(request):
    """Stream the latest frame as an MJPEG multipart response."""
    streamResponse = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": f"multipart/x-mixed-replace; boundary={BOUNDARY}",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    await streamResponse.prepare(request)

    try:
        while True:
            if lastFrame is not None:
                partHeader = (
                    f"--{BOUNDARY}\r\n"
                    f"Content-Type: image/jpeg\r\n"
                    f"Content-Length: {len(lastFrame)}\r\n\r\n"
                ).encode()
                await streamResponse.write(partHeader)
                await streamResponse.write(lastFrame)
                await streamResponse.write(b"\r\n")
            await asyncio.sleep(0.2)  # approx 5 fps
    except (ConnectionResetError, asyncio.CancelledError):
        pass

    return streamResponse


app = web.Application()
app.router.add_get("/ws", wsHandler)
app.router.add_get("/", mjpegHandler)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=8080)
