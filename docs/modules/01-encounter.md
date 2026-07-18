# Module 01 — Encounter

## Mục tiêu và pain point
Cho mọi module cùng một patient/appointment/encounter context và timeline; tránh thao tác nhầm ca hoặc mất trạng thái khi chuyển bước.

## Phạm vi / không làm
Hiển thị hồ sơ synthetic, header, năm stage và chỉ cho chuyển sang stage kế tiếp. Không đánh giá compliance, không chứa form chuyên môn, không xây scheduling.

## Đường dẫn sở hữu
`backend/app/features/encounter/`, `frontend/src/features/encounter/`, `tests/encounter/`, `db/init/10_encounter.sql` (chỉ khi thật sự cần).

## Consumes / produces
React export bắt buộc: `export const route = { path, label, Component }`; integrator import vào `frontend/src/routes.js`.
- Đọc core `patients`, `appointments`, `encounters`; dùng `EncounterStage` và `X-Demo-Role`.
- `GET /api/v1/encounters/{id}` → patient, appointment, encounter, `stage`, `version`, `next_stage`, `can_advance`.
- `GET /api/v1/encounters/{id}/transitions` → stage transition history từ audit-safe metadata.
- `POST /api/v1/encounters/{id}/stage` body `{stage, version}` → encounter mới và append transition audit; lỗi `{code,message,details}`.
- Không tạo evidence.

## Các bước
1. Test lookup ca demo, transition hợp lệ, skip/backward và stale version bị từ chối.
2. Viết router/repository tối thiểu và React route timeline.
3. Export `router` và `route`; không nối registry.

## Acceptance
Mở được UUID seed; đi đúng năm stage không mất context/version; stage skip/backward hoặc version cũ trả lỗi rõ ràng.

## Handoff integrator
Router export: `backend.app.features.encounter:router`, prefix `/api/v1/encounters`.
Route export: `frontend/src/features/encounter/index.jsx:route`, URL `/encounter`.
Verification hiện tại: unit/HTTP suite — 23 passed; PostgreSQL concurrency test — 1 passed khi đặt `ENCOUNTER_TEST_DATABASE_URL`; backend compile và frontend production build pass. Không có biến DB thì concurrency test chủ động skip. Base implementation commit `1914561`; follow-up hardening/integration đang ở working tree và cần ghi commit hash khi bàn giao.

Integration exception: theo yêu cầu chạy demo đồng nhất cho cả nhóm, router/route đã được nối vào shared bootstrap ngay trên working tree này; Vite proxy dùng `api:8000` trong Compose và `localhost:8000` khi chạy local.

## Ghi chú ownership cho các AI agent

Nhánh `feat/encounter` chỉ sở hữu context patient/appointment/encounter, timeline năm stage và primitive chuyển đúng stage kế tiếp bằng optimistic `version`. Không sửa shared bootstrap, registry, navigation, core contract/schema hoặc Compose từ nhánh này.

| Việc cần xử lý | Owner / nơi xử lý | Handoff từ Encounter |
| --- | --- | --- |
| Đăng ký FastAPI router | `feat/compliance-integration` — app bootstrap/router registry | Import `backend.app.features.encounter:router`; không viết lại endpoint. |
| Đăng ký và render React route `/encounter` | `feat/compliance-integration` — registry/navigation/app shell | Import `frontend/src/features/encounter/index.jsx:route`; app shell phải render `Component`, không chỉ tạo link. |
| Readiness, evaluate, finding, task và audit | `feat/compliance-integration` | Dùng `encounter_id`, `stage`, `version`; Encounter không tạo evidence/check/task. Nếu đóng ca cần compliance gate, integrator điều phối evaluate/readiness trước transition, không đưa rule vào Encounter. |
| Form, note và AI evidence | `feat/documentation-ai` | Dùng encounter context; evidence thuộc nhóm `DOC_*`. Không cập nhật stage trực tiếp. |
| Checklist an toàn trước điều trị | `feat/pre-treatment` | Dùng encounter context; ghi evidence `PRE_*` và audit qua core seam. Evaluator, không phải Encounter, quyết định obligation state. |
| Release, hướng dẫn và patient chat | `feat/post-treatment-chat` | Chỉ dùng released data; không ghi raw chat vào Encounter response hoặc audit metadata. |
| Worklist, handoff và overlap | `feat/coordination` | Dùng task/appointment và encounter reference; acknowledgment, owner và idempotency không thuộc Encounter. |
| Scheduling/check-in tạo hoặc ghép Encounter | shared/integration nếu demo cần | Appointment là kế hoạch, Encounter là ca thực tế; thao tác tạo/ghép phải idempotent và không nằm trong phạm vi module 01. |
| Khác biệt schema demo và kiến trúc đích | shared foundation/integration | Demo dùng năm `EncounterStage`; kiến trúc đích dùng lifecycle `PLANNED/IN_PROGRESS/ON_HOLD/PRE_CLOSE/...`. Không tự đổi enum/schema trên nhánh Encounter; cần mapping/ADR dùng chung trước. |
| Test/build portability và dependency setup | shared foundation/integration | Makefile, dependency manifest, UTF-8 test và CI là file shared; Encounter chỉ duy trì `tests/encounter/`. |

