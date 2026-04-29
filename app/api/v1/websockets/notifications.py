from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import List, Dict
from app.core.logger import get_logger

logger = get_logger(__name__)

class ConnectionManager:
    """
    Manages WebSocket connections for real-time status updates.
    """
    def __init__(self):
        # Maps user_id to a list of active WebSocket connections
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        logger.info(f"WebSocket: User {user_id} connected. Active: {len(self.active_connections[user_id])}")

    def disconnect(self, websocket: WebSocket, user_id: int):
        if user_id in self.active_connections:
            self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        logger.info(f"WebSocket: User {user_id} disconnected.")

    async def send_personal_message(self, message: dict, user_id: int):
        if user_id in self.active_connections:
            for connection in self.active_connections[user_id]:
                await connection.send_json(message)

manager = ConnectionManager()

router = APIRouter()

@router.websocket("/ws/kyc-status/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    """
    WebSocket endpoint for real-time KYC status updates.
    """
    await manager.connect(websocket, user_id)
    try:
        while True:
            # Keep connection alive; wait for client messages if any
            data = await websocket.receive_text()
            # For now, we just echo or ignore. The server-to-client notifications
            # happen via the manager.send_personal_message call in KYCService.
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
