# Module 03 — Pre-treatment Safety

> **MERGE-CRITICAL — read before integrating this module:** Pre-treatment is a current-encounter safety attestation layer, **not** a second medical record or an AI clinical-decision feature. It consumes encounter context and source-cited Documentation & Staff AI output; it writes only the five `PRE_*` evidence items after a human confirms them. Read [AI context and source-of-truth decisions](#ai-context-and-source-of-truth-decisions) before changing its API, UI or evaluator mapping.

> **Non-negotiable AI boundary:** AI may produce a `DRAFT/UNVERIFIED` medical-history summary with source references. Only `ASSISTANT` or `DENTIST` can create `VERIFIED` pre-treatment evidence. No image AI, raw note/chat audit logging, clinical diagnosis or treatment decision belongs here.

## Mục tiêu và pain point
Ngăn bỏ qua bước an toàn bắt buộc trước điều trị, với actor và thời điểm có thể audit.

## Phạm vi / không làm
Checklist medical history, allergy, vitals, sterilization và imaging có điều kiện. Không đánh giá lâm sàng, không đọc ảnh, không quản lý thiết bị.

## Đường dẫn sở hữu
`backend/app/features/pre_treatment/`, `frontend/src/features/pre-treatment/`, `tests/pre_treatment/`, `db/init/30_pre_treatment.sql`.

## Consumes / produces
React export bắt buộc: `export const route = { path, label, Component }`; integrator import vào `frontend/src/routes.js`.
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

## AI context and source-of-truth decisions

### Safety gate UX

Pre-treatment là một Safety gate trên một màn hình: phải thấy đủ năm check, trạng thái còn thiếu/đã xác nhận, actor và timestamp. Module không dùng wizard; mục còn thiếu phải nổi bật để staff không bỏ qua.

Mỗi check có dữ liệu tối thiểu riêng, rồi staff `Confirm` từng mục:

| Evidence | Confirmed value |
|---|---|
| `PRE_MEDICAL_HISTORY` | `summary`, `reviewed_source_refs`, `performed_at` |
| `PRE_ALLERGY` | `status` (`NONE_KNOWN` hoặc `PRESENT`), `allergen` bắt buộc khi `PRESENT`, `performed_at` |
| `PRE_VITALS` | `systolic`, `diastolic`, `pulse`, `performed_at` |
| `PRE_STERILIZATION` | `confirmed: true`, `cycle_or_tray_id`, `performed_at` |
| `PRE_IMAGING` | `reviewed: true`, `imaging_reference`, `performed_at`; hoặc `not_applicable: true` |

Vitals chỉ validate là số dương; module không suy luận normal/abnormal hoặc tự chặn điều trị từ giá trị lâm sàng.

### AI assistance: draft only

AI chỉ hỗ trợ tạo bản tóm tắt `DRAFT/UNVERIFIED` cho medical-history review. Staff có thể sửa, accept hoặc reject; chỉ hành động Confirm của `ASSISTANT`/`DENTIST` mới ghi `PRE_MEDICAL_HISTORY` là `VERIFIED` và tạo audit event. AI không tự tạo verified evidence, finding, chẩn đoán hoặc quyết định điều trị.

Module 03 không tạo provider/model AI mới. Khi Module 02 đã được merge, Module 03 reuse output/source citation của Documentation & Staff AI. Audit chỉ lưu quyết định, source reference, actor và thời gian; không lưu raw note.

Image AI nằm ngoài scope của demo và Module 03. Imaging chỉ là human attestation có `imaging_reference`; nếu `PRE_PROCEDURE.requires_imaging` là `false`, server ghi `not_applicable: true`.

### Source ownership and integration boundary

Module 03 không tạo intake note hay một bệnh án thứ hai. Nó review nguồn có sẵn rồi ghi nhận rằng staff đã hoàn thành safety check cho current encounter:

| Source | Owner | Module 03 responsibility |
|---|---|---|
| Patient, appointment, current encounter | Module 01 Encounter | Dùng đúng patient/encounter context |
| Progress note, medication details và AI facts có nguồn | Module 02 Documentation & Staff AI | Hiển thị facts/citations để staff review |
| Past medical record / visit history | Chưa có nguồn trong scope hiện tại | Không giả lập là data có sẵn; cần contract/synthetic source riêng nếu được mở rộng |
| Doctor-patient chat | Không có pre-treatment chat trong spec; Module 04 là post-treatment portal chat | Không dùng làm nguồn pre-treatment; không đưa raw chat vào audit |

`PRE_MEDICAL_HISTORY` lưu summary đã được staff xác nhận và `reviewed_source_refs`, không sao chép raw source hoặc nhận ownership của documentation/history. Compliance chỉ đọc state `VERIFIED`/`NOT_APPLICABLE` của evidence, không đọc AI draft để quyết định readiness.

## Handoff integrator
Router export: `backend.app.features.pre_treatment.router:router`, prefix `/api/v1/encounters`.
Route export: `frontend/src/features/pre-treatment/index.jsx:route`, URL `/pre-treatment`.
Verification: `python -m unittest tests.pre_treatment.test_pre_treatment`; mẫu `PRE_IMAGING={"not_applicable":true}`; commit được báo kèm bàn giao.