Các agent khác không nên sửa `backend/app/features/encounter/`, `frontend/src/features/encounter/` hoặc `tests/encounter/` để giải quyết vấn đề integration. Nếu cần thay contract, ghi yêu cầu trong handoff và để integrator điều phối thay đổi shared.

## Thiết kế trước implementation

Phần này chốt contract ở mức thiết kế cho `feat/encounter` và ghi rõ handoff liên module. Nó không cấp quyền cho nhánh Encounter sửa core enum/schema hoặc file shared.

### 1. Ranh giới target product và dental demo

| Chủ đề | Target product | Dental demo khóa phạm vi | Quyết định cho `feat/encounter` |
| --- | --- | --- | --- |
| Phạm vi | HIS/EHR/PMS, Patient Portal, bốn specialty | Một encounter nha khoa synthetic | Chỉ triển khai dental demo; giữ response nhỏ và không giả lập toàn bộ EHR. |
| Identity | OIDC, tenant/facility scope, patient/proxy grant, RLS | `X-Demo-Role` với năm role cố định | Dùng contract demo; không thêm OIDC/RLS cục bộ. |
| Encounter lifecycle | `PLANNED`, `IN_PROGRESS`, `ON_HOLD`, `PRE_CLOSE`, `COMPLETED`, `CANCELLED`, `ENTERED_IN_ERROR` | Timeline năm stage | Không đồng nhất `status` với `stage`; module 01 chỉ sở hữu `stage`. |
| Clinical record | FHIR-shaped resource, version/signature/amendment | Evidence tối thiểu qua core services | Encounter chỉ đọc context; không tạo clinical resource/evidence. |
| Compliance | Versioned Policy Pack, obligation history, decision/override | `dental-policy.v1`, evaluator cố định | Module 06 sở hữu readiness/evaluate; Encounter không nhúng rule. |
| AI | Model/prompt/source links, abstain, human review | Fixture fallback, output Draft/Unverified | Không gọi model từ Encounter. |
| Integration | Idempotent ingest/check-in, worker/jobs, ACK/reconciliation | Seed PostgreSQL và route integration | Encounter nhận UUID đã tồn tại; không xây scheduling/check-in. |

Nguyên tắc tương thích: demo có thể là tập con của target, nhưng không được tạo coupling khiến target phải coi dental stage là encounter lifecycle chung hoặc cho patient dùng staff scope.

### 2. Chuẩn hóa state machine

#### 2.1 Appointment status — owner shared/integration

Target transition đề xuất:

```text
PENDING → BOOKED → ARRIVED → CHECKED_IN → FULFILLED
    └──────────────→ CANCELLED
BOOKED ────────────→ NO_SHOW
```

- Appointment là kế hoạch; `CHECKED_IN` có thể tạo/ghép tối đa một Encounter bằng idempotency key.
- Module 01 chỉ đọc appointment hiện tại. Không mutation appointment status.
- Demo seed bắt đầu tại `CHECKED_IN`; không cần triển khai toàn state machine trên nhánh Encounter.

#### 2.2 Encounter status — owner EHR/shared

Target transition đề xuất:

```text
PLANNED → IN_PROGRESS ↔ ON_HOLD → PRE_CLOSE → COMPLETED
   ├──────────────→ CANCELLED
   └──────────────→ ENTERED_IN_ERROR
IN_PROGRESS/PRE_CLOSE ─────────→ ENTERED_IN_ERROR
```

