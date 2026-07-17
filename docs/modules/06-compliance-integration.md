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
Verification: `make check` — 47 tests pass, Python compile, Compose config và Vite production build; FastAPI health/error/OpenAPI smoke pass.
Known limits: Docker daemon không chạy trong session nên chưa boot PostgreSQL/reset demo; chạy `make reset-demo` khi Docker sẵn sàng.
