from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from logger import get_logger

app = FastAPI(title="Inventory Service")
logger = get_logger("inventory-service")

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
    if product_id not in INVENTORY_DB:
        logger.warning(f"Product {product_id} not found in inventory")
        raise HTTPException(status_code=404, detail="Product not found")

    return {"product_id": product_id, "stock": INVENTORY_DB[product_id]}


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