- `COMPLETED` yêu cầu authorization, validation và signature.
- `ENTERED_IN_ERROR` không phải delete; lịch sử và audit vẫn còn.
- Demo chưa có cột/status contract này. Không thêm vào core schema từ module 01.

#### 2.3 Workflow stage — owner Encounter trong demo

```text
CHECK_IN → PRE_TREATMENT → TREATMENT → POST_TREATMENT → CLOSED
```

Quy tắc:

- Chỉ đi đúng một bước; không skip, backward hoặc reopen.
- Mọi mutation gửi `version`; stale version trả `409 STALE_ENCOUNTER_VERSION`.
- `PATIENT` và `QA` không chuyển stage.
- Mapping định hướng, không phải schema migration:

| Workflow stage | Encounter status target tương ứng |
| --- | --- |
| `CHECK_IN` | `PLANNED` hoặc vừa chuyển `IN_PROGRESS` khi check-in hoàn tất |
| `PRE_TREATMENT` | `IN_PROGRESS` |
| `TREATMENT` | `IN_PROGRESS` |
| `POST_TREATMENT` | `IN_PROGRESS` |
| `CLOSED` | `COMPLETED`; trước đó nên đi qua `PRE_CLOSE` ở orchestration target |

Nếu demo yêu cầu compliance gate trước `CLOSED`, module 06 phải orchestration `evaluate/readiness` rồi mới gọi primitive chuyển stage. Module 01 không đọc obligation tables.

#### 2.4 Clinical resource status — owner Documentation/EHR

Target nên tách lifecycle envelope khỏi status chuyên biệt trong payload:

```text
DRAFT → FINAL/SIGNED → AMENDED
  └───────────────→ ENTERED_IN_ERROR
```

- `FINAL/SIGNED` bất biến; sửa bằng version/amendment mới.
- Patient chỉ đọc resource đã release; release không đồng nghĩa với signed status.
- Demo module 02 dùng evidence `DRAFT/VERIFIED`; đây không phải enum thay thế clinical resource status.

#### 2.5 Obligation state — owner Compliance

Target đầy đủ:

```text
PENDING → SATISFIED | MISSING | UNVERIFIED | CONFLICTING
        | NOT_APPLICABLE | OVERRIDDEN | EXPIRED
```

Demo chỉ dùng `PENDING`, `MISSING`, `UNVERIFIED`, `SATISFIED`, `NOT_APPLICABLE`. Không silently map `CONFLICTING`, `OVERRIDDEN` hoặc `EXPIRED` sang `SATISFIED`; nếu gặp ngoài phạm vi demo, giữ trạng thái an toàn (`UNVERIFIED/MISSING`) với `reason_code`, hoặc abstain.

#### 2.6 Task status — owner Coordination

```text
OPEN → ACKNOWLEDGED → COMPLETED
  └────────────────→ CANCELLED
ACKNOWLEDGED ──────→ CANCELLED
```

- Acknowledge không đồng nghĩa Complete.
- Complete cần evidence, cancellation hoặc human decision hợp lệ.
- Escalation cập nhật cùng task; không clone task.

### 3. Traceability matrix

