import os
import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from logger import get_logger
from tracer import setup_tracer
from prometheus_fastapi_instrumentator import Instrumentator



app = FastAPI(title="API Gateway")
tracer = setup_tracer("api-gateway", app)
Instrumentator().instrument(app).expose(app)
logger = get_logger("api-gateway")

ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://localhost:8001")
INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://localhost:8002")


class OrderCreate(BaseModel):
    user_id: str
    product_id: str
    quantity: int
    amount: float


@app.get("/health")
async def health():
    # Ping downstream services to check full system health
    services_status = {}
    async with httpx.AsyncClient(timeout=2.0) as client:
        for name, url in [("order_service", ORDER_SERVICE_URL), ("inventory_service", INVENTORY_SERVICE_URL)]:
            try:
                res = await client.get(f"{url}/health")
                services_status[name] = "reachable" if res.status_code == 200 else "unhealthy"
            except Exception:
                services_status[name] = "unreachable"

    return {"service": "api-gateway", "status": "healthy", "downstream": services_status}


@app.post("/orders")
async def create_order(order: OrderCreate):
    logger.info("Forwarding order creation to order-service", extra={"product_id": order.product_id})
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(f"{ORDER_SERVICE_URL}/orders", json=order.model_dump())
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=resp.json().get("detail", "Order failed"))
            return resp.json()
        except httpx.RequestError as exc:
            logger.error(f"Cannot reach order-service: {exc}")
            raise HTTPException(status_code=503, detail="Order service unreachable")


@app.get("/inventory/{product_id}")
async def get_inventory(product_id: str):
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            resp = await client.get(f"{INVENTORY_SERVICE_URL}/inventory/{product_id}")
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail="Product not found")
            return resp.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=503, detail="Inventory service unreachable")
