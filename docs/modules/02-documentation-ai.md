# Module 02 — Documentation & Staff AI

Frontend export contract: `export const route = { path, label, Component }`.

## Mục tiêu

Thu thập documentation bắt buộc và biến note thành đề xuất có nguồn để Dentist review. AI chỉ tạo `UNVERIFIED`; quyết định human review mới có thể tạo verified evidence.

## Phạm vi

- Form consent, treatment plan, progress note, medication có điều kiện và tooth/surface.
- Fixture/live extraction cho fact đã được ghi rõ trong note.
- Accept/reject AI run một lần.
- Không chẩn đoán, kê đơn, đọc ảnh, tự ký hồ sơ hoặc tự chuyển Encounter stage.

Code nằm tại `backend/app/features/documentation_ai/`, `frontend/src/features/documentation-ai/` và `tests/documentation_ai/`.

## Shared data và transaction boundary

Module không có bảng riêng theo feature. Nó dùng các bảng shared trong `db/init/00_core.sql`:

- `encounters` để khóa/kiểm tra Encounter còn mutable.
- `evidence_items` cho `DOC_*`.
- `ai_runs` cho output và review state.
- `audit_events` cho metadata an toàn.

`POST /api/v1/documentation` khóa Encounter, upsert/delete toàn bộ evidence điều kiện và append `DOCUMENTATION_SAVED` trong một database transaction. Accept AI run đổi run state, kiểm tra Encounter, upsert verified evidence và append audit trong cùng transaction; lỗi hoặc Encounter đã đóng làm rollback toàn bộ. Một run đã accept/reject không được review lại.

Không gọi nhiều core transaction rời rạc cho một logical documentation mutation.

## Authorization và CLOSED

| Hành động | ASSISTANT | DENTIST | FRONT_DESK / QA / PATIENT |
| --- | --- | --- | --- |
| Lưu documentation form | Có | Có | Không |
| Chạy extraction | Có | Có | Không |
| Accept/reject AI run | Không | Có | Không |

Mọi mutation trên Encounter `CLOSED` trả `409 ENCOUNTER_CLOSED`. Documentation đã có vẫn được bảo toàn; muốn sửa hồ sơ target product phải dùng version/amendment, không sửa ngầm bản đã đóng.

## Evidence contract

Form có thể tạo:

- `DOC_CONSENT_SIGNED` với `{"signed": true}`.
- `DOC_TREATMENT_PLAN_SIGNED` với `{"signed": true}`.
- `DOC_PROGRESS_NOTE` với note không rỗng.
- `DOC_TOOTH_SURFACE` với tooth và surface không rỗng.
- `DOC_MEDICATION_PRESCRIBED` với boolean `prescribed`.
- `DOC_MEDICATION_DETAILS` chỉ khi prescribed và detail không rỗng.

String input được trim và từ chối nếu chỉ có whitespace. Evaluator kiểm tra content bên trong; nhãn `VERIFIED` đơn lẻ không đủ để thỏa obligation.

AI-accepted evidence dùng `source_type=AI_REVIEW`, `source_ref=ai_run_id` và lưu `source_span`. Live provider output bị validate tại boundary; source span phải xuất hiện trong note gốc.

`AI_MODE=fixture` là chế độ demo deterministic. Với `AI_MODE=live`, provider thiếu cấu hình, timeout hoặc output không hợp lệ không được âm thầm đổi thành fixture: hệ thống lưu một `ai_runs.status=ABSTAINED`, ghi audit không chứa raw note và trả `503 AI_PROVIDER_UNAVAILABLE` kèm `manual_fallback=true`. Checklist/form thủ công vẫn hoạt động độc lập.

## HTTP contract

- `POST /api/v1/documentation` nhận `encounter_id` cùng các field form.
- `POST /api/v1/ai/extract-note` nhận `{encounter_id, note}`, trả `{ai_run_id, facts, state:"UNVERIFIED"}`.
- `POST /api/v1/ai/runs/{run_id}/accept` nhận `{evidence_code}`.
- `POST /api/v1/ai/runs/{run_id}/reject` không tạo evidence.

Accept chỉ cho phép evidence code khớp loại fact; procedure fact bắt buộc có tooth và surface. AI run không tự tạo `SATISFIED`; Module 06 luôn đánh giá từ verified evidence và content.

Provider tùy chọn:

```text
MODEL_BASE_URL
MODEL_API_KEY
MODEL_NAME
```

## Audit và privacy

Audit chỉ ghi action, actor, object, encounter và evidence code; không ghi raw note. Patient không đọc draft hoặc staff documentation API. Released patient content là contract riêng của Module 04.

## Acceptance và verification

- Role boundary được enforce ở backend, không phụ thuộc nút UI.
- Medication conditional field và whitespace được validate.
- Fixture/live output hợp lệ luôn bắt đầu `UNVERIFIED`; live failure được lưu `ABSTAINED` và không tạo evidence.
- Chỉ Dentist accept/reject; repeated review trả conflict.
- Save/AI review trên `CLOSED` bị chặn và không để lại partial state.
- Audit không chứa raw note.

```powershell
python -m unittest tests.documentation_ai.test_documentation_ai -v
```
