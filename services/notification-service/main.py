import uuid
from fastapi import FastAPI
from pydantic import BaseModel
from logger import get_logger

app = FastAPI(title="Notification Service")
logger = get_logger("notification-service")


class NotificationRequest(BaseModel):
    order_id: str
    user_id: str
    message: str


class NotificationResponse(BaseModel):
    notification_id: str
    order_id: str
    status: str
    message: str


@app.get("/health")
async def health():
    return {"service": "notification-service", "status": "healthy"}


@app.post("/notify", response_model=NotificationResponse)
async def send_notification(request: NotificationRequest):
    notification_id = str(uuid.uuid4())

    logger.info(
        "Sending notification",
        extra={
            "notification_id": notification_id,
            "order_id": request.order_id,
            "user_id": request.user_id,
        }
    )

    # Simulated send — in a real system this would call email/SMS/push
    logger.info(
        "Notification delivered",
        extra={
            "notification_id": notification_id,
            "order_id": request.order_id,
        }
    )

    return NotificationResponse(
        notification_id=notification_id,
        order_id=request.order_id,
        status="delivered",
        message=request.message,
    )
