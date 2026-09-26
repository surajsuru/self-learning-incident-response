import asyncio
import random
from fastapi import Request, HTTPException, FastAPI
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware


class ChaosState:
    """Holds active fault injection parameters in memory."""
    def __init__(self):
        self.latency_seconds: float = 0.0
        self.error_rate: float = 0.0
        self.error_code: int = 500

    def reset(self):
        self.latency_seconds = 0.0
        self.error_rate = 0.0
        self.error_code = 500

    def to_dict(self):
        return {
            "latency_seconds": self.latency_seconds,
            "error_rate": self.error_rate,
            "error_code": self.error_code,
            "active": self.latency_seconds > 0 or self.error_rate > 0
        }


chaos_state = ChaosState()


class ChaosConfigRequest(BaseModel):
    latency_seconds: float = Field(0.0, ge=0.0, description="Delay in seconds to inject")
    error_rate: float = Field(0.0, ge=0.0, le=1.0, description="Probability of requests to fail (0.0 to 1.0)")
    error_code: int = Field(500, description="HTTP status code to return when failing")


class ChaosMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Never inject faults into internal observability or chaos management endpoints
        path = request.url.path
        if path.startswith("/chaos") or path in ["/health", "/metrics", "/docs", "/openapi.json"]:
            return await call_next(request)

        # 1. Inject Latency
        if chaos_state.latency_seconds > 0:
            await asyncio.sleep(chaos_state.latency_seconds)

        # 2. Inject Errors
        if chaos_state.error_rate > 0:
            if random.random() < chaos_state.error_rate:
                raise HTTPException(
                    status_code=chaos_state.error_code,
                    detail=f"Simulated Incident Fault (HTTP {chaos_state.error_code})"
                )

        return await call_next(request)


def setup_chaos(app: FastAPI):
    """Adds the ChaosMiddleware and management routes (/chaos/inject, /chaos/reset, /chaos/status) to FastAPI."""
    app.add_middleware(ChaosMiddleware)

    @app.post("/chaos/inject", tags=["Chaos Engineering"])
    async def inject_fault(config: ChaosConfigRequest):
        chaos_state.latency_seconds = config.latency_seconds
        chaos_state.error_rate = config.error_rate
        chaos_state.error_code = config.error_code
        return {"status": "fault_injected", "config": chaos_state.to_dict()}

    @app.post("/chaos/reset", tags=["Chaos Engineering"])
    async def reset_fault():
        chaos_state.reset()
        return {"status": "reset", "config": chaos_state.to_dict()}

    @app.get("/chaos/status", tags=["Chaos Engineering"])
    async def get_status():
        return chaos_state.to_dict()
