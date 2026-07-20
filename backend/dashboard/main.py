"""FastAPI entry point for the SOC triage dashboard.

Run with:
    uv run uvicorn dashboard.main:app --reload --port 8000
or
    uv run python -m dashboard

Config (ports, origins, collection, stream name) is loaded from
``config/settings.yaml`` — no hardcoded values (backend_AGENTS.md rule 7).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dashboard.config_loader import cors_origins, load_config
from dashboard.routes import alerts, health, ws
from dashboard.services.redis_service import RedisStreamBridge

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("dashboard")


@asynccontextmanager
async def lifespan(app: FastAPI):
    bridge = RedisStreamBridge()
    app.state.bridge = bridge
    await bridge.start()
    logger.info("Dashboard Redis stream bridge started")
    try:
        yield
    finally:
        await bridge.stop()
        logger.info("Dashboard Redis stream bridge stopped")


app = FastAPI(
    title="SOC Triage Dashboard API",
    description="Stage-5 dashboard serving triage reports from Qdrant + Redis Streams",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(alerts.router, prefix="/api")
app.include_router(health.router, prefix="/api")
app.include_router(ws.router)


@app.get("/")
async def root() -> dict:
    return {"service": "soc-triage-dashboard", "docs": "/docs"}


def main() -> None:
    port = load_config()["dashboard"]["fastapi_port"]
    uvicorn.run("dashboard.main:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()