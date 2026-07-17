# Pre-treatment AI review fixtures

## Goal

Make each pre-treatment check reviewable instead of presenting empty fields while claiming that AI and cited records exist. The demo must keep the human as the only authority that creates verified evidence.

## Scope

- Add a deterministic `ai_review` draft to each checklist item returned by `GET /api/v1/encounters/{id}/pre-treatment`.
- Each draft contains a suggested value and structured citations (`ref`, `label`, `excerpt`).
- Show the suggestion and citations in the UI. Staff can use the suggestion, edit it, or reject it before confirming.
- Send only citation references selected for review as `reviewed_source_refs` when confirming. Store them in the verified evidence value with the existing actor and UTC timestamp.
- Do not add a model, provider, endpoint, raw source persistence, clinical finding, or treatment decision.

## API contract

Each checklist item has this additional field:

```json
{
  "ai_review": {
    "state": "DRAFT",
    "suggestion": {},
    "citations": [{ "ref": "DOC-DEMO-001", "label": "Intake record", "excerpt": "Synthetic source excerpt" }]
  }
}
```

`suggestion` uses the same field names as the attestation value, excluding server-owned `performed_at`. The fixture is defined in the pre-treatment backend and is replaceable by Module 02 output that conforms to this contract.

## UI and data flow

1. Load checklist plus each item's `ai_review`.
2. Render cited source cards and an explicitly labelled unverified AI suggestion.
3. "Use suggestion" copies the suggestion into the editable native controls. Reject leaves fields unchanged and hides the draft for the current session.
4. Confirm remains the sole write action. It sends staff-edited values plus `reviewed_source_refs`.
5. Backend appends `performed_at`, writes `VERIFIED` evidence, and keeps audit metadata free of raw excerpts or summaries.

## Validation

- Unit test the GET response's fixture shape and citations for every checklist item.
- Unit test that medical-history confirmation persists `reviewed_source_refs` alongside the edited summary.
- Run the existing pre-treatment test suite and frontend build/check command from the repository Makefile.

## Explicit non-goals

- Live LLM calls or a mock AI provider.
- Clinical inference, diagnosis, image analysis, or auto-confirmation.
- Persisting raw cited excerpts in evidence or audit data.
