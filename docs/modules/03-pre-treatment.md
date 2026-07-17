# Module 03 — Pre-treatment Safety

## Mục tiêu và pain point
Ngăn bỏ qua bước an toàn bắt buộc trước điều trị, với actor và thời điểm có thể audit.

## Phạm vi / không làm
Checklist medical history, allergy, vitals, sterilization và imaging có điều kiện. Không đánh giá lâm sàng, không đọc ảnh, không quản lý thiết bị.

## Đường dẫn sở hữu
`backend/app/features/pre_treatment/`, `frontend/src/features/pre-treatment/`, `tests/pre_treatment/`, `db/init/30_pre_treatment.sql`.

## Consumes / produces
- Dùng encounter, `X-Demo-Role`, `upsert_evidence`, `append_audit`.
- Evidence: `PRE_MEDICAL_HISTORY`, `PRE_ALLERGY`, `PRE_VITALS`, `PRE_STERILIZATION`, `PRE_IMAGING`.
- `GET /api/v1/encounters/{id}/pre-treatment` → checklist hiện tại.
- `PUT /api/v1/encounters/{id}/pre-treatment/{code}` body `{value,performed_at}` → verified evidence kèm actor.
- Procedure seed quyết định imaging `NOT_APPLICABLE`; module cung cấp dữ liệu, evaluator quyết định obligation state.

## Các bước
1. Test role, timestamp, required allergy/sterilization và imaging condition.
2. Viết router/form native inputs; ghi evidence/audit qua core seam.
3. Export `router`/`route`.

## Acceptance
Thiếu allergy hoặc sterilization còn visible cho evaluator; mọi attestation có actor/time; procedure không cần phim cho phép imaging N/A.

## Handoff integrator
Router export: ghi import path và prefix.
Route export: ghi import path và URL.
Verification: ghi lệnh test, evidence mẫu và commit hash.
