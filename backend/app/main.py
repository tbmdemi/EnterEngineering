from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .core.errors import AppError
from .dependencies import require_demo_role
from .features.compliance.router import router as compliance_router
from .features.encounter.router import router as encounter_router


app = FastAPI(title="CareGuard Dental Demo")
app.include_router(compliance_router)
app.include_router(encounter_router)


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, error: AppError):
    return JSONResponse(status_code=error.status_code, content=error.payload)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, error: RequestValidationError):
    return JSONResponse(status_code=422, content={"code": "VALIDATION_ERROR", "message": "Request validation failed", "details": {"error_count": len(error.errors())}})


@app.exception_handler(Exception)
async def unhandled_error_handler(_request: Request, _error: Exception):
    return JSONResponse(status_code=500, content={"code": "INTERNAL_ERROR", "message": "Unexpected server error", "details": {}})


@app.get("/api/health")
def health(role=Depends(require_demo_role)):
    return {"status": "ok", "role": role.value}
