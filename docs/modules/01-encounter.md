# Module 01 — Encounter

Frontend export contract: `export const route = { path, label, Component }`.

## Mục tiêu

Encounter là context chung của một lần khám nha khoa: patient, appointment, workflow stage, optimistic version và lịch sử chuyển stage. Module này điều phối điều kiện vào từng stage; dữ liệu chuyên môn vẫn do các module 02–05 sở hữu.

## Phạm vi triển khai hiện tại

Workflow demo có một chiều:

```text
CHECK_IN → PRE_TREATMENT → TREATMENT → POST_TREATMENT → CLOSED
```

- Chỉ được chuyển đúng stage kế tiếp; không skip, quay lui hoặc reopen.
- Mọi transition gửi `version`; request dùng version cũ nhận `409 STALE_ENCOUNTER_VERSION`.
- `stage` là workflow của dental demo, không phải encounter lifecycle tổng quát của EHR.
- Appointment là kế hoạch; Encounter là ca thực tế. Hai state machine không được đồng nhất với nhau.

Code chính nằm tại `backend/app/features/encounter/`, `frontend/src/features/encounter/` và `tests/encounter/`. Schema dùng các bảng shared trong `db/init/00_core.sql`; hardening nằm ở `db/migrations/003_workflow_hardening.sql`.

## Authorization

Staff Encounter API không phải Patient Portal API:

| Hành động | FRONT_DESK | ASSISTANT | DENTIST | QA | PATIENT |
| --- | --- | --- | --- | --- | --- |
| Đọc encounter và transition history | Có | Có | Có | Có | Không |
| `CHECK_IN → PRE_TREATMENT` | Có | Có | Có | Không | Không |
| Các transition lâm sàng còn lại | Không | Không | Có | Không | Không |

`PATIENT` nhận `403 ROLE_FORBIDDEN` khi gọi `GET /api/v1/encounters/{id}` hoặc endpoint history. Patient chỉ dùng contract portal/released content của Module 04. `X-Demo-Role` chỉ phục vụ demo synthetic; sản phẩm thật cần identity, patient binding, tenant/facility scope và access grant.

## HTTP contract

- `GET /api/v1/encounters/{encounter_id}` trả patient, appointment, `stage`, `version`, `next_stage`, `can_advance` và readiness của transition kế tiếp.
- `GET /api/v1/encounters/{encounter_id}/transitions` trả lịch sử append-only đã lọc từ audit: from/to stage, actor, version và thời điểm.
- `POST /api/v1/encounters/{encounter_id}/stage` nhận `{"stage": "...", "version": n}`.
- Frontend nhận Encounter ID từ URL/query context; không buộc người dùng vào một UUID seed duy nhất.
- Lỗi dùng envelope chung `{code, message, details}`.

`can_advance` là kết quả kết hợp giữa role hiện tại, stage kế tiếp và readiness; UI không tự suy luận policy.

## Guard theo từng transition

| Transition | Role ghi | Điều kiện bắt buộc |
| --- | --- | --- |
| `CHECK_IN → PRE_TREATMENT` | FRONT_DESK, ASSISTANT, DENTIST | Appointment liên kết tồn tại và đang `CHECKED_IN`. |
| `PRE_TREATMENT → TREATMENT` | DENTIST | Consent, treatment plan và toàn bộ `PRE_*` applicable có content hợp lệ. |
| `TREATMENT → POST_TREATMENT` | DENTIST | Các điều kiện trước đó cùng progress note, medication detail khi applicable và tooth/surface. |
| `POST_TREATMENT → CLOSED` | DENTIST | Toàn bộ `dental-policy.v1`, gồm post-treatment và coordination, ở `SATISFIED` hoặc `NOT_APPLICABLE`. |

Transition tới `TREATMENT` hoặc `POST_TREATMENT` bị chặn bằng `STAGE_REQUIREMENTS_NOT_READY`; close bị chặn bằng `COMPLIANCE_NOT_READY`. Response chứa blocker code/state/owner để UI đưa người dùng tới đúng feature.

## Transaction và concurrency

Một transition dùng một PostgreSQL transaction:

1. Đọc encounter và kiểm tra optimistic `version`.
2. Kiểm tra transition kế tiếp và role tại HTTP boundary.
3. Chạy guard; guard compliance reconcile obligation/task đúng scope stage và ghi audit an toàn trong cùng transaction.
4. Khi guard pass, cập nhật `encounters.stage/version` bằng compare-and-swap và append `ENCOUNTER_STAGE_CHANGED`.
5. Riêng khi vào `CLOSED`, appointment `CHECKED_IN` được đổi thành `FULFILLED` và tăng appointment version trong cùng transaction.

`CHECK_IN → PRE_TREATMENT` khóa row appointment để trạng thái check-in không đổi giữa lúc kiểm tra và cập nhật. Hai request cùng encounter version chỉ có tối đa một request thắng. Một transition bị compliance chặn vẫn có thể commit assessment/task/audit của lần kiểm tra, nhưng không đổi stage.

Database bảo vệ tối đa một Encounter cho mỗi Appointment bằng unique partial index.

## Invariant sau CLOSED

`CLOSED` khóa clinical record: không thêm/sửa Documentation AI, pre-treatment attestation, release, evaluate mới hoặc coordination work mới. Appointment đã là `FULFILLED`.

Ngoại lệ có chủ đích là lifecycle của released follow-up task đúng obligation/key đã được tạo trước khi đóng ca: owner vẫn có thể acknowledge rồi complete, hoặc complete trực tiếp từ `OPEN`, sau `CLOSED`. Ngoại lệ này chỉ cập nhật vận hành follow-up và audit; nó không sửa evidence lâm sàng, không tạo task/coordination mới và không reopen Encounter.

## Boundary liên module

- Module 02 ghi documentation evidence và AI review; không cập nhật stage trực tiếp.
- Module 03 ghi `PRE_*` trong `CHECK_IN/PRE_TREATMENT`; không quyết định obligation state.
- Module 04 phát hành post-treatment data tại `POST_TREATMENT`; portal không dùng staff Encounter API.
- Module 05 sở hữu task/handoff/schedule conflict.
- Module 06 sở hữu policy evaluator, obligation/task reconciliation, audit/dashboard và shared bootstrap.

## Acceptance và verification

- Patient không đọc được staff Encounter API.
- Role, skip/backward và stale version đều bị từ chối đúng contract.
- Guard stage chỉ xét obligations cần cho transition đích.
- Concurrent transition chỉ có một winner.
- Close chỉ thành công khi full policy ready và appointment được `FULFILLED` atomically.
- Transition history không chứa raw note/chat.

Chạy test module bằng:

```powershell
python -m unittest tests.encounter.test_encounter -v
```

PostgreSQL concurrency/full-flow được chạy khi đặt `ENCOUNTER_TEST_DATABASE_URL`; hướng dẫn môi trường thống nhất nằm trong `README.md`.
