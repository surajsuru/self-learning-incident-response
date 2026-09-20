import os
import uuid
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from logger import get_logger

app = FastAPI(title="Order Service")
logger = get_logger("order-service")

# Service URLs (configurable via environment variables)
INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://localhost:8002")
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://localhost:8003")
NOTIFICATION_SERVICE_URL = os.getenv("NOTIFICATION_SERVICE_URL", "http://localhost:8004")

# In-memory order store for Phase 1
ORDERS_DB = {}


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
async def get_order(order_id: str):
    if order_id not in ORDERS_DB:
        raise HTTPException(status_code=404, detail="Order not found")
    return ORDERS_DB[order_id]


@app.post("/orders", response_model=OrderResponse)
async def create_order(request: CreateOrderRequest):
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

        # Step 3: Trigger Notification (best-effort async event)
        notification_status = "pending"
        try:
            notif_resp = await client.post(
                f"{NOTIFICATION_SERVICE_URL}/notify",
                json={
                    "order_id": order_id,
                    "user_id": request.user_id,
                    "message": f"Order {order_id} placed successfully!",
                },
            )
            if notif_resp.status_code == 200:
                notification_status = "delivered"
        except httpx.RequestError as exc:
            logger.warning(f"Notification service could not be reached: {exc}", extra={"order_id": order_id})
            notification_status = "failed"

    # Save to memory
    order_record = {
        "order_id": order_id,
        "user_id": request.user_id,
        "product_id": request.product_id,
        "quantity": request.quantity,
        "amount": request.amount,
        "status": "completed",
        "details": {
            "payment_id": payment_data.get("payment_id"),
            "notification": notification_status,
        },
    }
    ORDERS_DB[order_id] = order_record

    logger.info(
        "Order completed successfully",
        extra={"order_id": order_id, "status": "completed"},
    )

    return OrderResponse(**order_record)
