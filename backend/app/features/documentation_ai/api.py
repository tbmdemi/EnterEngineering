import json
import os
import re
import urllib.request
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator

from ...core.contracts import Role
from ...core.services import _connect, append_audit, upsert_evidence
from ...dependencies import require_demo_role


router = APIRouter(tags=["documentation-ai"])


class DocumentationInput(BaseModel):
    encounter_id: UUID
    consent_signed: bool
    treatment_plan_signed: bool
    progress_note: str = Field(min_length=1)
    tooth: str = Field(min_length=1)
    surface: str = Field(min_length=1)
    medication_used: bool = False
    medication_detail: Optional[str] = None

    @model_validator(mode="after")
    def require_medication_detail(self):
        if self.medication_used and not (self.medication_detail or "").strip():
            raise ValueError("medication_detail is required when medication_used is true")
        return self


class ExtractNoteInput(BaseModel):
    encounter_id: UUID
    note: str = Field(min_length=1)


class Fact(BaseModel):
    fact: str
    tooth: Optional[str] = None
    surface: Optional[str] = None
    source_span: str = Field(min_length=1)


class Extraction(BaseModel):
    ai_run_id: str
    facts: list[Fact]
    state: str = "UNVERIFIED"


class ReviewInput(BaseModel):
    evidence_code: str = Field(pattern=r"^DOC_(CONSENT_SIGNED|TREATMENT_PLAN_SIGNED|PROGRESS_NOTE|MEDICATION_DETAILS|TOOTH_SURFACE)$")


def _fixture(note: str) -> list[Fact]:
    match = re.search(r"[^.]*\btooth\s+(\w+)\s+surface\s+(\w+)\b[^.]*\.", note, re.IGNORECASE)
    if match:
        span = match.group(0).strip()
        return [Fact(fact="procedure_documented", tooth=match.group(1), surface=match.group(2), source_span=span)]
    span = note.split(".", 1)[0].strip() + ("." if "." in note else "")
    return [Fact(fact="note_documented", source_span=span)]


def _live_extract(note: str) -> tuple[list[Fact], str]:
    base_url, api_key, model = (os.environ.get(name) for name in ("MODEL_BASE_URL", "MODEL_API_KEY", "MODEL_NAME"))
    if not all((base_url, api_key, model)):
        raise RuntimeError("provider is not configured")
    prompt = "Extract only explicitly documented dental facts. Never diagnose or prescribe. Return JSON: {facts:[{fact,tooth,surface,source_span}]}. source_span must be an exact quote."
    body = json.dumps({"model": model, "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": note}], "temperature": 0}).encode()
    request = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", body, {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=8) as response:
        payload = json.load(response)
    content = payload["choices"][0]["message"]["content"]
    facts = [Fact.model_validate(item) for item in json.loads(content)["facts"]]
    if not facts or any(fact.source_span not in note for fact in facts):
        raise ValueError("provider returned unsupported source spans")
    return facts, model


def _save_run(encounter_id: UUID, model_name: str, facts: list[Fact]) -> str:
    with _connect() as connection:
        row = connection.execute(
            "INSERT INTO ai_runs (encounter_id, model_name, status, output) VALUES (%s,%s,'UNVERIFIED',%s::jsonb) RETURNING id",
            (encounter_id, model_name, json.dumps({"facts": [fact.model_dump() for fact in facts]})),
        ).fetchone()
    return str(row["id"])


def _load_run(run_id: UUID):
    with _connect() as connection:
        row = connection.execute("SELECT * FROM ai_runs WHERE id = %s", (run_id,)).fetchone()
    if not row:
        raise ValueError("AI run not found")
    return dict(row)


def _mark_reviewed(run_id: UUID, status: str):
    with _connect() as connection:
        connection.execute("UPDATE ai_runs SET status = %s WHERE id = %s", (status, run_id))


@router.post("/api/v1/documentation")
def save_documentation(data: DocumentationInput, role: Role = Depends(require_demo_role)):
    values = {
        "DOC_PROGRESS_NOTE": {"note": data.progress_note},
        "DOC_TOOTH_SURFACE": {"tooth": data.tooth, "surface": data.surface},
    }
    if data.consent_signed:
        values["DOC_CONSENT_SIGNED"] = {"signed": True}
    if data.treatment_plan_signed:
        values["DOC_TREATMENT_PLAN_SIGNED"] = {"signed": True}
    if data.medication_used:
        values["DOC_MEDICATION_DETAILS"] = {"detail": data.medication_detail}
    for code, value in values.items():
        upsert_evidence(data.encounter_id, code, "VERIFIED", value, "FORM", None, role.value)
    return {"evidence_codes": list(values)}


@router.post("/api/v1/ai/extract-note", response_model=Extraction)
def extract_note(data: ExtractNoteInput):
    try:
        facts, model = _live_extract(data.note)
    except Exception:
        facts, model = _fixture(data.note), "fixture-v1"
    run_id = _save_run(data.encounter_id, model, facts)
    return Extraction(ai_run_id=run_id, facts=facts)


@router.post("/api/v1/ai/runs/{run_id}/accept")
def accept_run(run_id: UUID, review: ReviewInput, role: Role = Depends(require_demo_role)):
    run = _load_run(run_id)
    output = run["output"] if isinstance(run["output"], dict) else json.loads(run["output"])
    evidence = upsert_evidence(run["encounter_id"], review.evidence_code, "VERIFIED", output, "AI_REVIEW", str(run_id), role.value)
    _mark_reviewed(run_id, "ACCEPTED")
    append_audit(role.value, "AI_RUN_ACCEPTED", "ai_run", run_id, run["encounter_id"], {"evidence_code": review.evidence_code})
    return {"ai_run_id": str(run_id), "state": "VERIFIED", "evidence_id": str(evidence.get("id", ""))}


@router.post("/api/v1/ai/runs/{run_id}/reject")
def reject_run(run_id: UUID, role: Role = Depends(require_demo_role)):
    run = _load_run(run_id)
    _mark_reviewed(run_id, "REJECTED")
    append_audit(role.value, "AI_RUN_REJECTED", "ai_run", run_id, run["encounter_id"], {})
    return {"ai_run_id": str(run_id), "state": "REJECTED"}