| Requirement / acceptance | Entity/contract | API/module | Test/acceptance cần có | Owner |
| --- | --- | --- | --- | --- |
| FR-ENC-001: encounter khóa đúng patient/context | `encounters.patient_id`, appointment join, response context | `GET /api/v1/encounters/{id}` | UUID seed trả đúng patient, appointment, stage, version | Encounter |
| FR-ENC-002: timeline có source/time/version/correlation | Target timeline event; demo hiện chỉ có `stage/version` | `POST .../{id}/stage` + audit ở integration | Transition giữ version; integration audit có correlation ID | Encounter + Integration |
| Không skip/backward | `EncounterStage` ordered transition | `POST .../{id}/stage` | Skip và backward trả `INVALID_STAGE_TRANSITION` | Encounter |
| Optimistic concurrency | `encounters.version` | `POST .../{id}/stage` | Hai request cùng version: tối đa một request thành công | Encounter |
| Role boundary | `X-Demo-Role` | GET/POST Encounter | Patient/QA bị cấm mutation; staff role hợp lệ được phép | Encounter |
| FR-PMS-001 / DB AC-02: check-in tạo tối đa một encounter | appointment/encounter unique or idempotency contract | `POST /appointments/{id}/check-in` | Retry không tạo encounter thứ hai | Integration/shared |
| FR-EVD-001/002: evidence có nguồn/actor/AI span | `evidence_items`, AI run/source span | module 02/03/04 | Draft không satisfied; accept giữ source; attestation có actor/time | Documentation/Pre-treatment/Post-treatment |
| FR-CMP-002/003: deterministic và idempotent | obligation check + policy version | evaluate/readiness | Re-evaluate không clone current finding/task | Compliance |
| AC-04: task đúng owner/SLA | `tasks` | task worklist/ack/complete | Acknowledge bắt buộc; escalation idempotent | Coordination |
| AC-09: portal không lộ draft | released summary/resource gate | release/chat/portal | Patient không đọc draft hoặc staff-only data | Post-treatment + Integration |
| Audit không có raw PHI/chat | `audit_events.metadata` allowlist | mọi mutation qua integration/core seam | Audit có actor/action/object/time/correlation, không raw body | Integration |

Khoảng trống có chủ đích của demo: timeline event append-only, policy pinning đầy đủ, tenant/facility scope và RLS thuộc target/shared; không tự bổ sung trong module 01.

### 4. Policy/evidence contract trước UI

Encounter không tạo evidence nhưng cung cấp context ổn định để các module khác ghi evidence. Contract tối thiểu cần giữ:

```text
Evidence input
- encounter_id
- code (namespace DOC_*, PRE_*, POST_*, COORD_*)
- state: DRAFT | VERIFIED
- value: structured JSON, không chứa binary
- source_type và source_ref
- actor_role
- observed/performed time khi module yêu cầu
- AI source_span + ai_run_id khi do AI trích xuất
```

Quy tắc policy/evidence:

1. Chỉ `dental-policy.v1` được evaluator demo sử dụng.
2. Structured/signed hoặc authorized attestation có thể là `VERIFIED`; AI output luôn bắt đầu `DRAFT/UNVERIFIED`.
3. Confidence không thay thế evidence, actor hoặc source reference.
4. Stale/conflicting/missing source không được thành `SATISFIED`.
5. Re-evaluation idempotent và không sửa lịch sử của policy version cũ.
6. UI chỉ trình bày finding/evidence; không tự tính obligation state.
7. Encounter response không mở rộng để nhét form, evidence, finding hoặc task; dùng API module tương ứng.

### 5. Dental vertical slice end-to-end

| Bước | Hành vi | Module chịu trách nhiệm | Kết quả kiểm chứng |
| --- | --- | --- | --- |
| 1 | Mở UUID encounter seed | Encounter | Đúng patient/appointment, `CHECK_IN`, version 1 |
| 2 | Chuyển `PRE_TREATMENT` | Encounter | Atomic transition, version tăng |
| 3 | Ghi medical history/allergy/sterilization; imaging theo điều kiện | Pre-treatment | Evidence `PRE_*` có actor/time |
| 4 | Evaluate lần đầu | Compliance | Thiếu evidence thành Missing; task không trùng |
| 5 | Nhập consent/treatment plan/note/tooth-surface | Documentation AI | AI fact là Unverified; human accept mới Verified |
| 6 | Chuyển `TREATMENT` và evaluate lại | Encounter + Compliance orchestration | Context không đổi; obligation cập nhật deterministic |
| 7 | Tạo/acknowledge handoff hoặc xử lý overlap | Coordination | Đúng owner; acknowledge/complete tách biệt |
| 8 | Chuyển `POST_TREATMENT`, tạo instruction/recall | Encounter + Post-treatment | Evidence `POST_*`; released summary tách draft |
| 9 | Patient chat từ released source | Post-treatment | Citation hoặc abstain; red flag luôn escalation; không lưu raw chat |
| 10 | Full evaluate/pre-close rồi chuyển `CLOSED` | Compliance Integration + Encounter | Không bypass gate do integrator quy định; version cuối đúng |
| 11 | Xem audit/readiness/dashboard | Compliance Integration | Trace policy → evidence → rule → human/task; không PHI thô |

### 6. Transaction và idempotency boundary

