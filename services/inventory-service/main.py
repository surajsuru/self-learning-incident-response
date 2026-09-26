import os
import redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from logger import get_logger
from tracer import setup_tracer
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(title="Inventory Service")
tracer = setup_tracer("inventory-service", app)
Instrumentator().instrument(app).expose(app)
logger = get_logger("inventory-service")

# Redis connection
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
try:
    redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
    redis_client.ping()
    logger.info("Connected to Redis successfully", extra={"redis_url": REDIS_URL})
except Exception as e:
    redis_client = None
    logger.warning("Could not connect to Redis, running with in-memory fallback", extra={"error": str(e)})


# Simulated in-memory inventory store for Phase 1
INVENTORY_DB = {
    "prod-1": 100,
    "prod-2": 50,
    "prod-3": 0,  # Out of stock
}


class ReserveRequest(BaseModel):
    product_id: str
    quantity: int


class ReserveResponse(BaseModel):
    product_id: str
    quantity: int
    remaining_stock: int
    status: str


@app.get("/health")
async def health():
    return {"service": "inventory-service", "status": "healthy"}


@app.get("/inventory/{product_id}")
async def get_stock(product_id: str):
    cache_key = f"inventory:{product_id}"

    # 1. Try reading from Redis (Cache Hit)
    if redis_client:
        try:
            cached_stock = redis_client.get(cache_key)
            if cached_stock is not None:
                logger.info("Cache hit for inventory", extra={"product_id": product_id, "stock": int(cached_stock)})
                return {"product_id": product_id, "stock": int(cached_stock), "source": "cache"}
        except Exception as e:
            logger.warning("Redis read error, falling back to database", extra={"error": str(e)})

    # 2. Cache Miss: check source of truth
    if product_id not in INVENTORY_DB:
        logger.warning(f"Product {product_id} not found in inventory")
        raise HTTPException(status_code=404, detail="Product not found")

    stock = INVENTORY_DB[product_id]

    # 3. Store in Redis cache for 60 seconds TTL
    if redis_client:
        try:
            redis_client.setex(cache_key, 60, stock)
        except Exception as e:
            logger.warning("Redis write error", extra={"error": str(e)})

    return {"product_id": product_id, "stock": stock, "source": "db"}


@app.post("/inventory/reserve", response_model=ReserveResponse)
async def reserve_stock(request: ReserveRequest):
    logger.info(
        "Attempting stock reservation",
        extra={"product_id": request.product_id, "quantity": request.quantity},
    )

    if request.product_id not in INVENTORY_DB:
        logger.warning(
            "Product not found during reservation",
            extra={"product_id": request.product_id},
        )
        raise HTTPException(status_code=404, detail="Product not found")

    current_stock = INVENTORY_DB[request.product_id]

    if current_stock < request.quantity:
        logger.warning(
            "Insufficient stock",
            extra={
                "product_id": request.product_id,
                "requested": request.quantity,
                "available": current_stock,
            },
        )
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient stock. Available: {current_stock}, Requested: {request.quantity}",
        )

    # Deduct stock
    INVENTORY_DB[request.product_id] -= request.quantity
    remaining = INVENTORY_DB[request.product_id]

    # Invalidate/Update Redis cache with new remaining stock
    if redis_client:
        try:
            redis_client.setex(f"inventory:{request.product_id}", 60, remaining)
        except Exception as e:
            logger.warning("Failed to update Redis cache after reservation", extra={"error": str(e)})


    logger.info(
        "Stock reserved successfully",
        extra={
            "product_id": request.product_id,
            "reserved": request.quantity,
            "remaining_stock": remaining,
        },
    )

    return ReserveResponse(
        product_id=request.product_id,
        quantity=request.quantity,
        remaining_stock=remaining,
        status="reserved",
    )
