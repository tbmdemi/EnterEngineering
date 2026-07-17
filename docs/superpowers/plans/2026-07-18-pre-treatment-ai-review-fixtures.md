# Pre-treatment AI Review Fixtures Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every pre-treatment check reviewable through a cited deterministic AI draft, with staff confirmation as the only verified-evidence write.

**Architecture:** The router adds a static `ai_review` fixture to each existing checklist item. The React page renders, uses, or rejects it locally, then sends citation refs with the existing attestation.

**Tech Stack:** FastAPI, Python unittest, React 19, Vite.

## Global Constraints

- Deterministic fixtures only; no model, provider, or new endpoint.
- Drafts never become verified without the existing staff confirmation.
- Persist citation refs only; raw citation excerpts never enter audit data.

---

### Task 1: Expose deterministic cited drafts

**Files:** Modify `backend/app/features/pre_treatment/router.py`; modify `tests/pre_treatment/test_pre_treatment.py`.

- [ ] **Step 1: Add a failing response-contract test**

```python
def test_checklist_exposes_draft_ai_review_with_citations_for_each_check(self):
    with patch.object(feature, "_read_evidence", return_value=[]), patch.object(feature, "_read_audit", return_value=[]):
        result = feature.get_checklist("enc", Role.ASSISTANT)
    for item in result["items"]:
        review = item["ai_review"]
        self.assertEqual(review["state"], "DRAFT")
        self.assertTrue(review["suggestion"])
        self.assertTrue(review["citations"][0]["ref"])
```

- [ ] **Step 2: Verify RED** — `.venv/bin/python -m unittest tests.pre_treatment.test_pre_treatment.PreTreatmentTest.test_checklist_exposes_draft_ai_review_with_citations_for_each_check`; expected `KeyError: 'ai_review'`.

- [ ] **Step 3: Add `AI_REVIEWS` keyed by every `CODES` member**

```python
AI_REVIEWS = {
    "PRE_MEDICAL_HISTORY": {"state": "DRAFT", "suggestion": {"summary": "No relevant contraindications noted."}, "citations": [{"ref": "DOC-DEMO-001", "label": "Intake record", "excerpt": "Synthetic intake review."}]},
    # Four same-shaped entries using existing form-field names.
}

# in each get_checklist item
"ai_review": AI_REVIEWS[code],
```

- [ ] **Step 4: Verify GREEN and commit** — run the focused test (expected `OK`), then commit `backend/app/features/pre_treatment/router.py` and `tests/pre_treatment/test_pre_treatment.py` as `feat: expose pre-treatment AI review fixtures`.

### Task 2: Retain reviewed medical-history citations

**Files:** Modify `backend/app/features/pre_treatment/router.py`; modify `tests/pre_treatment/test_pre_treatment.py`.

- [ ] **Step 1: Add a failing persistence test**

```python
def test_medical_history_attestation_keeps_reviewed_source_refs(self):
    body = feature.Attestation(value={"summary": "No relevant contraindications noted.", "reviewed_source_refs": ["DOC-DEMO-001"]}, performed_at=datetime(2026, 7, 18, 2, tzinfo=timezone.utc))
    with patch.object(feature.services, "upsert_evidence", return_value={"id": "evidence"}) as upsert, patch.object(feature.services, "append_audit"):
        feature.put_attestation("enc", "PRE_MEDICAL_HISTORY", body, Role.ASSISTANT)
    self.assertEqual(upsert.call_args.args[3]["reviewed_source_refs"], ["DOC-DEMO-001"])
```

- [ ] **Step 2: Verify RED** — run that test; expected failure until source refs are normalized.

- [ ] **Step 3: Normalize refs before evidence write**

```python
if code == "PRE_MEDICAL_HISTORY":
    refs = body.value.get("reviewed_source_refs", [])
    value["reviewed_source_refs"] = [ref for ref in refs if isinstance(ref, str) and ref]
```

- [ ] **Step 4: Verify GREEN and commit** — focused test is `OK`; commit both files as `feat: retain reviewed source references`.

### Task 3: Render and review drafts in the safety gate

**Files:** Modify `frontend/src/features/pre-treatment/index.jsx`; modify `frontend/src/style.css`.

- [ ] **Step 1: Add local reject state and an explicit prefill action**

```jsx
const [rejectedReviews, setRejectedReviews] = useState({});
const useSuggestion = item => {
  setValues(current => ({ ...current, [item.code]: { ...current[item.code], ...item.ai_review.suggestion } }));
  setDirty(current => ({ ...current, [item.code]: true }));
};
```

- [ ] **Step 2: Render an unverified citation card above each pending form**

```jsx
{item.ai_review && !rejectedReviews[item.code] && <section className="ai-review" aria-label={`${title} AI review`}>
  <strong>AI suggestion — unverified</strong>
  <ul>{item.ai_review.citations.map(citation => <li key={citation.ref}><b>{citation.label}</b>: {citation.excerpt}</li>)}</ul>
  <button type="button" onClick={() => useSuggestion(item)}>Use suggestion</button>
  <button type="button" onClick={() => setRejectedReviews(current => ({ ...current, [item.code]: true }))}>Reject suggestion</button>
</section>}
```

- [ ] **Step 3: Include citation refs in confirmation values** — make `valueFor(item)` add `reviewed_source_refs: item.ai_review?.citations.map(citation => citation.ref) || []`; clear rejection state in `resetDemo`.

- [ ] **Step 4: Add compact card CSS, build, and commit** — `cd frontend && npm run build` exits 0; commit both files as `feat: review AI drafts before pre-treatment confirmation`.

### Task 4: Document and verify the contract

**Files:** Modify `docs/modules/03-pre-treatment.md`.

- [ ] **Step 1: Document the current fixture** — `GET .../pre-treatment` returns `{state:"DRAFT", suggestion, citations}` until Module 02 provides that same schema; Module 03 adds no provider.

- [ ] **Step 2: Verify** — `make check` exits 0; `git diff --check` has no output.

- [ ] **Step 3: Commit** — commit the module doc as `docs: document pre-treatment AI review fixture contract`.
