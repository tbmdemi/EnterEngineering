import json
import os
import re
import urllib.request
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator

from ...core.contracts import Role
from ...core.errors import AppError
from ...core.services import _connect, upsert_evidence
from ...dependencies import require_demo_role


router = APIRouter(tags=["documentation-ai"])


class DocumentationInput(BaseModel):
    encounter_id: UUID
    consent_signed: bool
    treatment_plan_signed: bool
    progress_note: str = Field(min_length=1)
    tooth: str = Field(min_length=1)
    surface: str = Field(min_length=1)
    medication_prescribed: bool = False
    medication_detail: Optional[str] = None

    @model_validator(mode="after")
    def require_medication_detail(self):
        if self.medication_prescribed and not (self.medication_detail or "").strip():
            raise ValueError("medication_detail is required when medication_prescribed is true")
        return self


class ExtractNoteInput(BaseModel):
    encounter_id: UUID
    note: str = Field(min_length=1)


class Fact(BaseModel):
    fact: Literal["note_documented", "procedure_documented"]
    tooth: Optional[str] = None
    surface: Optional[str] = None
    source_span: str = Field(min_length=1)


class Extraction(BaseModel):
    ai_run_id: str
    facts: list[Fact]
    state: str = "UNVERIFIED"


class ReviewInput(BaseModel):
    evidence_code: Literal["DOC_PROGRESS_NOTE", "DOC_TOOTH_SURFACE"]


FACT_EVIDENCE = {
    "note_documented": "DOC_PROGRESS_NOTE",
    "procedure_documented": "DOC_TOOTH_SURFACE",
}


def _require_role(role: Role, *allowed: Role):
    if role not in allowed:
        raise AppError("ROLE_FORBIDDEN", "Role is not allowed for this action", {"role": role.value}, 403)


def _raise_review_error(connection, run_id: UUID):
    existing = connection.execute("SELECT status FROM ai_runs WHERE id = %s", (run_id,)).fetchone()
    if not existing:
        raise AppError("AI_RUN_NOT_FOUND", "AI run was not found", {"ai_run_id": str(run_id)}, 404)
    raise AppError("AI_RUN_ALREADY_REVIEWED", "AI run has already been reviewed", {"status": existing["status"]}, 409)


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


@router.post("/api/v1/documentation")
def save_documentation(data: DocumentationInput, role: Role = Depends(require_demo_role)):
    _require_role(role, Role.ASSISTANT, Role.DENTIST)
    values = {
        "DOC_PROGRESS_NOTE": {"note": data.progress_note},
        "DOC_TOOTH_SURFACE": {"tooth": data.tooth, "surface": data.surface},
    }
    if data.consent_signed:
        values["DOC_CONSENT_SIGNED"] = {"signed": True}
    if data.treatment_plan_signed:
        values["DOC_TREATMENT_PLAN_SIGNED"] = {"signed": True}
    if data.medication_prescribed:
        values["DOC_MEDICATION_DETAILS"] = {"detail": data.medication_detail}
    for code, value in values.items():
        upsert_evidence(data.encounter_id, code, "VERIFIED", value, "FORM", None, role.value)
    return {"evidence_codes": list(values)}


@router.post("/api/v1/ai/extract-note", response_model=Extraction)
def extract_note(data: ExtractNoteInput, role: Role = Depends(require_demo_role)):
    _require_role(role, Role.ASSISTANT, Role.DENTIST)
    try:
        facts, model = _live_extract(data.note)
    except Exception:
        facts, model = _fixture(data.note), "fixture-v1"
    run_id = _save_run(data.encounter_id, model, facts)
    return Extraction(ai_run_id=run_id, facts=facts)


@router.post("/api/v1/ai/runs/{run_id}/accept")
def accept_run(run_id: UUID, review: ReviewInput, role: Role = Depends(require_demo_role)):
    _require_role(role, Role.DENTIST)
    with _connect() as connection:
        run = connection.execute(
            "UPDATE ai_runs SET status = 'ACCEPTED' WHERE id = %s AND status = 'UNVERIFIED' RETURNING encounter_id, output",
            (run_id,),
        ).fetchone()
        if not run:
            _raise_review_error(connection, run_id)
        output = run["output"] if isinstance(run["output"], dict) else json.loads(run["output"])
        try:
            fact = Fact.model_validate(output["facts"][0])
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise AppError("AI_OUTPUT_INVALID", "AI output cannot be accepted", status_code=400) from error
        expected_code = FACT_EVIDENCE[fact.fact]
        if review.evidence_code != expected_code:
            raise AppError("EVIDENCE_CODE_MISMATCH", "Evidence code does not match extracted fact", {"expected": expected_code}, 400)
        value = {"source_span": fact.source_span}
        if fact.fact == "procedure_documented":
            if not fact.tooth or not fact.surface:
                raise AppError("AI_OUTPUT_INVALID", "Procedure fact requires tooth and surface", status_code=400)
            value.update(tooth=fact.tooth, surface=fact.surface)
        evidence = connection.execute(
            """INSERT INTO evidence_items (encounter_id, code, state, value, source_type, source_ref, actor_role)
               VALUES (%s,%s,'VERIFIED',%s::jsonb,'AI_REVIEW',%s,%s)
               ON CONFLICT (encounter_id, code) DO UPDATE SET state='VERIFIED', value=EXCLUDED.value,
                 source_type=EXCLUDED.source_type, source_ref=EXCLUDED.source_ref, actor_role=EXCLUDED.actor_role, updated_at=now()
               RETURNING id""",
            (run["encounter_id"], expected_code, json.dumps(value), str(run_id), role.value),
        ).fetchone()
        connection.execute(
            "INSERT INTO audit_events (actor_role, action, object_type, object_id, encounter_id, metadata) VALUES (%s,'AI_RUN_ACCEPTED','ai_run',%s,%s,%s::jsonb) RETURNING id",
            (role.value, run_id, run["encounter_id"], json.dumps({"evidence_code": expected_code})),
        ).fetchone()
    return {"ai_run_id": str(run_id), "state": "VERIFIED", "evidence_id": str(evidence.get("id", ""))}


@router.post("/api/v1/ai/runs/{run_id}/reject")
def reject_run(run_id: UUID, role: Role = Depends(require_demo_role)):
    _require_role(role, Role.DENTIST)
    with _connect() as connection:
        run = connection.execute(
            "UPDATE ai_runs SET status = 'REJECTED' WHERE id = %s AND status = 'UNVERIFIED' RETURNING encounter_id",
            (run_id,),
        ).fetchone()
        if not run:
            _raise_review_error(connection, run_id)
        connection.execute(
            "INSERT INTO audit_events (actor_role, action, object_type, object_id, encounter_id, metadata) VALUES (%s,'AI_RUN_REJECTED','ai_run',%s,%s,'{}'::jsonb) RETURNING id",
            (role.value, run_id, run["encounter_id"]),
        ).fetchone()
    return {"ai_run_id": str(run_id), "state": "REJECTED"}
