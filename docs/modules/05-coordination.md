# Module 05 — Coordination

## Mục tiêu và pain point
Cho đúng vai trò thấy việc cần làm, handoff có người nhận và phát hiện xung đột lịch demo.

## Phạm vi / không làm
Worklist theo role, acknowledge/complete, referral owner và appointment/chair overlap. Không scheduling engine, notification service hoặc SLA escalation phức tạp.

## Đường dẫn sở hữu
`backend/app/features/coordination/`, `frontend/src/features/coordination/`, `tests/coordination/`, `db/init/40_coordination.sql`.

## Consumes / produces
React export bắt buộc: `export const route = { path, label, Component }`; integrator import vào `frontend/src/routes.js`.
- Dùng core `tasks`, appointments, `ensure_task`, `append_audit`.
- Evidence: `COORD_HANDOFF_ACK`, `COORD_REFERRAL_OWNER`, `COORD_SCHEDULE_CLEAR`.
- `GET /api/v1/tasks?owner_role=...`; `POST /api/v1/tasks/{id}/acknowledge`; `POST /api/v1/tasks/{id}/complete`.
- Task output gồm id, encounter, obligation, owner, status, due time; mutation xác thực `X-Demo-Role`.

## Các bước
1. Test role filtering, required acknowledgment, owner và overlap/idempotency.
2. Viết query/router/worklist; overlap là query interval trực tiếp trên seed.
3. Export `router`/`route`.

## Acceptance
Handoff chưa acknowledge vẫn open; referral thiếu owner bị từ chối; evaluate lặp không clone task; overlap chair/appointment bị flag.

## Build checkpoints

| Checkpoint | Evidence |
|---|---|
| Baseline | Branch bắt đầu tại `63a529d`; 10 coordination tests và 7 foundation tests pass trước khi sửa. |
| State machine | Handoff bắt buộc acknowledge; referral chỉ nhận care-team owner; mutation terminal idempotent. |
| Seed và evaluator | Ba role có task seed; overlap, cancelled và half-open boundary có test; schedule key ổn định theo encounter. |
| Integration | FastAPI router và React route được đăng ký; Vite proxy dùng `API_PROXY_TARGET`. |
| Verification | `python -m unittest discover -s tests -v` chạy 26 tests; frontend build pass; desktop/mobile không overflow; PostgreSQL 16 API acceptance pass. |

PostgreSQL 16.14 native đã được kiểm tra qua API thật. Docker Compose chưa chạy được vì Windows image hiện không có `VirtualMachinePlatform` hoặc Hyper-V component.

## Handoff integrator
Router export: `backend.app.features.coordination.router` (`router`), API prefix nằm sẵn trong từng route `/api/v1`.
Route export: `frontend/src/features/coordination/index.jsx` (`route`), URL `/coordination`.
Verification: `python -m unittest discover -s tests -v`; idempotency `coord:{encounter_id}:schedule-conflict`; commit xem bằng `git rev-parse HEAD`.
