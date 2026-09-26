import os
import json
import time
import uuid
import threading
import pika
from fastapi import FastAPI
from pydantic import BaseModel
from logger import get_logger
from tracer import setup_tracer

app = FastAPI(title="Notification Service")
tracer = setup_tracer("notification-service", app)
logger = get_logger("notification-service")

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")


def process_order_message(ch, method, properties, body):
    """Callback function triggered whenever RabbitMQ delivers a message."""
    try:
        data = json.loads(body.decode("utf-8"))
        notification_id = str(uuid.uuid4())
        
        logger.info(
            "Consumed notification event from RabbitMQ",
            extra={
                "notification_id": notification_id,
                "order_id": data.get("order_id"),
                "user_id": data.get("user_id"),
                "notification_body": data.get("message"),
            },
        )

        
        # Simulate processing (e.g. sending email / SMS)
        logger.info(
            "Notification successfully delivered to user",
            extra={"notification_id": notification_id, "order_id": data.get("order_id")},
        )
        
        # Acknowledge message (tells RabbitMQ it was handled successfully)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as exc:
        logger.error(f"Error processing notification: {exc}")
        # Reject message without requeueing to avoid poison-pill loops
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def run_rabbitmq_consumer():
    """Background loop that connects to RabbitMQ and consumes messages."""
    while True:
        try:
            logger.info("Connecting RabbitMQ consumer...", extra={"rabbitmq_url": RABBITMQ_URL})
            params = pika.URLParameters(RABBITMQ_URL)
            connection = pika.BlockingConnection(params)
            channel = connection.channel()
            
            channel.queue_declare(queue="order_notifications", durable=True)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue="order_notifications", on_message_callback=process_order_message)
            
            logger.info("RabbitMQ consumer started listening on 'order_notifications'")
            channel.start_consuming()
        except Exception as exc:
            logger.warning(f"RabbitMQ consumer connection lost, retrying in 5s: {exc}")
            time.sleep(5)



class NotificationRequest(BaseModel):
    order_id: str
    user_id: str
    message: str


class NotificationResponse(BaseModel):
    notification_id: str
    order_id: str
    status: str
    message: str

@app.on_event("startup")
def startup_event():
    consumer_thread = threading.Thread(target=run_rabbitmq_consumer, daemon=True)
    consumer_thread.start()
    logger.info("RabbitMQ consumer background thread started")


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
