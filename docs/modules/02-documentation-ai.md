# Module 02 — Documentation & Staff AI

## Mục tiêu và pain point
Thu thập tài liệu bắt buộc và biến note thành đề xuất có nguồn; tránh hồ sơ thiếu ký hoặc AI tự xác nhận.

## Phạm vi / không làm
Form consent, treatment plan, progress note, medication detail có điều kiện, tooth/surface và fixture extraction. Không dictation, image AI, chẩn đoán, kê đơn hoặc multi-model router.

## Đường dẫn sở hữu
`backend/app/features/documentation_ai/`, `frontend/src/features/documentation-ai/`, `tests/documentation_ai/`, `db/init/20_documentation_ai.sql`.

## Consumes / produces
- Dùng encounter và core service `upsert_evidence`, `append_audit`.
- Evidence: `DOC_CONSENT_SIGNED`, `DOC_TREATMENT_PLAN_SIGNED`, `DOC_PROGRESS_NOTE`, `DOC_MEDICATION_DETAILS`, `DOC_TOOTH_SURFACE`.
- `POST /api/v1/ai/extract-note` → `{ai_run_id,facts:[{fact,tooth,surface,source_span}],state:"UNVERIFIED"}`.
- `POST /api/v1/ai/runs/{id}/accept` hoặc `/reject`; accept ghi `VERIFIED`, reject không ghi evidence.
- Provider env: `MODEL_BASE_URL`, `MODEL_API_KEY`, `MODEL_NAME`; timeout/missing key trả fixture cùng schema.

## Các bước
1. Test conditional fields, source span, fixture fallback và trạng thái trước/sau review.
2. Viết form/router và một provider HTTP tối thiểu; validate output tại boundary.
3. Export `router`/`route`; không sửa shared config.

## Acceptance
AI output không bao giờ tự `SATISFIED`; accept tạo verified evidence và audit; reject giữ nguồn không đổi; timeout chạy fixture.

## Handoff integrator
Router export: ghi import path, prefix và env dùng.
Route export: ghi import path và URL.
Verification: ghi lệnh test, fixture và commit hash.
