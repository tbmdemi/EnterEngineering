# Module 05 — Coordination

Frontend export contract: `export const route = { path, label, Component }`.

## Mục tiêu

Đưa đúng task tới đúng care-team role, tách acknowledge khỏi complete và xử lý appointment overlap mà không hủy nhầm lịch đã đổi trạng thái.

## Phạm vi

- Worklist theo role.
- Handoff, referral và patient follow-up lifecycle.
- Schedule overlap/evaluate/resolve cho dental demo.
- Không phải scheduling engine, notification service hoặc SLA escalation platform.

Code nằm tại `backend/app/features/coordination/`, `frontend/src/features/coordination/`, `tests/coordination/`. Seed nằm ở `db/init/40_coordination.sql`; task timestamps và appointment constraints nằm ở `db/migrations/003_workflow_hardening.sql`.

## Task contract

### Tạo task

`POST /api/v1/coordination/tasks`

```json
{
  "encounter_id": "30000000-0000-0000-0000-000000000003",
  "obligation_code": "COORD_HANDOFF_ACK",
  "task_type": "HANDOFF",
  "owner_role": "ASSISTANT",
  "due_at": "2026-07-20T09:00:00+07:00"
}
```

- `task_type` chỉ `HANDOFF` hoặc `REFERRAL`.
- Referral bắt buộc có owner.
- Owner phải thuộc `FRONT_DESK | ASSISTANT | DENTIST`; Patient/QA không phải worklist owner.
- Idempotency key được derive từ encounter, type và obligation; retry không clone logical task.

### Worklist và mutation

- `GET /api/v1/tasks?owner_role=...`: FRONT_DESK/ASSISTANT/DENTIST chỉ đọc worklist của chính role; QA có thể đọc để audit; Patient bị cấm.
- `POST /api/v1/tasks/{task_id}/acknowledge`: chỉ owner; áp dụng cho `HANDOFF` và released `PATIENT_FOLLOW_UP`; repeated acknowledge là idempotent.
- `POST /api/v1/tasks/{task_id}/complete`: chỉ owner; handoff phải ở `ACKNOWLEDGED`, referral/follow-up theo lifecycle hợp lệ; repeated complete là idempotent.
- `CANCELLED` không được acknowledge/complete.

Status theo task type:

```text
HANDOFF:          OPEN → ACKNOWLEDGED → COMPLETED
REFERRAL:         OPEN ─────────────────→ COMPLETED
PATIENT_FOLLOW_UP OPEN → ACKNOWLEDGED → COMPLETED
                  OPEN ─────────────────→ COMPLETED
Active task       OPEN/ACKNOWLEDGED ────→ CANCELLED
```

Mỗi transition cập nhật timestamp tương ứng, `updated_at`, evidence liên quan và audit from/to status trong cùng transaction.

## Schedule conflict contract

`POST /api/v1/encounters/{encounter_id}/coordination/evaluate` khóa Encounter/appointment rows, dùng interval half-open:

```text
anchor.starts_at < other.ends_at
AND anchor.ends_at > other.starts_at
```

Chỉ appointment active `PENDING | BOOKED | ARRIVED | CHECKED_IN` được coi là conflict. Appointment terminal không tạo false positive. Evaluation upsert `COORD_SCHEDULE_CLEAR`; conflict tạo đúng một `REVIEW_SCHEDULE_CONFLICT` task cho FRONT_DESK.

Việc phát hiện và việc được phép hủy là hai rule riêng: resolve chỉ được cancel target `PENDING | BOOKED | ARRIVED`. Target đã `CHECKED_IN` vẫn được flag để con người thấy conflict nhưng API trả `409 APPOINTMENT_NOT_CANCELLABLE`; không tự hủy một ca đã check-in.

`POST /api/v1/encounters/{encounter_id}/coordination/resolve-schedule` chỉ FRONT_DESK được gọi và bắt buộc body:

```json
{
  "appointment_id": "uuid-cua-lich-xung-dot",
  "expected_status": "BOOKED",
  "reason": "DUPLICATE_BOOKING"
}
```

`reason` chỉ nhận:

- `DUPLICATE_BOOKING`
- `PATIENT_REQUESTED_CANCELLATION`
- `REBOOKED_TO_ANOTHER_SLOT`
- `CREATED_IN_ERROR`

Server kiểm tra target vẫn khác anchor, còn cancellable, cùng chair, còn overlap và status vẫn bằng `expected_status` ngay trong atomic SQL update. Thành công đổi target thành `CANCELLED`, tăng appointment version, evaluate conflict còn lại và ghi reason code an toàn vào audit. Stale status trả `APPOINTMENT_STATE_CONFLICT`; conflict đã biến mất trả `SCHEDULE_CONFLICT_NOT_FOUND`.

Không đưa free-text reason hoặc PHI vào audit.

## Locking, CLOSED và follow-up

Mọi coordination write khóa theo thứ tự ổn định Encounter → task/appointments để tránh deadlock. Không tạo task, evaluate schedule, resolve schedule hoặc thay đổi clinical coordination evidence sau `CLOSED`.

Ngoại lệ hẹp: released task `PATIENT_FOLLOW_UP` đúng obligation/key do Module 04 tạo trước khi close vẫn được owner acknowledge rồi complete, hoặc complete trực tiếp từ `OPEN`, sau `CLOSED`. Ngoại lệ chỉ update task status/timestamp và audit; không tạo task/evidence mới, không áp dụng cho handoff/referral/schedule task và không reopen Encounter.

## Evidence ownership

- `COORD_HANDOFF_ACK`: tạo khi handoff được acknowledge.
- `COORD_REFERRAL_OWNER`: giữ owner hợp lệ của referral.
- `COORD_SCHEDULE_CLEAR`: `{"clear": true}` mới thỏa policy.

Compliance đọc các evidence này nhưng không tạo generic REVIEW task trùng với domain task do Coordination sở hữu.

## Acceptance và verification

- Worklist không lộ sang role khác/Patient.
- Handoff chưa acknowledge không thể complete; terminal retry không tạo transition phụ.
- Referral thiếu/sai owner bị từ chối.
- Overlap half-open, terminal status, checked-in target và stale request được xử lý an toàn.
- Resolve request luôn có status snapshot và reason allowlist.
- New coordination writes sau close bị chặn; existing follow-up vẫn hoàn tất được.

```powershell
python -m unittest tests.coordination.test_coordination -v
```
