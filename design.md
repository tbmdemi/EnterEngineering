# CareGuard — Đặc tả Clinical Compliance & Operations Copilot

> Phiên bản: 2.0
> Ngày: 17/07/2026
> Độc giả chính: Product, Engineering, Clinical, QA, Security và đội thi hackathon
> Thị trường giả định: phòng khám ngoại trú quy mô nhỏ tại Việt Nam
> Trạng thái lâm sàng: mọi Policy Pack phải được bác sĩ phụ trách duyệt trước khi dùng thực tế

Tài liệu liên quan:

- [Đặc tả database](2026-07-17-careguard-database-design.md)
- [Thiết kế kiến trúc](2026-07-17-careguard-architecture-design.md)

---

## 1. CareGuard trong ba phút

Một lượt khám có thể hoàn tất về mặt điều trị nhưng vẫn còn thiếu consent, tiền sử dị ứng, kết quả khám, hướng dẫn sau khám hoặc lịch follow-up. Những phần thiếu này thường chỉ được phát hiện khi đã quá muộn: lúc audit, khi bệnh nhân gọi lại hoặc khi xảy ra tranh chấp.

CareGuard là lớp kiểm tra tuân thủ chạy bên cạnh phần mềm quản lý phòng khám hiện có. Hệ thống không chẩn đoán và không kê đơn. Nó trả lời năm câu hỏi:

1. Với lượt khám này, quy trình nào đang áp dụng?
2. Mỗi bước bắt buộc cần bằng chứng gì?
3. Bằng chứng đã có, còn thiếu hay đang mâu thuẫn?
4. Ai phải xử lý và hạn xử lý là khi nào?
5. Quyết định cuối cùng đã được ghi nhận và audit chưa?

```text
Lượt khám
   ↓
Chọn Policy Pack phù hợp
   ↓
Đọc dữ liệu và tìm Evidence
   ↓
Đánh giá từng Obligation
   ↓
Hiển thị cảnh báo hoặc giao Task
   ↓
Nhân viên xử lý / bác sĩ xác nhận
   ↓
Follow-up → Audit → KPI
```

### 1.1 Bốn khái niệm cần biết

| Khái niệm | Giải thích đơn giản | Ví dụ |
| --- | --- | --- |
| Policy Pack | Bộ quy trình đã được phê duyệt cho một nhóm ca | “Khám đau tai/viêm tai” |
| Obligation | Một điều bắt buộc phải kiểm tra, ghi nhận hoặc thực hiện | “Phải có kết quả soi tai” |
| Evidence | Dữ liệu chứng minh obligation đã được đáp ứng | Trường `otoscopy_result` trong hồ sơ |
| Finding | Kết luận của CareGuard về obligation | Missing, Unverified hoặc Satisfied |

### 1.2 CareGuard không làm gì

- Không thay thế HIS/EHR/PMS.
- Không đưa ra chẩn đoán thay bác sĩ.
- Không tự chọn thuốc, liều hoặc phác đồ.
- Không tự ký hồ sơ, gửi đơn hoặc đóng encounter.
- Không coi nội dung AI tạo là bằng chứng đã được xác nhận.
- Không biến guideline quốc tế thành quy định tại Việt Nam nếu chưa được clinical owner phê duyệt.

---

## 2. Một lượt khám diễn ra như thế nào

Đây là flow chung cho cả Tai Mũi Họng, Da liễu và Phụ khoa. Mỗi Policy Pack chỉ thay đổi các bước chuyên khoa và evidence cần thu thập.

### Bước 1 — Tiếp nhận

Lễ tân mở hoặc nhập encounter từ dữ liệu mock/HIS. CareGuard kiểm tra:

- Đúng người bệnh và đúng lượt khám.
- Thông tin định danh tối thiểu.
- Lý do khám và chuyên khoa.
- Người phụ trách hiện tại.

Nếu thiếu dữ liệu hành chính, task thuộc về lễ tân; bác sĩ không bị làm phiền.

### Bước 2 — Consent và quyền riêng tư

Hệ thống kiểm tra consent theo loại khám và thủ thuật. Consent ở trạng thái Draft không được xem là Signed. Người bệnh có thể từ chối; hệ thống ghi nhận từ chối thay vì ngăn quyền được khám.

