import os
import uuid
import json
import pika
import httpx
from pydantic import BaseModel, Field
from logger import get_logger
from tracer import setup_tracer
from prometheus_fastapi_instrumentator import Instrumentator
from chaos import setup_chaos
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from database import init_db, get_db, OrderModel


RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")

def publish_order_notification(notification_data: dict):
    """Publish an order notification event to RabbitMQ queue."""
    try:
        params = pika.URLParameters(RABBITMQ_URL)
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        
        # Declare durable queue so messages survive broker restarts
        channel.queue_declare(queue="order_notifications", durable=True)
        
        channel.basic_publish(
            exchange="",
            routing_key="order_notifications",
            body=json.dumps(notification_data),
            properties=pika.BasicProperties(delivery_mode=2),  # Persistent message
        )
        connection.close()
        logger.info("Published notification event to RabbitMQ", extra={"order_id": notification_data.get("order_id")})
        return True
    except Exception as exc:
        logger.warning(f"Failed to publish notification event to RabbitMQ: {exc}", extra={"order_id": notification_data.get("order_id")})
        return False


app = FastAPI(title="Order Service")
setup_chaos(app)
tracer = setup_tracer("order-service", app)
Instrumentator().instrument(app).expose(app)
logger = get_logger("order-service")

@app.on_event("startup")
def on_startup():
    try:
        init_db()
        logger.info("PostgreSQL database tables initialized successfully")
    except Exception as exc:
        logger.error(f"Failed to initialize database: {exc}")


# Service URLs (configurable via environment variables)
INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://localhost:8002")
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://localhost:8003")
NOTIFICATION_SERVICE_URL = os.getenv("NOTIFICATION_SERVICE_URL", "http://localhost:8004")

# In-memory order store for Phase 1
# ORDERS_DB = {}


class CreateOrderRequest(BaseModel):
    user_id: str
    product_id: str
    quantity: int = Field(gt=0, description="Quantity must be greater than zero")
    amount: float = Field(gt=0, description="Total amount must be greater than zero")


class OrderResponse(BaseModel):
    order_id: str
    user_id: str
    product_id: str
    quantity: int
    amount: float
    status: str
    details: dict


@app.get("/health")
async def health():
    return {"service": "order-service", "status": "healthy"}


@app.get("/orders/{order_id}")
async def get_order(order_id: str, db: Session = Depends(get_db)):
    order = db.query(OrderModel).filter(OrderModel.order_id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return {
        "order_id": order.order_id,
        "user_id": order.user_id,
        "product_id": order.product_id,
        "quantity": order.quantity,
        "amount": order.amount,
        "status": order.status,
        "details": order.details,
    }



@app.post("/orders", response_model=OrderResponse)
async def create_order(request: CreateOrderRequest, db: Session = Depends(get_db)):
    order_id = str(uuid.uuid4())
    logger.info(
        "Creating new order",
        extra={
            "order_id": order_id,
            "user_id": request.user_id,
            "product_id": request.product_id,
            "quantity": request.quantity,
        },
    )

    async with httpx.AsyncClient(timeout=5.0) as client:
        # Step 1: Reserve Inventory
        try:
            inv_resp = await client.post(
                f"{INVENTORY_SERVICE_URL}/inventory/reserve",
                json={"product_id": request.product_id, "quantity": request.quantity},
            )
            if inv_resp.status_code != 200:
                logger.error(
                    "Failed to reserve inventory",
                    extra={"order_id": order_id, "status_code": inv_resp.status_code, "detail": inv_resp.text},
                )
                raise HTTPException(
                    status_code=inv_resp.status_code,
                    detail=f"Inventory error: {inv_resp.json().get('detail', 'Unknown error')}",
                )
        except httpx.RequestError as exc:
            logger.error(f"Cannot reach inventory service: {exc}", extra={"order_id": order_id})
            raise HTTPException(status_code=503, detail="Inventory service unreachable")

        # Step 2: Process Payment
        try:
            pay_resp = await client.post(
                f"{PAYMENT_SERVICE_URL}/payment/process",
                json={"order_id": order_id, "user_id": request.user_id, "amount": request.amount},
            )
            if pay_resp.status_code != 200:
                logger.error(
                    "Payment failed",
                    extra={"order_id": order_id, "status_code": pay_resp.status_code, "detail": pay_resp.text},
                )
                raise HTTPException(
                    status_code=pay_resp.status_code,
                    detail=f"Payment error: {pay_resp.json().get('detail', 'Payment failed')}",
                )
            payment_data = pay_resp.json()
        except httpx.RequestError as exc:
            logger.error(f"Cannot reach payment service: {exc}", extra={"order_id": order_id})
            raise HTTPException(status_code=503, detail="Payment service unreachable")

        # Step 3: Publish Notification Event to RabbitMQ (Asynchronous & Decoupled)
        notif_payload = {
            "order_id": order_id,
            "user_id": request.user_id,
            "message": f"Order {order_id} placed successfully!",
        }
        published = publish_order_notification(notif_payload)
        notification_status = "queued" if published else "publish_failed"


    # Save to PostgreSQL
    new_order = OrderModel(
        order_id=order_id,
        user_id=request.user_id,
        product_id=request.product_id,
        quantity=request.quantity,
        amount=request.amount,
        status="completed",
        details={
            "payment_id": payment_data.get("payment_id"),
            "notification": notification_status,
        },
    )
    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    logger.info(
        "Order persisted to database successfully",
        extra={"order_id": order_id, "status": "completed"},
    )

    return OrderResponse(
        order_id=new_order.order_id,
        user_id=new_order.user_id,
        product_id=new_order.product_id,
        quantity=new_order.quantity,
        amount=new_order.amount,
        status=new_order.status,
        details=new_order.details,
    )
