# CareGuard Dental — đặc tả demo 20 giờ

## Mục tiêu

Trong 20 giờ, hoàn thành một luồng nha khoa synthetic: mở ca thiếu dữ liệu, bổ sung evidence, human-review AI, kiểm tra trước điều trị, tạo follow-up/handoff, patient chat và xem audit/readiness. Demo chứng minh AI chỉ tìm evidence; rule deterministic và con người quyết định.

## Phạm vi khóa

- React/Vite, FastAPI và PostgreSQL 16; modular monolith, JSON `snake_case`, UUID, thời gian UTC ISO-8601.
- Vai trò demo lấy từ `X-Demo-Role`: `FRONT_DESK`, `ASSISTANT`, `DENTIST`, `PATIENT`, `QA`.
- Stage: `CHECK_IN → PRE_TREATMENT → TREATMENT → POST_TREATMENT → CLOSED`.
- Error: `{code, message, details}`. Không trả stack trace, PHI hoặc raw source.
- AI output luôn `DRAFT/UNVERIFIED`; chỉ human accept mới thành evidence `VERIFIED`.
- Không làm HIS/PMS đầy đủ, đa chuyên khoa, OIDC, billing, image AI, vector DB, policy editor, broker hoặc realtime chat.

## Hợp đồng dùng chung

Core tables: `patients`, `appointments`, `encounters`, `evidence_items`, `obligation_checks`, `tasks`, `ai_runs`, `audit_events`.

```python
upsert_evidence(encounter_id, code, state, value, source_type, source_ref, actor_role)
ensure_task(encounter_id, obligation_code, task_type, owner_role, due_at, idempotency_key)
append_audit(actor_role, action, object_type, object_id, encounter_id, metadata)
```

Các module export một FastAPI `router` và một React `route`; integrator là người duy nhất nối registry/navigation. Policy cố định là `dental-policy.v1`.

## Timeline và Definition of Done

- H0–H2: foundation/contracts/seed; mọi branch tách từ commit `foundation-v1`.
- H2–H8: happy path; H8–H13: test/fallback/docs; feature freeze H13.
- H13–H16: merge theo thứ tự encounter, documentation, pre-treatment, coordination, post-treatment.
- H16–H20: integration, ba lần chạy demo, code freeze.

Hoàn thành khi `make check` pass, database reset được, và demo 5 phút đi hết luồng. Bắt buộc kiểm tra idempotency task, portal không thấy draft, AI timeout dùng fixture, chat red-flag escalation, overlap bị flag và audit không chứa raw note/chat.
