import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse

from app.api.v1.tasks import router as tasks_router
from app.core.config import settings
from app.core.logger import get_logger, setup_logger

setup_logger()
logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Application starting up", env=settings.llm_provider)
    yield
    logger.info("Application shutting down")

app = FastAPI(
    title="Web Discovery Agent API",
    description="Professional API for autonomous web discovery and structured extraction",
    version="0.1.0",
    lifespan=lifespan,
)

@app.middleware("http")
async def add_request_id_and_log(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    # Can bind request_id to context vars for structured logging here
    logger.info(f"Incoming request {request.method} {request.url.path}", request_id=request_id)

    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception as exc:
        logger.error(f"Unhandled error in request {request_id}", error=str(exc), exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id}
        )

app.include_router(tasks_router, prefix="/api/v1")

@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "version": "0.1.0"}

@app.get('/', include_in_schema=False)
async def serve_dashboard() -> FileResponse:
    import os
    index_path = os.path.join(os.path.dirname(__file__), 'frontend', 'index.html')
    return FileResponse(index_path)

