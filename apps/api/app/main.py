import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.asset_csv_routes import router as asset_csv_router
from app.asset_routes import router as asset_router
from app.catalog_routes import router as catalog_router
from app.config import get_settings
from app.image_routes import router as image_router
from app.logging_config import configure_logging
from app.openapi import catalog_openapi
from app.routes import router
from app.security import validate_csrf

configure_logging(get_settings().log_level)
logger = logging.getLogger("assetvision")
app = FastAPI(title="AssetVision IT", version="0.1.0", dependencies=[Depends(validate_csrf)])
app.include_router(router)
app.include_router(catalog_router)
app.include_router(asset_csv_router)
app.include_router(asset_router)
app.include_router(image_router)
app.openapi = lambda: catalog_openapi(app)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Validation errors may contain passwords: expose only safe metadata.
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {"loc": error["loc"], "type": error["type"], "msg": error["msg"]}
                for error in exc.errors()
            ]
        },
    )


@app.middleware("http")
async def request_logging(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = str(uuid.uuid4())
    started = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        # Never serialize exceptions, SQL parameters, headers, or request bodies.
        logger.error("request_failed", extra={"context": {"request_id": request_id}})
        response = JSONResponse(status_code=500, content={"detail": "Internal server error"})
    response.headers["X-Request-ID"] = request_id
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    logger.info(
        "request_completed",
        extra={
            "context": {
                "request_id": request_id,
                "method": request.method,
                "route": getattr(request.scope.get("route"), "path", "unmatched"),
                "status": response.status_code,
                "duration_ms": round((time.monotonic() - started) * 1000),
            }
        },
    )
    return response
