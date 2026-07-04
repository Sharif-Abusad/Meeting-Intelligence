"""
FastAPI application entry point.

Run with:

    uvicorn api.main:app --reload --port 8000

Then point your Streamlit frontend at http://localhost:8000/api.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import ensure_directories
from app.core.exceptions import MeetingIntelligenceError
from app.core.logging_config import configure_logging
from app.api.routes import router

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Meeting Intelligence API",
    description="Transcribe, summarize, and query meeting recordings.",
    version="1.0.0",
)

# Streamlit typically runs on a different origin/port (e.g. localhost:8501).
# Restrict this to your actual frontend origin(s) in production.
_ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
async def on_startup() -> None:
    ensure_directories()
    logger.info("Meeting Intelligence API started.")


@app.exception_handler(MeetingIntelligenceError)
async def handle_pipeline_error(request: Request, exc: MeetingIntelligenceError) -> JSONResponse:
    logger.warning("Unhandled pipeline error on %s: %s", request.url.path, exc)
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.get("/")
def root():
    return {"message": "Welcome to my API"}


@app.get("/api/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok"}
