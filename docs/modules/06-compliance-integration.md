# Module 06 — Compliance, Audit & Integration

Frontend export contract: `export const route = { path, label, Component }`.

## Mục tiêu

Đánh giá evidence deterministic theo `dental-policy.v1`, reconcile obligation/task idempotently, lưu audit tối thiểu và ráp các module thành một dental vertical slice chạy trên cùng PostgreSQL.

## Ownership

- Policy/evaluator: `backend/app/features/compliance/`.
- Compliance UI: `frontend/src/features/compliance/`.
- Shared bootstrap/router/navigation, Compose, migrations và smoke flow.
- Core schema: `db/init/00_core.sql`.
- Integrated migrations:
  - `001_integrated_demo.sql`: patient-release integration.
  - `002_demo_scenarios.sql`: năm scenario synthetic deterministic.
  - `003_workflow_hardening.sql`: appointment version/status/unique Encounter link và task lifecycle timestamps.

Module không triển khai policy editor, rule DSL, raw-PHI analytics, identity provider hoặc multi-tenant RLS.

## Policy và state

Policy version cố định: `dental-policy.v1`.

Obligation state trong demo:

```text
PENDING | MISSING | UNVERIFIED | SATISFIED | NOT_APPLICABLE
```

Chỉ `SATISFIED` và `NOT_APPLICABLE` được coi là ready. Evaluator không chỉ tin `evidence.state=VERIFIED`; nó kiểm tra content tối thiểu cho signed flag, note/source span, tooth/surface, từng `PRE_*`, post-treatment date/text và coordination values.

Conditional rule dùng fail-safe semantics:

- condition `false` → `NOT_APPLICABLE`;
- condition chưa biết → `MISSING`;
- orphan evidence không làm unknown condition pass.

AI draft luôn `UNVERIFIED`. UI chỉ render kết quả backend, không tự tính state.

## Scope theo stage

Evaluation chỉ mở obligations khi workflow tới đúng phase:

| Current/target phase | Scope chính |
| --- | --- |
| `CHECK_IN` | Chưa tạo clinical obligation task. |
| Vào/ở `PRE_TREATMENT` | Consent, treatment plan và `PRE_*`. |
| Vào/ở `TREATMENT` | Thêm progress note, medication conditional và tooth/surface; coordination bắt đầu actionable. |
| `POST_TREATMENT` / vào `CLOSED` | Full policy gồm documentation, safety, coordination và post-treatment release. |

Vì vậy evaluate sớm không tạo task recall/hậu điều trị trước thời điểm cần thiết.

## HTTP và authorization

- `POST /api/v1/encounters/{id}/evaluate`: FRONT_DESK, ASSISTANT, DENTIST hoặc QA; reconcile checks/tasks theo current stage và append audit. `CLOSED` bị chặn vì evaluate là mutation.
- `GET /api/v1/encounters/{id}/readiness`: staff roles trên; read-only full close assessment.
- `GET /api/v1/audit-events?encounter_id=...`: chỉ DENTIST hoặc QA.
- `GET /api/v1/dashboard`: chỉ DENTIST hoặc QA; chỉ aggregate count, không trả patient/raw evidence.
- PATIENT không dùng Compliance/Encounter staff API.

## Reconciliation và idempotency

Mỗi check được upsert theo `(encounter_id, code, policy_version)`. Generic compliance task có key:

```text
{encounter_id}:{obligation_code}:dental-policy.v1
```

Evaluate lặp cập nhật logical task hiện hữu, không clone. Missing/unverified mở hoặc reopen task; satisfied/N/A cancel task đang active. Coordination codes `COORD_HANDOFF_ACK`, `COORD_REFERRAL_OWNER`, `COORD_SCHEDULE_CLEAR` bị loại khỏi generic task creation vì Module 05 đã sở hữu domain task tương ứng.

## Stage orchestration transaction

Module 01 gọi transition guard của Compliance bằng chính connection đang xử lý stage:

1. derive/evaluate evidence cho target stage;
2. upsert obligation checks và reconcile tasks;
3. append transition-evaluated/blocked audit;
4. nếu ready, compare-and-swap Encounter stage/version;
5. khi close, đổi appointment `CHECKED_IN → FULFILLED`;
6. append stage-transition audit.

Các bước trên cùng một PostgreSQL transaction. Không có khoảng hở giữa “compliance pass” và stage update. Transition bị block không đổi stage nhưng assessment/task/audit an toàn của lần kiểm tra được giữ lại.

## Audit contract

Audit lưu actor role, action, object, encounter, correlation ID, timestamp và metadata allowlist. Metadata có thể chứa code, from/to state/stage, policy version, reason code và citation count; không chứa raw clinical note, raw chat hoặc free-text cancellation reason.

Transition history của Module 01 là projection read-only từ `ENCOUNTER_STAGE_CHANGED`.

## CLOSED invariant liên module

Sau `CLOSED`:

- không có clinical evidence/documentation/pre-treatment/release/evaluate mới;
- không tạo coordination work hoặc chạy schedule mutation mới;
- appointment liên kết đã `FULFILLED`;
- Encounter không reopen trong demo.

Released task `PATIENT_FOLLOW_UP` đúng obligation/key đã tồn tại trước close là ngoại lệ vận hành: owner được acknowledge rồi complete, hoặc complete trực tiếp từ `OPEN`. Chỉ task status/timestamp và audit thay đổi; released evidence và compliance decision không bị sửa. Nhờ vậy immutable clinical record không làm stranded recall work.

## Demo scenarios

`002_demo_scenarios.sql` seed năm trạng thái có chủ đích:

1. `CHECK_IN_BLANK`
2. `PRE_TREATMENT_INCOMPLETE`
3. `TREATMENT_PRE_READY`
4. `POST_TREATMENT_BLOCKED`
5. `POST_TREATMENT_READY`

Migration idempotent; có thể chạy lại service `migrate` mà không nhân bản scenario. Dùng scenario blocked/ready để chứng minh blocker, release và close thay vì sửa tay database.

## Acceptance và verification

- Draft/malformed/unknown-condition evidence không thể làm gate pass.
- Evaluate lặp không clone finding/task.
- Guard stage chỉ xét đúng scope và close xét full policy.
- Stage/compliance/audit/appointment close là atomic.
- Audit/dashboard không lộ raw PHI/chat.
- Clinical writes sau close bị chặn nhưng existing post-treatment follow-up không bị stranded.

Không ghi test count hoặc commit hash cố định trong tài liệu vì chúng nhanh stale. Verification chuẩn:

```powershell
$env:ENCOUNTER_TEST_DATABASE_URL = "postgresql://careguard:careguard@localhost:5432/careguard?connect_timeout=5"
python -m unittest discover -s tests -v
docker compose -f docker-compose.yml -f docker-compose.dev.yml config --quiet
Push-Location frontend
npm.cmd run build
Pop-Location
```

Compose chạy một service PostgreSQL shared, rồi migration one-shot trước API. Cách cài/chạy/reset và xử lý lỗi migration nằm trong `README.md`.