### Bước 3 — Sàng lọc an toàn

Điều dưỡng hoặc bác sĩ ghi nhận tiền sử, dị ứng, thuốc đang dùng, thai kỳ khi liên quan và dấu hiệu cần chuyển tuyến/cấp cứu. CareGuard chỉ kiểm tra dữ liệu có được ghi nhận hay chưa; đánh giá chuyên môn thuộc về bác sĩ.

### Bước 4 — Khám chuyên khoa

Policy Pack sinh checklist theo specialty. Mỗi bước có:

- Điều kiện áp dụng.
- Evidence được chấp nhận.
- Vai trò chịu trách nhiệm.
- Severity nếu thiếu.
- Nguồn guideline và phiên bản.

### Bước 5 — Ghi nhận đánh giá và kế hoạch

CareGuard kiểm tra hồ sơ có assessment, plan, hướng dẫn và quyết định referral/follow-up hay chưa. Hệ thống không đánh giá kế hoạch đó đúng hay sai về chuyên môn, trừ các rule an toàn đã được clinical owner duyệt rõ ràng.

### Bước 6 — Pre-close review

Trước khi đóng encounter, CareGuard gom finding thành ba nhóm:

- **Must resolve:** không nên đóng khi chưa xử lý.
- **Needs review:** cần người có thẩm quyền xác nhận.
- **Follow-up:** không chặn đóng encounter nhưng phải có owner và deadline.

Người dùng mở finding để thấy: thiếu gì, bằng chứng hiện có, điều khoản nguồn, ai cần xử lý và nút hành động.

### Bước 7 — Handoff và follow-up

Task sau khám có một owner hiện tại, due date và escalation rule. Khi chuyển ca, người nhận phải acknowledge. Task chỉ đóng khi có evidence, cancellation hợp lệ hoặc override có lý do.

### Bước 8 — Audit và cải tiến

CareGuard lưu policy version, rule, evidence, AI run, hành động người dùng và kết quả cuối. Dashboard chỉ dùng dữ liệu tổng hợp để đo lỗi được ngăn chặn, task quá hạn và alert precision.

---

## 3. Ai sử dụng hệ thống

| Vai trò | CareGuard hiển thị | Hành động được phép |
| --- | --- | --- |
| Lễ tân | Dữ liệu hành chính, consent, lịch và task follow-up | Bổ sung hành chính, giao lịch, acknowledge handoff |
| Điều dưỡng/trợ lý | Sàng lọc, sinh hiệu, checklist chuẩn bị | Ghi nhận dữ liệu, attestation trong phạm vi được giao |
| Bác sĩ | Readiness brief, evidence và pre-close findings | Xác nhận, sửa dữ liệu nguồn, resolve hoặc override theo quyền |
| QA/Compliance | Policy, override, audit và xu hướng lỗi | Draft/review/publish/retire Policy Pack |
| Clinic Manager | SLA, queue và bottleneck | Điều phối owner, escalation và báo cáo |
| Integration Admin | Connector health và reconciliation | Mapping, replay job và xử lý lỗi tích hợp; không mặc định xem PHI |

Nguyên tắc UX: không tạo một inbox mới phải canh. CareGuard xuất hiện dưới dạng worklist hoặc sidebar cạnh workflow hiện tại, gom cảnh báo ít nguy cơ ở checkpoint và chỉ ngắt luồng với hard-stop đã được phê duyệt.

---

## 4. Ba Policy Pack chuyên khoa

### 4.1 Tai Mũi Họng — Đau tai/viêm tai

Nguồn baseline: WHO *Primary ear and hearing care: training manual*, đặc biệt module về viêm tai giữa, biến chứng và referral. Policy Pack production phải được bác sĩ Tai Mũi Họng điều chỉnh theo cơ sở.

