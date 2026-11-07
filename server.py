"""
Connected Campus chat server (FastAPI + WebSockets):

Adapted from Activity 08. The key difference:
  * Activity 08 BROADCAST every message to every connected client
  * Here each client connects as ONE user (/ws/{user_id}) and the server ROUTES
    each message only to the user it is addressed to

Wire format (every frame is JSON text):
  client -> server : {"type": "message", "to": "u2", "payload": {...}}
  server -> client : {"type": "message", "from": "u1", "payload": {...}}
  server -> client : {"type": "error", "detail": "..."}      (only for bad frames)

The server doesn't look at type/payload, so later features (connection
requests, location-sharing updates) can reuse the same route with no server changes

Midterm Scope: there is no login. User id in the URL is trusted
The final project will replace that with token-based auth (see proposal, Future Work)
"""

import json
from collections import defaultdict, deque
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import List

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_FRAME_CHARS = 64_000        # reject absurdly large frames
MAX_QUEUED_PER_USER = 100       # messages held for a user who is offline

class ConnectionManager:
    # Keeps track of which sockets belong to which user

    def __init__(self) -> None:
        # One user may be connected from several devices, so each user maps to a SET of sockets
        self.connections: dict[str, set[WebSocket]] = defaultdict(set)
        
        # Frames addressed to users who are offline deliver when they reconnect
        # (In memory only, lost if the server restarts)
        self.offline_queue: dict[str, deque[str]] = defaultdict(
            lambda: deque(maxlen=MAX_QUEUED_PER_USER)
        )

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections[user_id].add(websocket)
        print(f"[connect] {user_id} (devices: {len(self.connections[user_id])})")

        # Deliver anything that arrived while user was offline
        queued = self.offline_queue.pop(user_id, None)
        for frame in queued or []:
            await websocket.send_text(frame)

    def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        sockets = self.connections.get(user_id)
        if sockets is None:
            return
        sockets.discard(websocket)
        if not sockets:
            del self.connections[user_id]
        print(f"[disconnect] {user_id}")

    async def send_to(self, user_id: str, frame: str) -> bool:
        # Send a frame to every device of `user_id` & queue it if they're offline
        # Returns True if at least one device received it
        delivered = False
        for socket in list(self.connections.get(user_id, ())):
            try:
                await socket.send_text(frame)
                delivered = True
            except Exception as error:  # a dead socket: drop it and keep going
                print(f"[send error] {user_id}: {error}")
                self.disconnect(user_id, socket)
        if not delivered:
            self.offline_queue[user_id].append(frame)
        return delivered

manager = ConnectionManager()

async def send_error(websocket: WebSocket, detail: str) -> None:
    # Send validation or processing problems back to this client as a JSON frame.
    await websocket.send_text(json.dumps({"type": "error", "detail": detail}))

async def handle_frame(sender_id: str, raw: str, websocket: WebSocket) -> None:
    # Validate one incoming frame & forward it to recipient
    # Reject oversized inputs before parsing it
    if len(raw) > MAX_FRAME_CHARS:
        await send_error(websocket, "Frame too large.")
        return

    # Decode JSON & read fields needed to route message
    try:
        frame = json.loads(raw)
        kind, recipient = frame["type"], frame["to"]
    except (json.JSONDecodeError, KeyError, TypeError):
        await send_error(websocket, "Frame must be a JSON object with 'type' and 'to'.")
        return

    # Ensure routing fields are usable before sending
    if not isinstance(kind, str) or not isinstance(recipient, str) or not recipient:
        await send_error(websocket, "'type' and 'to' must be non-empty strings.")
        return

    # from is set by SERVER from connection (never copied from client)
    # Ensures one user can't pretend to be another
    outgoing = json.dumps(
        {"type": kind, "from": sender_id, "payload": frame.get("payload")}
    )
    # Deliver to all recipient's connected devices/queue if offline
    delivered = await manager.send_to(recipient, outgoing)
    # Log route & if any connected device received the frame
    print(f"[route] {sender_id} -> {recipient} ({kind}) delivered={delivered}")

@app.get("/")
async def health():
    # Render pings endpoint to check if service is alive
    # Returns status & number of users currently connected
    return {"status": "ok", "usersOnline": len(manager.connections)}

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    # Handle user's connection & route frames till disconnect
    # Accept socket, register it to user, and deliver queued frames
    await manager.connect(user_id, websocket)
    try:
        # Keep receiving text frames & pass each to validation/router
        while True:
            raw = await websocket.receive_text()
            await handle_frame(user_id, raw, websocket)
    except WebSocketDisconnect:
        # Disconnect ends user's receive loop
        pass
    finally:
        # Remove socket if disconnected normally/raised an error
        manager.disconnect(user_id, websocket)
