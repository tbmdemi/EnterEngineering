# Module 03 — Pre-treatment Safety

Frontend export contract: `export const route = { path, label, Component }`.

## Mục tiêu

Pre-treatment là lớp human attestation cho safety checklist của current Encounter, không phải bệnh án thứ hai và không phải AI clinical-decision feature.

Module đọc Encounter context cùng source citation đã có, ghi procedure applicability và năm evidence checklist `PRE_*` sau khi clinical staff xác nhận.

## Phạm vi và ownership

- Medical-history review, allergy, vitals, sterilization và imaging có điều kiện.
- Không chẩn đoán, suy luận normal/abnormal, đọc ảnh, quyết định treatment hoặc quản lý thiết bị.
- Code: `backend/app/features/pre_treatment/`, `frontend/src/features/pre-treatment/`, `tests/pre_treatment/`.
- Seed riêng: `db/init/30_pre_treatment.sql`; evidence/audit vẫn dùng shared tables trong `db/init/00_core.sql`.

## Authorization và stage boundary

| Hành động | FRONT_DESK | ASSISTANT | DENTIST | QA | PATIENT |
| --- | --- | --- | --- | --- | --- |
| Đọc checklist/audit | Có | Có | Có | Có | Không |
| Ghi attestation | Không | Có | Có | Không | Không |
| Reset scenario demo | Không | Không | Không | Có | Không |

Attestation và demo reset chỉ mutable khi Encounter đang `CHECK_IN` hoặc `PRE_TREATMENT`. Từ `TREATMENT` trở đi trả `409 PRE_TREATMENT_STAGE_INVALID`; riêng `CLOSED` trả `409 ENCOUNTER_CLOSED`.

Quy tắc này giữ pre-treatment data ổn định sau khi treatment bắt đầu. Việc sửa sai trong sản phẩm thật phải là amendment/version mới, không overwrite lịch sử.

## HTTP contract

- `GET /api/v1/encounters/{encounter_id}/pre-treatment` trả năm item, applicability, evidence hiện tại, draft suggestion/citation và audit tối thiểu.
- `PUT /api/v1/encounters/{encounter_id}/pre-treatment/procedure` nhận `{requires_imaging, performed_at}` để clinical staff chốt applicability trước khi xử lý imaging.
- `PUT /api/v1/encounters/{encounter_id}/pre-treatment/{code}` nhận `{value, performed_at}`.
- `POST /api/v1/encounters/{encounter_id}/pre-treatment/demo-reset` chỉ dành cho QA và dữ liệu synthetic.

`performed_at` bắt buộc có timezone và được chuẩn hóa về UTC trong evidence/audit.

## Content validation

`VERIFIED` không thay thế content hợp lệ. Server dùng strict model riêng cho từng code, từ chối field lạ trong `value` và trả `422 PRE_TREATMENT_VALUE_INVALID` hoặc `PRE_TREATMENT_SOURCE_REF_INVALID`.

| Evidence | Content tối thiểu |
| --- | --- |
| `PRE_MEDICAL_HISTORY` | `summary` không rỗng và ít nhất một `reviewed_source_refs` thuộc citation allowlist. |
| `PRE_ALLERGY` | `status=NONE_KNOWN` hoặc `PRESENT`; `PRESENT` bắt buộc có `allergen`. |
| `PRE_VITALS` | `systolic`, `diastolic`, `pulse` là số dương hữu hạn; không nhận boolean/string giả số. |
| `PRE_STERILIZATION` | `confirmed=true` và `cycle_or_tray_id` không rỗng. |
| `PRE_IMAGING` | Khi applicable: `reviewed=true` và `imaging_reference` không rỗng. |

Mỗi evidence còn có `performed_at`, actor, source type/reference. Module 06 kiểm tra lại cả state lẫn content; evidence malformed được đánh giá `UNVERIFIED`, không phải `SATISFIED`.

## Conditional imaging

`PRE_PROCEDURE.requires_imaging` là context điều kiện:

- `true`: cần attestation imaging đầy đủ.
- `false`: server ghi `{"not_applicable": true, "performed_at": ...}`; evaluator trả `NOT_APPLICABLE`.
- thiếu/không hợp lệ: applicability là unknown và obligation giữ trạng thái an toàn `MISSING`; một orphan imaging row không được làm gate pass.

`ASSISTANT` hoặc `DENTIST` khai báo context này qua endpoint procedure/UI. Nếu đổi true ↔ false, server xóa attestation imaging cũ trong cùng transaction để không giữ evidence mâu thuẫn; staff phải xác nhận lại theo applicability mới.

## AI/source boundary

Draft suggestion trong demo là fixture deterministic để minh họa review UX. AI luôn là `DRAFT/UNVERIFIED`; chỉ `ASSISTANT` hoặc `DENTIST` nhấn Confirm mới tạo verified attestation.

`PRE_MEDICAL_HISTORY` lưu summary đã được human xác nhận và source refs, không sao chép raw intake note. Module không dùng post-treatment chat làm nguồn và audit không lưu raw note/chat.

## Atomicity và audit

Mỗi attestation khóa Encounter, kiểm tra stage, upsert evidence và append `PRE_TREATMENT_ATTESTED` trong cùng shared transaction. Reset cũng khóa Encounter, xóa năm checklist item, khôi phục procedure context và ghi audit atomically.

## Acceptance và verification

- Patient/Front Desk/QA không thể attest; QA chỉ reset demo.
- Mutation ngoài `CHECK_IN/PRE_TREATMENT` không làm thay đổi evidence.
- Mọi item validate đúng content, source ref và timezone.
- Imaging false là N/A; unknown không tự pass.
- Transition vào `TREATMENT` chỉ pass khi toàn bộ applicable pre-treatment evidence hợp lệ.

```powershell
python -m unittest tests.pre_treatment.test_pre_treatment -v
```
