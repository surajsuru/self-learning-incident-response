import uuid
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from logger import get_logger
from tracer import setup_tracer
from prometheus_fastapi_instrumentator import Instrumentator
from chaos import setup_chaos

app = FastAPI(title="Payment Service")
setup_chaos(app)
tracer = setup_tracer("payment-service", app)
Instrumentator().instrument(app).expose(app)
logger = get_logger("payment-service")


class PaymentRequest(BaseModel):
    order_id: str
    user_id: str
    amount: float = Field(gt=0, description="Amount must be greater than zero")


class PaymentResponse(BaseModel):
    payment_id: str
    order_id: str
    amount: float
    status: str


@app.get("/health")
async def health():
    return {"service": "payment-service", "status": "healthy"}


@app.post("/payment/process", response_model=PaymentResponse)
async def process_payment(request: PaymentRequest):
    payment_id = str(uuid.uuid4())

    logger.info(
        "Processing payment",
        extra={
            "payment_id": payment_id,
            "order_id": request.order_id,
            "user_id": request.user_id,
            "amount": request.amount,
        },
    )

    # Simulated payment processing (successful by default)
    logger.info(
        "Payment successful",
        extra={
            "payment_id": payment_id,
            "order_id": request.order_id,
            "status": "completed",
        },
    )

    return PaymentResponse(
        payment_id=payment_id,
        order_id=request.order_id,
        amount=request.amount,
        status="successful",
    )
