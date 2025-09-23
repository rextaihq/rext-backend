from typing import List
from fastapi import WebSocket
from src.utils.logger import logger

class ConnectionController:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        logger.info("New WebSocket connection")
        logger.info(f"Current connections before adding: {len(self.active_connections)}")
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Current connections after adding: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            logger.info("WebSocket disconnected")
            self.active_connections.remove(websocket)

    async def send_notification(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)


    async def broadcast(self, message: dict):
        logger.info(f"Broadcasting message to {len(self.active_connections)} connections")
        disconnected = []
        for connection in self.active_connections.copy():
            try:
                logger.info(f"Sending {message} to connection {connection}")
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send message, marking as disconnected: {e}")
                disconnected.append(connection)

        # Remove disconnected websockets
        for conn in disconnected:
            self.disconnect(conn)