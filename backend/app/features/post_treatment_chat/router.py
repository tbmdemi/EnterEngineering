from uuid import UUID

from fastapi import APIRouter, Depends

from ...dependencies import require_demo_role
from .service import (
    ChatRequest,
    ChatResponse,
    ReleaseRequest,
    ReleaseResponse,
    TemplateCatalogResponse,
    chat,
    list_templates,
    release_encounter,
)


router = APIRouter(tags=["post-treatment-chat"])


@router.post("/api/v1/encounters/{encounter_id}/release", response_model=ReleaseResponse)
def release(encounter_id: UUID, payload: ReleaseRequest, role=Depends(require_demo_role)):
    return release_encounter(str(encounter_id), payload, role)


@router.post(
    "/api/v1/portal/chat",
    response_model=ChatResponse,
    response_model_exclude_none=True,
)
def portal_chat(payload: ChatRequest, role=Depends(require_demo_role)):
    return chat(payload, role)


@router.get(
    "/api/v1/post-treatment/templates",
    response_model=TemplateCatalogResponse,
)
def approved_templates(
    locale: str | None = None,
    procedure_code: str | None = None,
    role=Depends(require_demo_role),
):
    return list_templates(role, locale=locale, procedure_code=procedure_code)
