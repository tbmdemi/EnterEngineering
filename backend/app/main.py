import logging

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .core.config import Settings
from .core.errors import AppError
from .core import services
from .dependencies import require_demo_role
from .features.compliance.router import router as compliance_router
from .features.coordination import router as coordination_router
from .features.documentation_ai import router as documentation_ai_router
from .features.encounter.router import router as encounter_router
from .features.pre_treatment import router as pre_treatment_router
from .features.post_treatment_chat import router as post_treatment_chat_router


logger = logging.getLogger("careguard.api")
settings = Settings.from_environment()
app = FastAPI(
    title="CareGuard Dental Demo",
    docs_url="/docs" if settings.enable_api_docs else None,
    redoc_url="/redoc" if settings.enable_api_docs else None,
    openapi_url="/openapi.json" if settings.enable_api_docs else None,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
if settings.allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["Content-Type", "X-Demo-Role", "X-Demo-Access-Token"],
    )
app.include_router(compliance_router)
app.include_router(coordination_router)
app.include_router(documentation_ai_router)
app.include_router(encounter_router)
app.include_router(pre_treatment_router)
app.include_router(post_treatment_chat_router)


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, error: AppError):
    return JSONResponse(status_code=error.status_code, content=error.payload)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, error: RequestValidationError):
    return JSONResponse(status_code=422, content={"code": "VALIDATION_ERROR", "message": "Request validation failed", "details": {"error_count": len(error.errors())}})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, error: Exception):
    logger.exception("Unhandled API error", extra={"method": request.method, "path": request.url.path}, exc_info=error)
    return JSONResponse(status_code=500, content={"code": "INTERNAL_ERROR", "message": "Unexpected server error", "details": {}})


@app.get("/api/health/live", include_in_schema=False)
def liveness():
    return {"status": "ok"}


@app.get("/api/health/ready", include_in_schema=False)
def readiness():
    try:
        with services._connect() as connection:
            connection.execute("SELECT 1").fetchone()
    except Exception:
        logger.exception("Database readiness check failed")
        return JSONResponse(status_code=503, content={"status": "not_ready"})
    return {"status": "ready"}


@app.get("/api/health")
def health(role=Depends(require_demo_role)):
    return {"status": "ok", "role": role.value}