| Bước | Nội dung CareGuard kiểm tra | Evidence tối thiểu | Khi thiếu |
| --- | --- | --- | --- |
| 1 | Lý do khám, bên tai, thời điểm và diễn tiến được ghi nhận | Structured history hoặc note đã ký | Needs review |
| 2 | Tiền sử tai, can thiệp trước đó, thuốc/dị ứng liên quan được rà soát | History fields | Missing |
| 3 | Dấu hiệu nguy hiểm/biến chứng đã được sàng lọc | Red-flag checklist + actor | Must resolve |
| 4 | Khám tai và quan sát ống tai/màng nhĩ được ghi nhận | Otoscopy result | Must resolve |
| 5 | Khả năng nghe hoặc lý do không đánh giá được được ghi nhận khi áp dụng | Hearing assessment/attestation | Needs review |
| 6 | Assessment và quyết định xử trí/referral thuộc về bác sĩ | Signed assessment/plan | Must resolve |
| 7 | Người bệnh có hướng dẫn dấu hiệu cần quay lại | Approved instruction | Follow-up |
| 8 | Follow-up/referral có owner, thời điểm và trạng thái | Task/appointment evidence | Follow-up |

CareGuard không tự kết luận viêm tai, không phân loại mức độ và không đề xuất thuốc. AI chỉ có thể tìm source span trong note và gắn trạng thái Unverified cho đến khi rule/evidence cho phép xác nhận.

### 4.2 Da liễu — Mụn trứng cá

Nguồn baseline: NICE NG198 *Acne vulgaris: management*; guideline phải được bác sĩ Da liễu và cơ sở điều chỉnh cho bối cảnh Việt Nam.

| Bước | Nội dung CareGuard kiểm tra | Evidence tối thiểu | Khi thiếu |
| --- | --- | --- | --- |
| 1 | Thời gian mắc, vị trí, điều trị trước và đáp ứng được ghi nhận | History fields/note | Needs review |
| 2 | Mức độ ảnh hưởng chất lượng sống và sức khỏe tinh thần được hỏi | Screening/attestation | Needs review |
| 3 | Thuốc, bệnh lý liên quan và khả năng mang thai được rà soát khi kế hoạch điều trị yêu cầu | Medication/history fields | Must resolve theo rule |
| 4 | Vị trí, loại tổn thương, mức độ và nguy cơ sẹo được mô tả | Exam fields hoặc ảnh có consent | Must resolve |
| 5 | Assessment, lựa chọn điều trị và thảo luận lợi ích/rủi ro được bác sĩ ghi nhận | Signed plan | Must resolve |
| 6 | Nếu có kháng sinh/thuốc nguy cơ cao, các kiểm tra an toàn đã được policy yêu cầu phải có | Policy-specific evidence | Must resolve |
| 7 | Hướng dẫn chăm sóc, tuân thủ và khi nào cần liên hệ lại đã được cung cấp | Approved instruction | Follow-up |
| 8 | Lịch review, đánh giá đáp ứng và referral khi cần có owner | Task/appointment | Follow-up |

Rule về thuốc, thai kỳ, xét nghiệm hoặc referral chỉ được publish khi clinical owner xác nhận nguồn và wording. CareGuard không suy ra chống chỉ định từ hội thoại nếu chưa có dữ liệu được xác nhận.

### 4.3 Phụ khoa — Tầm soát ung thư cổ tử cung

Nguồn ưu tiên: hướng dẫn dự phòng và kiểm soát ung thư cổ tử cung của Bộ Y tế Việt Nam; đối chiếu WHO *Guideline for screening and treatment of cervical pre-cancer lesions*. Nội dung eligibility, test và follow-up phải được cơ sở cấu hình theo chương trình đang áp dụng.

| Bước | Nội dung CareGuard kiểm tra | Evidence tối thiểu | Khi thiếu |
| --- | --- | --- | --- |
| 1 | Danh tính, eligibility và lịch sử sàng lọc được xác nhận | Patient + screening history | Needs review |
| 2 | Consent, quyền riêng tư và người thực hiện đúng thẩm quyền | Signed consent + practitioner | Must resolve |
| 3 | Thông tin ảnh hưởng đến thời điểm/phương pháp lấy mẫu được rà soát | Pre-screen checklist | Must resolve theo policy |
| 4 | Loại test, mẫu, thời điểm và chất lượng mẫu được ghi nhận | Screening procedure record | Must resolve |
| 5 | Kết quả được nhận, xác minh và liên kết đúng người bệnh | Signed result + patient match | Must resolve |
| 6 | Kết quả được phân tuyến theo algorithm đã publish | Deterministic rule output | Must resolve |
| 7 | Người bệnh được thông báo bằng nội dung/kênh được phê duyệt | Communication evidence | Follow-up |
| 8 | Tái khám, xét nghiệm tiếp hoặc referral có owner và SLA | Task/appointment/referral | Follow-up |

