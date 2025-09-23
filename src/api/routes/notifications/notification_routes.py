from fastapi import APIRouter, WebSocket, WebSocketDisconnect,Request,Depends
from src.utils.logger import logger
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from src.utils.response_utils import success, error, created
from src.api.schema.notification_schema import NotificationBase
from src.api.database.database import get_db
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.routes.notifications.controller import ConnectionController
from src.api.models.notificaton_model import Notification
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    WrextExternalServiceException,
    WrextValidationException,
    WrextAuthenticationException
)

controller = ConnectionController()
router = APIRouter(
    prefix="/notifications",
    tags=["notifications"],
    responses={404: {"description": "Not found"}},
)

@router.get("/")
def get():
    return success("Notification service is up and running")

import asyncio
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await controller.connect(websocket)
    try:
        while True:
            # await websocket.send_json({"action": "ping"})
            # await asyncio.sleep(30)
                # keep connection alive
                data = await websocket.receive_text()
                logger.info(f"Received from client:")
                await websocket.send_text(f"Message text was: {data}")
                
    except WebSocketDisconnect:
        logger.info("Client disconnected")
    finally:
        controller.disconnect(websocket)

@router.get("/all")
def get_all_notifications(
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        notifications = db.query(Notification).all()
        notifications_data = [notification.to_dict() for notification in notifications]
        return success("Notifications retrieved successfully", data=notifications_data)
    except Exception as e:
        return {
            "error":str(e)
        }
    

@router.post("/create")
async def create_notification(
    request: Request,
    data: NotificationBase,
    db: Session = Depends(get_db)
):
    try:
        new_notification = Notification(
            title=data.title,
            description=data.description,
            notification_type=data.notification_type
        )
        db.add(new_notification)
        db.commit()
        db.refresh(new_notification)

        # Broadcast via WebSocket
        logger.info("Broadcasting new notification via WebSocket")
        await controller.broadcast({
            "action": "new_notification",
            "data": new_notification.to_dict()
        })
        logger.info("Broadcast complete")
        
        return success("Notification created successfully", data=new_notification.to_dict())
    except Exception as e:
        return {
            "error":str(e)
        }