| Operation | Transaction boundary | Concurrency/idempotency rule | Owner |
| --- | --- | --- | --- |
| Read encounter | Một read transaction ngắn | Không side effect | Encounter |
| Advance stage | Đọc/validate và `UPDATE ... WHERE id=? AND version=?` trong một DB transaction | Optimistic version; một winner; stale trả 409 | Encounter |
| Appointment check-in → Encounter | Một transaction cho lookup/create/link | Unique appointment link + organization-scoped idempotency key | Integration/shared |
| Upsert evidence | Một transaction mỗi logical evidence write | Unique `(encounter_id, code)` trong demo; retry trả logical result cũ | Module 02–04 + core |
| Accept AI output | Target cần một transaction cho review state + verified evidence + audit/outbox | Cùng AI output chỉ accept/reject một lần | Documentation AI; nếu core seam không đủ thì handoff Integration |
| Evaluate | Một transaction cho current checks và ensure task, hoặc outbox nhất quán | Key `encounter:obligation:dental-policy.v1`; retry không clone task | Compliance |
| Acknowledge/complete task | Atomic conditional update theo current status | Retry cùng action không tạo transition phụ | Coordination |
| Release summary | Atomic mark released + audit/outbox | Chỉ release approved content; retry trả cùng release | Post-treatment |
| Chat | Read-only source retrieval; escalation task dùng transaction riêng/idempotent | Không dùng raw message làm idempotency key hoặc audit metadata | Post-treatment + Coordination |

Không tạo distributed transaction giữa module. Khi một action cần DB state và side effect ngoài hệ thống, ghi DB state + outbox/job trước, worker giao tiếp ngoài và reconcile bằng idempotency key.

### 7. Authorization matrix

Ký hiệu: `R` đọc, `W` mutation, `—` không được phép. Đây là contract demo; target phải thay header role bằng identity/grant/RLS tương ứng.

| Action | FRONT_DESK | ASSISTANT | DENTIST | PATIENT | QA | WORKER target |
| --- | --- | --- | --- | --- | --- | --- |
| Đọc encounter synthetic | R | R | R | R trong demo | R | R theo purpose |
| Chuyển workflow stage | W | W | W | — | — | — |
| Ghi pre-treatment attestation | Theo module 03 | W theo module 03 | W theo module 03 | — | R/audit nếu được cấp | — |
| Accept/reject AI clinical fact | — hoặc theo module 02 | Theo policy module 02 | W | — | R/audit | — |
| Evaluate/readiness | R | R | R | — | R | W cho scheduled evaluation |
| Task acknowledge/complete | Theo owner_role | Theo owner_role | Theo owner_role | — | R/audit | W chỉ escalation job |
| Đọc released portal content/chat | — | — | — | R | R/audit theo quyền | R tối thiểu theo purpose |
| Đọc draft clinical content | Theo staff scope | Theo staff scope | Theo staff scope | — | Theo compliance scope | R tối thiểu theo purpose |
| Publish policy/override hard-stop | — | — | — | — | Target compliance/admin, demo không làm | — |

Lưu ý an toàn:

- `PATIENT` đọc encounter staff endpoint chỉ chấp nhận được vì dữ liệu demo là synthetic. Target phải dùng portal API và release/access grant.
- Browser không quyết định tenant/role; `X-Demo-Role` chỉ là cơ chế demo.
- Worker không có quyền lâm sàng chung; mỗi job dùng service identity và purpose-bound query.
- Mutation bị từ chối không được rò PHI/source text trong error.

### 8. Exit criteria trước khi mở rộng schema/code

1. Integrator xác nhận mapping `Encounter status` và `Workflow stage` là hai state machine riêng.
2. Owner module 02–06 xác nhận evidence code, API export và ownership ở bảng trên.
3. Compliance xác nhận gate trước `CLOSED` nằm ở orchestration, không thay đổi endpoint Encounter âm thầm.
4. Shared owner xác nhận transaction nào cần atomic audit/outbox thay vì gọi nhiều core service transaction rời.
5. Authorization demo được test; target portal/staff scope được ghi là deferred, không giả an toàn bằng UI.
6. Traceability rows có test owner rõ; không để module Encounter nhận test của feature khác.
7. Chỉ sau các xác nhận trên mới đề xuất thay core enum/schema/shared registry.