AI không tự diễn giải kết quả thành chẩn đoán. Phân tuyến chỉ dùng deterministic rule đã được publish; kết quả bất thường chưa có follow-up phải được escalation.

---

## 5. CareGuard đánh giá một obligation

### 5.1 Trạng thái

```text
PENDING
  ├─ SATISFIED
  ├─ MISSING
  ├─ UNVERIFIED
  ├─ CONFLICTING
  ├─ NOT_APPLICABLE
  ├─ OVERRIDDEN
  └─ EXPIRED
```

| Trạng thái | Ý nghĩa |
| --- | --- |
| Satisfied | Có evidence đúng loại, còn hiệu lực và đáp ứng rule |
| Missing | Rule áp dụng nhưng không có evidence |
| Unverified | Có dấu hiệu trong note/draft nhưng chưa đủ thẩm quyền xác nhận |
| Conflicting | Hai nguồn mâu thuẫn; hệ thống không tự chọn nguồn đúng |
| Not applicable | Điều kiện áp dụng không đúng hoặc đã được xác nhận không áp dụng |
| Overridden | Người có quyền chấp nhận ngoại lệ và ghi lý do |
| Expired | Quá hạn mà chưa có trạng thái cuối hợp lệ |

### 5.2 Evidence hierarchy

1. Dữ liệu có cấu trúc hoặc tài liệu đã ký trong system of record.
2. Event tích hợp có ACK và provenance.
3. Manual attestation của vai trò có thẩm quyền.
4. Draft note hoặc fact do AI trích xuất — chỉ đủ cho Unverified nếu policy không quy định khác.

Không có evidence thì để Missing. Confidence của model không thay thế evidence.

### 5.3 Policy lifecycle

```text
DRAFT → CLINICAL_REVIEW → APPROVED → PUBLISHED → RETIRED
```

- Chỉ `PUBLISHED` được chạy trong production.
- Policy version mới không viết lại lịch sử encounter cũ.
- Hard-stop cần hai người phê duyệt và có kill switch.
- Policy mới có thể chạy shadow để đo false positive trước khi bật.

---

## 6. Yêu cầu chức năng

### 6.1 Policy và governance

| ID | Yêu cầu |
| --- | --- |
| FR-POL-001 | Policy Pack phải có source, version, phạm vi, clinical owner và approval state. |
| FR-POL-002 | Mỗi obligation phải khai báo applicability, evidence rule, owner, SLA, severity và citation. |
| FR-POL-003 | Chỉ version Published được đánh giá encounter production. |
| FR-POL-004 | Publish/retire/hard-stop/override policy phải được audit. |
| FR-POL-005 | Hệ thống hỗ trợ shadow evaluation và kill switch theo Policy Pack. |

### 6.2 Encounter và evidence

| ID | Yêu cầu |
| --- | --- |
| FR-ENC-001 | Một encounter phải khóa với một patient reference, facility và specialty. |
| FR-ENC-002 | Timeline event phải có source, occurred time, version và correlation ID. |
| FR-EVD-001 | Evidence phải chỉ rõ source type, source reference, status, observed time và actor khi có. |
| FR-EVD-002 | AI evidence phải kèm exact source span và AI run version. |
| FR-EVD-003 | Dữ liệu stale hoặc conflict không được tự chuyển thành Satisfied. |

### 6.3 Evaluation và task

| ID | Yêu cầu |
| --- | --- |
| FR-CMP-001 | Rule engine tạo obligation instances theo encounter context và Policy Pack. |
| FR-CMP-002 | Chỉ rule deterministic quyết định applicability, final state và hard-stop. |
| FR-CMP-003 | Evaluation lặp lại phải idempotent và giữ lịch sử transition. |
| FR-CMP-004 | Finding phải giải thích thiếu gì, evidence nào được dùng và điều khoản nào áp dụng. |
| FR-TSK-001 | Mỗi finding actionable có tối đa một owner hiện tại, due date và escalation rule. |
| FR-TSK-002 | Handoff cần acknowledgment; escalation không tạo task trùng. |
| FR-TSK-003 | Task chỉ đóng bằng evidence, cancellation hoặc human decision hợp lệ. |

