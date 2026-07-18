# Module 06 — Compliance, Audit & Integration

## Mục tiêu và pain point
Đánh giá thiếu sót deterministic, tạo đúng một task, lưu audit tối thiểu và ráp các module thành demo chạy được.

## Phạm vi / không làm
Policy cố định `dental-policy.v1`, readiness/evaluate, audit/dashboard, bootstrap/registry/Compose/seed và smoke flow. Không policy editor, rule DSL, analytics platform hoặc raw PHI logging.

## Đường dẫn sở hữu
Toàn bộ shared/bootstrap/registry/navigation, `backend/app/features/compliance/`, `frontend/src/features/compliance/`, `tests/compliance/`, `db/init/60_compliance.sql`.

## Consumes / produces
React export bắt buộc: `export const route = { path, label, Component }`; integrator import vào `frontend/src/routes.js`.
- Consume mọi evidence code trong module 02–05 và core services.
- `POST /api/v1/encounters/{id}/evaluate` → checks/tasks; `GET /api/v1/encounters/{id}/readiness` → grouped findings.
- `GET /api/v1/audit-events`; `GET /api/v1/dashboard`.
- State chỉ gồm `PENDING`, `MISSING`, `UNVERIFIED`, `SATISFIED`, `NOT_APPLICABLE`; task key `encounter:obligation:dental-policy.v1`.

## Các bước
1. Test evaluator RED: missing, verified, draft, N/A và repeated evaluation.
2. Bind ba core services tới PostgreSQL, viết evaluator/policy JSON cố định.
3. Merge router/route tuần tự; chạy `make check`, reset DB và smoke demo ba lần.

## Acceptance
Kết quả tái hiện được; draft không satisfied; evaluate lặp không clone task; audit có actor/action/object/time/correlation nhưng không raw note/chat; dashboard không lộ PHI.

## Handoff integrator
Merged commits: encounter `20681fc`, documentation-AI `9df7d21`, pre-treatment `01bcf0b`, coordination `63a529d`, post-treatment/chat `226f41c`.
Current integration hardening: shared Encounter ID/role context đã được nối vào toàn bộ React route; readiness live và `COMPLIANCE_NOT_READY` hard-gate được áp dụng cho `POST_TREATMENT → CLOSED`; task/evidence/audit của Pre-treatment và Coordination dùng cùng transaction; Compose chạy migration idempotent trước API; Post-treatment không còn khóa vào Encounter seed. Coordination có action xử lý schedule conflict để demo có thể đạt readiness.

Verification hiện tại: 95 tests được phát hiện — 93 pass, 2 PostgreSQL integration tests chủ động skip khi thiếu `ENCOUNTER_TEST_DATABASE_URL`; Python compile, Compose config và Vite production build pass. Hai PostgreSQL tests gồm optimistic concurrency và full dental flow từ evidence đến blocked-close rồi successful-close.

Known limit của phiên verification này: Docker Desktop/daemon trên máy không khởi động được, nên chưa thể chạy hai PostgreSQL tests thật. Khi Docker sẵn sàng, chạy `docker compose up -d db migrate`, đặt `ENCOUNTER_TEST_DATABASE_URL`, rồi chạy lại toàn bộ test theo README. Frontend dev server proxy `/api` tới service `api:8000` trong Compose.
