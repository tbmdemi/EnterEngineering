from fastapi import APIRouter, Depends

from ...dependencies import require_demo_role
from .service import ChatRequest, ChatResponse, ReleaseRequest, chat, release_encounter


router = APIRouter(tags=["post-treatment-chat"])


@router.post("/api/v1/encounters/{encounter_id}/release")
def release(encounter_id: str, payload: ReleaseRequest, role=Depends(require_demo_role)):
    return release_encounter(encounter_id, payload, role)


@router.post("/api/v1/portal/chat", response_model=ChatResponse)
def portal_chat(payload: ChatRequest, role=Depends(require_demo_role)):
    return chat(payload, role)