### 6.4 AI và human control

| ID | Yêu cầu |
| --- | --- |
| FR-AI-001 | AI chỉ trích xuất fact, source span và explanation trong schema được kiểm tra. |
| FR-AI-002 | Mỗi run lưu model, prompt, policy/retrieval version, latency và result status. |
| FR-AI-003 | Khi không đủ nguồn, AI phải abstain. |
| FR-AI-004 | AI không được gọi write API lâm sàng, ký, kê đơn hoặc đóng encounter. |
| FR-HUM-001 | Resolve, Not applicable và Override phải lưu actor, reason và timestamp. |
| FR-HUM-002 | Hard-stop override yêu cầu quyền riêng, reason và re-authentication. |

### 6.5 Audit, privacy và integration

| ID | Yêu cầu |
| --- | --- |
| FR-AUD-001 | Audit append-only cho view, evaluation, assignment, decision, policy và integration action. |
| FR-AUD-002 | Không ghi PHI, note body hoặc prompt thô vào application log. |
| FR-INT-001 | Prototype nhận ba mock encounter qua một JSON contract chung. |
| FR-INT-002 | Ingest, evaluation và write-back dùng idempotency key. |
| FR-INT-003 | Không hiển thị Synced/Completed trước ACK hoặc reconciliation. |

---

## 7. AI-native nhưng không giao quyền lâm sàng cho AI

| Hoạt động | AI | Rule engine | Con người |
| --- | --- | --- | --- |
| Tìm fact trong note | Đề xuất + source span | Validate schema | Sửa/xác nhận khi cần |
| Chọn obligation áp dụng | Có thể hỗ trợ metadata | Quyết định | Override theo quyền |
| Đánh dấu Satisfied | Không | Quyết định theo evidence rule | Attest/override |
| Hard-stop | Không | Thực thi published rule | Resolve/override theo policy |
| Soạn hướng dẫn | Draft | Kiểm tra template | Phê duyệt/gửi |
| Chẩn đoán, điều trị, ký | Không | Không | Bác sĩ có thẩm quyền |

Guardrails bắt buộc:

- Permission-aware retrieval.
- JSON Schema validation.
- Citation và evidence span bắt buộc.
- Không online learning từ dữ liệu production.
- Prompt/model/policy versioning.
- Shadow/canary và rollback.
- Manual checklist fallback khi AI lỗi.
- No-PHI logs và audit mọi truy cập nhạy cảm.

---

## 8. Acceptance scenarios

### AC-01 — Thiếu bằng chứng khám tai

- Given encounter dùng Policy Pack đau tai.
- And note có assessment nhưng không có otoscopy result.
- When pre-close evaluation chạy.
- Then obligation khám tai là Missing.
- And finding chỉ rõ field cần bổ sung và guideline citation.
- And AI không tự suy ra kết quả khám.

### AC-02 — Evidence từ note chưa ký

- Given note Draft nói “đã kiểm tra dị ứng”.
- And structured allergy review chưa được xác nhận.
- When evaluation chạy.
- Then evidence được lưu với source span.
- And obligation là Unverified, không phải Satisfied.

### AC-03 — Rule mụn cần dữ liệu an toàn

- Given kế hoạch điều trị kích hoạt một obligation an toàn đã publish.
- And dữ liệu bắt buộc còn thiếu.
- When bác sĩ đóng encounter.
- Then hệ thống hiển thị Must resolve.
- And không tự điền dữ liệu hoặc đề xuất thuốc.

### AC-04 — Kết quả sàng lọc chưa có follow-up

- Given kết quả tầm soát đã được nhận và rule yêu cầu follow-up.
- When chưa có task hoặc appointment hợp lệ.
- Then finding là Missing.
- And task được tạo đúng owner/SLA.
- And quá hạn sẽ escalation một lần.

### AC-05 — Policy version không sửa lịch sử

- Given encounter A được đánh giá bằng Policy Pack v1.
- When v2 được publish.
- Then encounter mới dùng v2.
- And audit của A vẫn tái hiện được bằng v1.

### AC-06 — Retry idempotent

- Given cùng event được gửi ba lần.
- When ingest và evaluation hoàn tất.
- Then chỉ một timeline event logic, một finding hiện tại và một task tồn tại.
- And cả ba delivery được audit.

### AC-07 — AI không có nguồn

- Given model không tìm được source span.
- When structured output được validate.
- Then AI run có trạng thái Abstained.
- And obligation giữ Missing hoặc Pending theo rule.

---

## 9. Demo hackathon

Một engine, ba encounter JSON:

1. **Tai Mũi Họng:** thiếu kết quả khám tai → CareGuard tìm thấy lỗ hổng → nhân viên bổ sung evidence → Satisfied.
2. **Da liễu:** note Draft nhắc dữ liệu an toàn nhưng chưa xác nhận → Unverified → bác sĩ review.
3. **Phụ khoa:** kết quả sàng lọc đã có nhưng chưa follow-up → tự tạo task → handoff → escalation/audit.

Demo kết thúc ở dashboard:

- Findings theo specialty và severity.
- Tỷ lệ Satisfied trước/sau pre-close.
- Task đúng SLA/quá hạn.
- Override và false-positive feedback.
- Toàn bộ trace từ policy → evidence → rule → human decision.

---

## 10. KPI và pilot

| Nhóm | Mục tiêu pilot đề xuất |
| --- | --- |
| Documentation | Giảm encounter thiếu tài liệu bắt buộc so với baseline |
| Safety | Không bỏ sót case nguy cơ cao trong bộ dữ liệu đã clinical-review |
| Alert quality | Precision finding actionable ≥ 85%; false-positive hard-stop < 2% |
| Follow-up | ≥ 90% task có trạng thái cuối trong SLA |
| UX | Median ≤ 30 giây xử lý một finding; giới hạn interruptive alerts |
| Adoption | ≥ 70% user pilot dùng worklist trên encounter đủ điều kiện |
| Governance | 100% policy, override và AI finding có provenance |

Ngưỡng là mục tiêu pilot, không phải số liệu đã được kiểm chứng.

---

## 11. Ánh xạ tiêu chí chấm

| Tiêu chí | Bằng chứng |
| --- | --- |
| Kỹ thuật | State machine, schema chung, idempotency, evidence hierarchy và tests |
| AI-Native | Policy-grounded extraction, explanation, abstention và feedback loop offline |
| Business/Pilot | Không thay HIS, triển khai theo specialty, KPI và workflow rõ |
| UX | Một worklist, source-first, đúng owner và ít ngắt luồng |
| Safety | Human authority, deterministic hard-stop, citations, audit và rollback |
| Trình bày | Ba ca dùng chung engine, mỗi ca giải quyết một failure mode của đề bài |

---

## 12. Definition of Done

- Ba Policy Pack có nguồn, version và clinical owner.
- Ba mock encounter dùng cùng JSON contract và không chứa PHI thật.
- AC-01 đến AC-07 pass.
- Mọi finding có rule version và evidence/citation hoặc trạng thái abstain.
- Tenant/authorization, idempotency và no-PHI-log tests pass.
- Manual fallback, kill switch và reconciliation được diễn tập.
- Không có rule thuốc, chẩn đoán hoặc điều trị được publish nếu chưa clinical-review.
- Database và architecture specs khớp entity/state/interface của tài liệu này.

---

## 13. Nguồn baseline

- World Health Organization. *Primary ear and hearing care: training manual*. 2023.
- NICE. *NG198 Acne vulgaris: management*. Published 2021, updated 2026.
- Bộ Y tế Việt Nam. *Hướng dẫn dự phòng và kiểm soát ung thư cổ tử cung*.
- World Health Organization. *Guideline for screening and treatment of cervical pre-cancer lesions for cervical cancer prevention*. Second edition, 2021.
- World Health Organization. *Primary Care Checklist*. 2025.

Các nguồn trên là baseline thiết kế. Bản Policy Pack triển khai phải được clinical owner, compliance và cơ sở y tế xác nhận theo phiên bản pháp lý/chuyên môn đang áp dụng.
