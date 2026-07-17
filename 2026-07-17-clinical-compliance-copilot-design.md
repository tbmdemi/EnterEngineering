# Đặc tả hệ thống Clinical Compliance & Operations Copilot

> Tên làm việc: **CareGuard**  
> Phiên bản: Draft 1.0  
> Ngày: 17/07/2026  
> Thị trường giả định: phòng khám ngoại trú/nha khoa tại Việt Nam  
> Mục tiêu: phục vụ hackathon và làm baseline cho pilot  
> Trạng thái: sẵn sàng để xác nhận với đại diện lâm sàng, vận hành và pháp lý

## 1. Tóm tắt điều hành

CareGuard là lớp giám sát tuân thủ và điều phối công việc chạy bên cạnh HIS/EHR/PMS hiện có. Hệ thống quan sát các sự kiện của một lượt khám, đối chiếu chúng với protocol, quy định và chính sách nội bộ đã được phê duyệt, sau đó:

- Xác định nghĩa vụ nào đã hoàn thành, còn thiếu, sắp quá hạn hoặc không áp dụng.
- Liên kết mỗi kết luận với bằng chứng trong hồ sơ và điều khoản nguồn.
- Nhắc đúng vai trò vào thời điểm ít gây gián đoạn nhất.
- Chuyển thiếu sót thành task có người phụ trách, SLA và escalation.
- Theo dõi follow-up cho đến khi hoàn tất hoặc được đóng có lý do.
- Lưu audit trail cho toàn bộ phát hiện, quyết định, override và thay đổi policy.

CareGuard không chẩn đoán, không kê đơn, không tự ký hồ sơ và không thay thế HIS/EHR. Với MVP, AI chỉ đọc dữ liệu được cấp quyền, trích xuất bằng chứng từ văn bản phi cấu trúc và giải thích cảnh báo. Việc xác định hard-stop, trạng thái hoàn tất và hành động ghi ngược vào hệ thống nguồn do rule, workflow và người có thẩm quyền kiểm soát.

### 1.1 Giá trị khác biệt

Sản phẩm không dừng ở một checklist tĩnh. Mỗi encounter có một **Obligation Graph** động: tập nghĩa vụ thay đổi theo loại điều trị, giai đoạn, đặc điểm người bệnh, dữ liệu mới phát sinh và policy version. Mỗi nghĩa vụ có bốn thành phần:

1. Điều kiện áp dụng.
2. Bằng chứng chấp nhận được.
3. Người chịu trách nhiệm và hạn xử lý.
4. Hành động khi thiếu, xung đột hoặc quá hạn.

Kết quả là một vòng lặp khép kín: **Detect → Explain → Assign → Resolve → Verify → Audit**.

## 2. Tổng hợp điểm tốt từ các hệ thống tham chiếu

| Hệ thống | Điểm tốt nên kế thừa | Cách áp dụng vào CareGuard |
| --- | --- | --- |
| Epic/MyChart | Hành trình liên tục trước–trong–sau khám; worklist theo vai trò; longitudinal record; patient-facing follow-up; FHIR/HL7; audit và consent | Dùng encounter timeline thống nhất, work queue cho từng bộ phận, task sau khám và integration-first thay vì tạo kho hồ sơ độc lập |
| Abridge | Linked Evidence; consent rõ ràng; output luôn là draft; provenance/versioning; quality gate; human sign-off; Vietnamese-first và clinical error taxonomy | Mọi phát hiện có evidence + policy citation; AI không tự quyết; version mọi policy/model/prompt; có abstain và review cho trường hợp không chắc chắn |
| Ambience Healthcare | Thiết kế Pre-visit/In-visit/Post-visit; chart awareness; tích hợp sâu vào EHR; hỗ trợ tại điểm chăm sóc; đo ROI vận hành và compliance | Tổ chức UX theo ba giai đoạn, chỉ hiển thị thông tin có liên quan đến encounter hiện tại, nhúng cảnh báo vào màn hình đang dùng và đo tác động định lượng |
| Suki | Clinical Fact Graph; structured output; intent detection; partial/incomplete state; field-level review; idempotent EHR write-back; schema + rule validation | Chuẩn hóa dữ kiện và obligation thành schema; không biến một câu nhắc thành hành động; để trống khi thiếu; task/write-back phải idempotent và có reconciliation |

### 2.1 Những phần chủ động không đưa vào MVP

- Patient portal, billing, telehealth và scheduling engine đầy đủ của Epic/MyChart.
- Ambient recording, ASR và clinical note generation toàn diện của Abridge/Suki.
- Coding/HCC/revenue-cycle theo thị trường Hoa Kỳ của Ambience.
- Order staging thuốc, xét nghiệm và thủ thuật.
- Kiến trúc microservice, Kafka, Kubernetes hoặc vector database riêng khi một ứng dụng modular và PostgreSQL đã đủ cho pilot.

Các phần này chỉ nên bổ sung khi pilot chứng minh chúng là nút thắt thực tế. MVP tập trung đúng bốn lỗi của đề bài: hồ sơ thiếu, bước lâm sàng bị bỏ qua, follow-up thất lạc và bàn giao kém.

## 3. Mục tiêu và phạm vi

### 3.1 Mục tiêu sản phẩm

- Giảm thiếu sót hồ sơ trước khi encounter được đóng.
- Phát hiện bước lâm sàng bắt buộc chưa có bằng chứng mà không gây alert fatigue.
- Bảo đảm mọi follow-up có owner, due date và trạng thái cuối.
- Cung cấp một hàng đợi bàn giao thống nhất giữa lễ tân, trợ lý/điều dưỡng, bác sĩ và QA.
- Cho phép auditor trả lời: quy tắc nào áp dụng, dữ liệu nào được dùng, ai đã quyết định và kết quả cuối là gì.
- Chứng minh ROI trong một pilot nhỏ bằng số liệu trước–sau.

### 3.2 Phạm vi MVP

- Một tenant, một cơ sở, khám ngoại trú hoặc nha khoa.
- Hai pathway điều trị được cơ sở chọn cho pilot.
- Nhận encounter, appointment, patient context và tài liệu từ HIS/EHR/PMS qua FHIR/REST, webhook hoặc file mock trong demo.
- Policy Pack có version cho protocol, compliance và operational policy.
- Encounter timeline và obligation state machine.
- Kiểm tra completeness của consent, treatment plan, progress note, medication instruction và tài liệu cấu hình khác.
- Kiểm tra bước pre-treatment: medical history, allergy, vital signs, imaging và infection-control attestation theo pathway.
- Pre-close compliance review.
- Follow-up plan, patient instruction, recall task và complication check.
- Handoff task, owner, SLA, escalation và reconciliation.
- Evidence-linked alert, override có lý do, audit log và dashboard pilot.

### 3.3 Ngoài phạm vi MVP

- Thay thế HIS/EHR/PMS hoặc trở thành system of record.
- Chẩn đoán, lập treatment plan hoặc clinical decision support tự trị.
- Tự đặt lịch, tự gửi đơn thuốc, tự chỉ định hoặc tự ký hồ sơ.
- Xác nhận một thủ thuật vật lý chỉ dựa vào AI; cần dữ liệu thiết bị, checkbox có trách nhiệm hoặc attestation.
- Gửi tin nhắn y tế cho bệnh nhân mà chưa có template/policy được phê duyệt.
- Thu âm ambient liên tục.
- Hỗ trợ mọi chuyên khoa ngay trong pilot.

## 4. Actors và phân quyền

| Actor | Nhu cầu chính | Quyền MVP |
| --- | --- | --- |
| Lễ tân | Hồ sơ trước khám đủ, lịch và chuyển giao rõ | Xem/sửa dữ liệu hành chính; xử lý task check-in và follow-up scheduling |
| Trợ lý nha khoa/điều dưỡng | Chuẩn bị người bệnh và phòng điều trị đúng protocol | Ghi nhận vital, checklist, sterilization attestation và handoff |
| Bác sĩ/nha sĩ | Nhìn nhanh rủi ro còn lại, hoàn thiện note và quyết định override | Review evidence, resolve/override obligation, ký/xác nhận trong hệ thống nguồn |
| QA/Compliance | Quản lý policy, điều tra thiếu sót và theo dõi xu hướng | Publish Policy Pack, review override, audit và báo cáo |
| Clinic Manager | Giảm delay, no-show follow-up và rework | Dashboard vận hành, SLA, assignment và escalation |
| System/Integration Admin | Kết nối và vận hành an toàn | Mapping, connector, identity, health và reconciliation; không mặc định xem PHI |
| Bệnh nhân | Nhận hướng dẫn và follow-up đúng lúc | Không cần ứng dụng riêng trong MVP; nhận qua kênh hiện có sau approval |

Nguyên tắc: deny-by-default, least privilege, phân quyền server-side theo tenant/facility/department/encounter và audit mọi lần đọc hoặc thay đổi dữ liệu nhạy cảm.

## 5. Trải nghiệm người dùng AI-native

### 5.1 Nguyên tắc UX

- **Zero new inbox:** task xuất hiện trong worklist theo vai trò hoặc sidebar nhúng, không tạo thêm một ứng dụng phải canh liên tục.
- **Progressive disclosure:** mặc định chỉ hiển thị số việc cần xử lý; mở rộng mới thấy lý do, evidence và policy.
- **One alert, one owner:** mỗi thiếu sót có một người xử lý hiện tại, deadline và action rõ ràng.
- **Batch low-risk, interrupt high-risk:** nhắc việc thường được gom ở checkpoint; chỉ hard-stop được phép ngắt luồng.
- **Source before suggestion:** hiển thị bằng chứng và điều khoản trước nút Resolve/Override.
- **No fake certainty:** phân biệt Missing, Conflicting, Unverified và Not Applicable.

### 5.2 Luồng Pre-visit

1. Encounter được tạo/đồng bộ.
2. Hệ thống chọn Policy Pack theo facility, specialty, visit type và planned procedure.
3. Obligation Graph được sinh từ các rule đã phê duyệt.
4. Evidence engine đọc trường có cấu trúc và tài liệu được phép.
5. Worklist hiển thị “Ready”, “Needs attention” hoặc “Blocked”, kèm các việc đúng vai trò.
6. Lễ tân/trợ lý xử lý consent, history, allergy, vital hoặc imaging còn thiếu.
7. Bác sĩ thấy bản readiness brief ngắn trước khi bắt đầu.

### 5.3 Luồng In-visit

1. Timeline nhận event mới từ HIS/EHR/PMS hoặc thao tác của nhân viên.
2. Rule engine đánh giá lại chỉ các obligation bị ảnh hưởng.
3. Không tạo popup cho việc có thể xử lý tại pre-close checkpoint.
4. Nếu phát hiện hard-stop đã được Medical Director phê duyệt, hệ thống hiển thị cảnh báo ngắn với evidence, policy citation và action.
5. Người dùng resolve, ghi attestation hoặc override theo quyền.

### 5.4 Luồng Post-visit / Pre-close

1. Khi người dùng chuẩn bị đóng encounter, CareGuard chạy pre-close check.
2. Các nghĩa vụ được nhóm thành: Must resolve, Needs review và Follow-up.
3. Người dùng có thể mở đúng field/tài liệu trong hệ thống nguồn, không nhập lại dữ liệu trong CareGuard nếu connector hỗ trợ deep link.
4. Sau khi dữ liệu nguồn thay đổi, hệ thống re-check và tự đóng task khi evidence hợp lệ xuất hiện.
5. Override bắt buộc có reason code; free text chỉ dùng khi “Other”.
6. Encounter được đánh dấu Compliant, Compliant with exception hoặc Closed with unresolved risk.

### 5.5 Luồng Follow-up và handoff

1. Pathway sinh các obligation sau khám: instruction, recall, recovery check, result review hoặc complication monitoring.
2. Mỗi obligation trở thành task với owner, due date, kênh thực hiện và escalation path.
3. Handoff yêu cầu người nhận acknowledge; chuyển ca không làm mất owner.
4. Event từ scheduling/messaging/HIS tự cập nhật trạng thái khi có thể.
5. Quá SLA tạo escalation theo policy; AI không tự gửi nội dung y tế chưa được phê duyệt.
6. Task chỉ đóng khi có evidence hoàn tất, explicit cancellation hoặc exception có lý do.

## 6. Mô hình policy và bằng chứng

### 6.1 Policy Pack

Mỗi Policy Pack là artifact được version và phê duyệt, gồm:

- Nguồn: protocol lâm sàng, quy định pháp lý hoặc policy nội bộ.
- Phạm vi: facility, specialty, procedure, encounter type và effective date.
- Obligation: điều phải làm hoặc phải có.
- Applicability rule: điều kiện áp dụng.
- Evidence rule: trường, tài liệu hoặc event được chấp nhận.
- Severity: Info, Advisory, Required hoặc Hard-stop.
- Owner role, due offset, SLA và escalation.
- Override policy và reason codes.
- Source citation: document ID, version, section/page.

AI có thể đề xuất bản nháp obligation từ tài liệu policy, nhưng QA/Compliance và clinical owner phải review/publish trước khi rule có hiệu lực.

### 6.2 Trạng thái obligation

`PENDING → SATISFIED | MISSING | UNVERIFIED | CONFLICTING | NOT_APPLICABLE | OVERRIDDEN | EXPIRED`

- `SATISFIED`: có evidence đáp ứng rule.
- `MISSING`: rule áp dụng nhưng chưa có evidence.
- `UNVERIFIED`: AI tìm thấy dấu hiệu trong nguồn chưa đủ thẩm quyền, cần người dùng hoặc system of record xác nhận.
- `CONFLICTING`: nhiều nguồn không nhất quán.
- `NOT_APPLICABLE`: điều kiện áp dụng không còn đúng hoặc người có quyền xác nhận không áp dụng.
- `OVERRIDDEN`: người có quyền chấp nhận ngoại lệ và ghi lý do.
- `EXPIRED`: đã quá hạn mà chưa có trạng thái cuối hợp lệ.

Mọi transition lưu actor, timestamp, rule version, evidence snapshot/hash và reason.

### 6.3 Evidence hierarchy

1. Dữ liệu có cấu trúc và chữ ký/xác nhận từ system of record.
2. Event từ hệ thống tích hợp có ACK và provenance.
3. Tài liệu/note đã ký.
4. Tài liệu/note draft hoặc dữ liệu do AI trích xuất — chỉ đủ cho `UNVERIFIED`, trừ khi policy cho phép.
5. Manual attestation của vai trò có thẩm quyền.

AI confidence không thay thế evidence. Không có evidence thì hệ thống để thiếu hoặc yêu cầu xác nhận, không tự điền.

## 7. Yêu cầu chức năng

### 7.1 Policy và governance

| ID | Yêu cầu | Ưu tiên |
| --- | --- | --- |
| FR-POL-001 | Admin phải tạo Policy Pack ở trạng thái Draft và chỉ bản Published mới chạy production. | Must |
| FR-POL-002 | Publish/retire policy cần clinical/compliance approval và lưu version, effective date, owner. | Must |
| FR-POL-003 | Mỗi obligation phải có applicability, evidence rule, severity, owner và citation. | Must |
| FR-POL-004 | Thay đổi policy không được viết lại kết quả lịch sử; encounter giữ policy version đã áp dụng. | Must |
| FR-POL-005 | Có thể chạy policy mới ở shadow mode để so sánh trước khi kích hoạt. | Should |
| FR-POL-006 | Hard-stop chỉ được publish qua phê duyệt bốn mắt và có kill switch. | Must |

### 7.2 Integration và encounter timeline

| ID | Yêu cầu | Ưu tiên |
| --- | --- | --- |
| FR-INT-001 | Nhận patient, appointment, encounter, practitioner, document, observation và task context qua adapter. | Must |
| FR-INT-002 | Một event phải có tenant, encounter, event type, occurred time, source, version và correlation ID. | Must |
| FR-INT-003 | Mọi ingest/write-back có idempotency key; retry không tạo task hoặc tài liệu trùng. | Must |
| FR-INT-004 | Không tự nhận là synced/completed trước khi nhận ACK hoặc reconciliation thành công. | Must |
| FR-INT-005 | Connector lỗi phải queue/retry và chuyển manual reconciliation sau ngưỡng cấu hình. | Must |
| FR-INT-006 | Deep link về field/tài liệu nguồn nên được dùng thay cho nhập lại dữ liệu. | Should |
| FR-INT-007 | MVP hỗ trợ một connector thật hoặc adapter mock có cùng contract. | Must |

### 7.3 Compliance evaluation

| ID | Yêu cầu | Ưu tiên |
| --- | --- | --- |
| FR-CMP-001 | Tạo Obligation Graph khi encounter được mở và cập nhật gia tăng khi có event mới. | Must |
| FR-CMP-002 | Rule engine xác định applicability và trạng thái bằng logic deterministic đã version. | Must |
| FR-CMP-003 | AI chỉ trích xuất fact/evidence từ dữ liệu phi cấu trúc và phải trả source span. | Must |
| FR-CMP-004 | Không được đánh dấu SATISFIED nếu evidence thấp hơn mức policy yêu cầu. | Must |
| FR-CMP-005 | Mâu thuẫn giữa nguồn phải thành CONFLICTING, không tự chọn một nguồn đúng. | Must |
| FR-CMP-006 | Pre-close check phải trả kết quả theo severity, owner và action. | Must |
| FR-CMP-007 | Re-check tự đóng issue khi evidence hợp lệ xuất hiện nhưng vẫn giữ lịch sử. | Must |
| FR-CMP-008 | Người dùng có quyền có thể override với reason code; hard-stop có policy override riêng. | Must |

### 7.4 Documentation completeness và clinical steps

| ID | Yêu cầu | Ưu tiên |
| --- | --- | --- |
| FR-DOC-001 | Kiểm tra presence, status, signature và required fields của tài liệu cấu hình. | Must |
| FR-DOC-002 | Phân biệt tài liệu Draft, Signed, Superseded và Missing. | Must |
| FR-DOC-003 | Hiển thị chính xác field/section còn thiếu, không chỉ báo “hồ sơ chưa đủ”. | Must |
| FR-CLN-001 | Theo dõi medical history, allergy, vital, imaging và infection-control obligation theo pathway. | Must |
| FR-CLN-002 | Không khẳng định một hành động vật lý đã diễn ra chỉ từ note do AI tạo. | Must |
| FR-CLN-003 | Bước không áp dụng cần actor có thẩm quyền và reason. | Must |
| FR-CLN-004 | Bước nguy cơ cao chưa hoàn tất có thể chặn close/start theo hard-stop policy. | Must |

### 7.5 Task, handoff và follow-up

| ID | Yêu cầu | Ưu tiên |
| --- | --- | --- |
| FR-TSK-001 | Mỗi issue có tối đa một owner hiện tại, due date, SLA và status. | Must |
| FR-TSK-002 | Assignment theo vai trò/ca trực; người nhận phải acknowledge handoff. | Must |
| FR-TSK-003 | Escalation không tạo task trùng và giữ toàn bộ chain of custody. | Must |
| FR-FUP-001 | Pathway tạo task post-treatment gồm instruction, recall và monitoring được cấu hình. | Must |
| FR-FUP-002 | Task follow-up chỉ đóng bằng evidence, cancellation hoặc exception có lý do. | Must |
| FR-FUP-003 | Hệ thống nhận event từ scheduling/messaging để tự cập nhật trạng thái. | Should |
| FR-FUP-004 | Nội dung gửi bệnh nhân phải dùng template được phê duyệt hoặc qua staff review. | Must |

### 7.6 AI, explanation và human review

| ID | Yêu cầu | Ưu tiên |
| --- | --- | --- |
| FR-AI-001 | Mỗi AI output lưu model, prompt, retrieval corpus/policy version và timestamp. | Must |
| FR-AI-002 | Structured output phải qua JSON Schema và rule validation. | Must |
| FR-AI-003 | Mỗi claim phải có evidence span và policy citation; thiếu nguồn thì abstain. | Must |
| FR-AI-004 | AI không được trực tiếp gọi write API lâm sàng hoặc thay đổi obligation state cuối. | Must |
| FR-AI-005 | Cảnh báo hiển thị vì sao áp dụng, thiếu gì, nguồn nào và hành động đề xuất. | Must |
| FR-AI-006 | Feedback Accept/Incorrect/Not relevant được liên kết với model/rule version để đánh giá offline. | Should |
| FR-AI-007 | Prompt injection trong note/policy được coi là dữ liệu, không phải instruction; tool access theo allowlist. | Must |

### 7.7 Audit, privacy và administration

| ID | Yêu cầu | Ưu tiên |
| --- | --- | --- |
| FR-AUD-001 | Audit append-only cho view, evaluate, assign, resolve, override, policy publish và integration action. | Must |
| FR-AUD-002 | Auditor tìm theo encounter, patient reference, user, obligation, policy version và thời gian. | Must |
| FR-AUD-003 | Không ghi PHI, note body hoặc model prompt thô vào application log. | Must |
| FR-ADM-001 | Admin cấu hình role mapping, SLA, severity, notification channel và connector. | Must |
| FR-ADM-002 | Dashboard hiển thị policy/rule/model/connector health và kill switch. | Must |
| FR-ADM-003 | Retention và quyền dữ liệu phải cấu hình theo artifact, không dùng một TTL chung. | Must |

## 8. Kiến trúc AI-native tối thiểu

```text
HIS / EHR / PMS / Scheduling / Messaging
                 │
          FHIR / REST / Webhook
                 ▼
        Integration Adapter Layer
                 ▼
       Normalized Encounter Timeline
                 │
       ┌─────────┴──────────┐
       ▼                    ▼
Deterministic Rules    Evidence Extractor
& Obligation Graph     (LLM/NLP + citations)
       │                    │
       └─────────┬──────────┘
                 ▼
      Compliance Evaluation Service
        status + reason + evidence
                 ▼
     Task / Handoff / Follow-up Engine
                 ▼
 Embedded Worklist + Pre-close Review
                 ▼
 Human decision → Adapter → Source system
                 │
                 ▼
        Audit + Pilot Analytics
```

### 8.1 Runtime pipeline

1. Xác thực user, tenant, purpose và encounter scope.
2. Chọn Policy Pack đã Published theo context.
3. Lấy dữ liệu tối thiểu cần thiết từ timeline và source system.
4. Chạy rule deterministic cho structured evidence.
5. Chỉ khi cần, AI trích xuất fact từ note/document và trả exact source span.
6. Validate schema, permission, citation và contradiction.
7. Rule engine quyết định obligation state; AI không quyết định hard-stop.
8. Tạo/cập nhật task idempotently.
9. Hiển thị explanation ngắn và cho human resolve/override.
10. Ghi audit và metric không chứa PHI.

### 8.2 Kiến trúc triển khai MVP

- Một web app responsive hoặc sidebar nhúng.
- Một backend modular monolith gồm integration, policy, evaluation, task và audit modules.
- PostgreSQL cho transaction, JSON policy, task, audit metadata và vector extension nếu thật sự cần semantic retrieval.
- Object storage cho policy document/tài liệu được phép lưu.
- Job table/worker cho ingest, evaluation và retry; chưa cần Kafka.
- Một model gateway để kiểm soát provider, redaction, structured output, timeout và audit metadata.
- FHIR/REST adapter đầu tiên; CSV/JSON fixture cho demo offline.

## 9. Mô hình dữ liệu cốt lõi

| Entity | Thuộc tính chính |
| --- | --- |
| Tenant/Facility | policy, timezone, role mapping, retention, connector |
| PatientReference | pseudonymous local ID, source reference; không mirror toàn bộ hồ sơ |
| Encounter | source ID, patient, practitioner, visit/procedure type, status |
| TimelineEvent | event type, source, occurredAt, payload reference/hash, correlation ID |
| PolicyDocument | title, issuer, version, effective dates, storage reference |
| PolicyPack | scope, version, status, approvers, effective dates |
| ObligationDefinition | applicability, evidence rule, severity, owner, SLA, citation |
| ObligationInstance | encounter, definition version, state, dueAt, current owner |
| Evidence | source type, resource/document/field, source span, signature/status, observedAt |
| ComplianceFinding | state, reason, evidence refs, model/rule versions |
| Task/Handoff | owner, status, SLA, acknowledgment, escalation chain |
| HumanDecision | resolve/override/not-applicable, actor, reason, timestamp |
| IntegrationJob | artifact, destination, idempotency key, ACK, retry state |
| AuditEvent | actor, purpose, action, object, result, timestamp, correlation ID |
| FeedbackMetric | correctness/relevance, cohort, rule/model version; không lưu PHI thô |

## 10. Yêu cầu phi chức năng

| ID | Yêu cầu đo lường được |
| --- | --- |
| NFR-PERF-001 | P95 ingest event đến cập nhật obligation ≤ 5 giây với structured data. |
| NFR-PERF-002 | P95 pre-close evaluation ≤ 3 giây khi tài liệu đã được index. |
| NFR-PERF-003 | P95 AI evidence extraction ≤ 10 giây; timeout phải fallback sang Unverified, không block vô hạn. |
| NFR-REL-001 | Availability mục tiêu pilot ≥ 99,5%; manual checklist fallback luôn khả dụng. |
| NFR-REL-002 | Retry/replay không tạo finding, task hoặc write-back trùng. |
| NFR-REL-003 | RPO ≤ 15 phút, RTO ≤ 4 giờ cho pilot; restore phải được diễn tập trước limited production. |
| NFR-SEC-001 | TLS khi truyền, mã hóa at-rest qua KMS/managed key và secret không nằm trong source/log. |
| NFR-SEC-002 | Mọi authorization được enforce backend; có tenant-isolation test. |
| NFR-SEC-003 | Model/provider không được dùng PHI cho training mặc định; data flow và retention cần hợp đồng/phê duyệt. |
| NFR-PRV-001 | Data minimization, purpose limitation, access audit và retention theo artifact. |
| NFR-PRV-002 | Quy định pháp lý cụ thể phải được legal/DPO của cơ sở mapping và phê duyệt trước pilot production. |
| NFR-AI-001 | 100% cảnh báo lâm sàng có policy citation; 100% claim từ unstructured data có source span hoặc abstain. |
| NFR-AI-002 | Báo cáo chất lượng tách theo pathway, severity, role, document type và model/rule version. |
| NFR-UX-001 | Từ worklist đến evidence/action không quá 2 lần click. |
| NFR-UX-002 | Không dùng màu làm tín hiệu duy nhất; keyboard navigation và screen-reader label cho action cốt lõi. |
| NFR-UX-003 | Mỗi encounter có tối đa một summary card mặc định; issue chi tiết được nhóm theo checkpoint. |

## 11. Safety, grounding và độ tin cậy

### 11.1 Phân quyền quyết định

| Quyết định | AI | Rule engine | Con người |
| --- | --- | --- | --- |
| Trích xuất fact từ note | Đề xuất + source span | Validate schema | Sửa/xác nhận khi cần |
| Applicability của policy | Có thể hỗ trợ phân loại | Quyết định theo published rule | Override theo quyền |
| Obligation SATISFIED | Không | Quyết định theo evidence threshold | Attest/override theo policy |
| Hard-stop | Không | Thực thi rule được phê duyệt | Resolve hoặc override nếu được phép |
| Gửi tin bệnh nhân | Soạn draft | Kiểm tra template/policy | Phê duyệt hoặc gửi qua workflow nguồn |
| Ký hồ sơ/đặt order | Không | Không | Chỉ người có thẩm quyền trong HIS/EHR |

### 11.2 Guardrails bắt buộc

- Retrieval permission-aware: index không được làm mất ranh giới quyền truy cập.
- Policy và evidence phải được pin version cho từng evaluation.
- Prompt/model update chạy offline evaluation và shadow/canary trước rollout.
- Kill switch theo model, policy pack và tenant.
- Không online learning trực tiếp từ feedback production.
- Có taxonomy: unsupported evidence, omission, contradiction, wrong patient, wrong policy, stale context, duplicate task và missed escalation.
- Sự cố có thể truy ngược toàn bộ encounter bị ảnh hưởng theo rule/model version.
- Khi AI hoặc integration lỗi, workflow trở về checklist/manual review; chăm sóc không bị chặn bởi model.

## 12. Acceptance criteria trọng yếu

### AC-01 — Consent còn thiếu trước điều trị

**Given** pathway yêu cầu signed consent và encounter chỉ có consent Draft  
**When** pre-treatment check chạy  
**Then** obligation ở trạng thái Missing, severity theo policy, hiển thị trạng thái Draft làm evidence không đủ và deep link đến tài liệu nguồn; hệ thống không tự đánh dấu đã ký.

### AC-02 — Không tạo cảnh báo sai khi bước không áp dụng

**Given** imaging chỉ bắt buộc cho một nhóm procedure và encounter thuộc nhóm khác  
**When** Obligation Graph được tạo  
**Then** imaging obligation là Not Applicable và không tạo task/cảnh báo.

### AC-03 — Note nói đã kiểm tra dị ứng nhưng EHR trống

**Given** note draft chứa “đã kiểm tra dị ứng” nhưng structured allergy review chưa được xác nhận  
**When** evaluation chạy  
**Then** AI trả source span nhưng obligation là Unverified/Missing theo evidence hierarchy; bác sĩ có thể xác nhận hoặc cập nhật EHR.

### AC-04 — Follow-up không bị thất lạc qua chuyển ca

**Given** task recovery check đến hạn trong ca sau  
**When** owner hết ca  
**Then** task được assign theo on-call mapping, người nhận phải acknowledge, SLA giữ nguyên và escalation không tạo task trùng.

### AC-05 — Policy thay đổi không sửa lịch sử

**Given** encounter A được đánh giá bằng Policy Pack v1  
**When** v2 được publish  
**Then** audit của A vẫn tái hiện được bằng v1; encounter mới dùng v2; v2 có thể shadow-evaluate A nhưng không viết lại quyết định cũ.

### AC-06 — AI không có bằng chứng

**Given** policy yêu cầu post-care instruction và không có document/event phù hợp  
**When** model không tìm thấy source  
**Then** output phải abstain, obligation là Missing và không sinh nội dung giả để đánh dấu complete.

### AC-07 — Connector retry idempotent

**Given** cùng event `EncounterClosed` được gửi ba lần  
**When** hệ thống xử lý retry  
**Then** chỉ một pre-close evaluation cuối và một bộ task tồn tại; cả ba delivery được audit.

### AC-08 — Override hard-stop

**Given** hard-stop cho medical history chưa hoàn tất  
**When** user không có quyền override cố đóng encounter  
**Then** action bị chặn. Khi Medical Director override theo policy, hệ thống yêu cầu reason, re-authentication và tạo review item cho Compliance.

## 13. KPI và pilot

### 13.1 North Star và guardrails

**North Star:** tỷ lệ encounter đủ điều kiện được đóng với toàn bộ obligation Required có evidence hoặc exception hợp lệ, không tăng thời gian thao tác trung vị.

| Nhóm | KPI pilot đề xuất |
| --- | --- |
| Documentation | Giảm ≥ 30% encounter thiếu tài liệu bắt buộc so với baseline |
| Clinical steps | Recall ≥ 95% trên bộ case đã clinical-review; không có missed high-risk case trong bộ pilot đã gắn nhãn |
| Alert quality | Precision cảnh báo actionable ≥ 85%; false-positive hard-stop < 2% |
| Follow-up | ≥ 90% task follow-up có trạng thái cuối trong SLA; giảm ≥ 25% task quá hạn |
| Coordination | ≥ 90% handoff được acknowledge; giảm ≥ 20% thời gian chờ do thiếu thông tin |
| UX | Median ≤ 30 giây để xử lý một issue; ≤ 2 interruptive alerts/encounter ở P95 |
| Adoption | ≥ 70% người dùng pilot dùng worklist trong ≥ 80% ca đủ điều kiện |
| Safety | 0 auto-sign/order/diagnosis; 0 cross-tenant access; 100% override có actor/reason/audit |
| Economics | Đo giờ rework tránh được, chi phí/encounter và thời gian QA; chưa cam kết doanh thu khi chưa có baseline |

Các ngưỡng trên là mục tiêu pilot, không phải số liệu đã kiểm chứng.

### 13.2 Lộ trình pilot 6 tuần

| Giai đoạn | Thời lượng | Phạm vi | Gate |
| --- | --- | --- | --- |
| Baseline & policy mapping | Tuần 1 | Chọn 2 pathway, đo lỗi hiện tại, chuẩn hóa 15–25 obligation | Clinical owner ký Policy Pack v1 |
| Offline evaluation | Tuần 2 | 50–100 encounter đã khử định danh/synthetic | Citation, rule và tenant tests pass |
| Shadow mode | Tuần 3 | Chạy thật nhưng không cảnh báo staff | Precision/recall và alert volume đạt ngưỡng |
| Supervised pilot | Tuần 4–5 | 5–10 users, một cơ sở, daily QA | Không Sev-1; override và false alert trong giới hạn |
| Readout & scale decision | Tuần 6 | So sánh trước–sau, phỏng vấn user, tính ROI | Go, revise hoặc stop theo KPI đã chốt |

### 13.3 Demo hackathon 5 phút

1. Chọn encounter có consent thiếu, allergy chưa xác nhận và chưa có follow-up.
2. CareGuard tạo readiness brief từ Policy Pack và nguồn EHR.
3. Mở một cảnh báo để thấy policy citation + evidence + deep link.
4. Cập nhật dữ liệu nguồn; issue tự chuyển sang Satisfied.
5. Đóng encounter; hệ thống sinh follow-up task và handoff có SLA.
6. Mở audit view để tái hiện rule/model/evidence/human decision.
7. Dashboard hiển thị prevented issues, thời gian xử lý và alert precision.

## 14. Ánh xạ với tiêu chí chấm

| Tiêu chí | Bằng chứng trong giải pháp |
| --- | --- |
| Chất lượng triển khai kỹ thuật — 20 | Event contract, obligation state machine, idempotency, evidence hierarchy, acceptance tests và fallback |
| AI-Native & đổi mới — 20 | Obligation Graph động, policy-to-rule draft, evidence extraction, explanation và closed-loop learning offline |
| Kinh doanh & pilot — 20 | Wedge rõ cho phòng khám, pilot 6 tuần, KPI trước–sau và không yêu cầu thay HIS/EHR |
| UX AI-Native — 15 | Embedded worklist, progressive disclosure, source-first, checkpoint thay vì popup liên tục |
| Safety/Grounding — 15 | Published policy, citations, evidence span, deterministic hard-stop, human override và audit/versioning |
| Trình bày — 10 | Demo một encounter end-to-end với Before → Detect → Resolve → Follow-up → Audit → KPI |

## 15. Rủi ro và biện pháp giảm thiểu

| Rủi ro | Biện pháp |
| --- | --- |
| Alert fatigue | Chỉ cảnh báo tại checkpoint, severity budget, đo alerts/encounter, shadow tuning |
| Rule/policy sai | Approval workflow, versioning, shadow mode, clinical owner, kill switch |
| AI hallucination | Source span bắt buộc, schema validation, abstain, rule quyết định trạng thái |
| Sai bệnh nhân/encounter | Context lock, hai định danh khi thao tác nhạy cảm, correlation và quarantine |
| EHR dữ liệu cũ/thiếu | Hiển thị freshness, conflict state, manual attestation và reconciliation |
| Staff né quy trình bằng override | Reason code, quyền hạn, re-auth cho hard-stop, dashboard và review định kỳ |
| Integration phân mảnh | Một contract chuẩn, adapter mỏng, deep link/manual fallback trong pilot |
| Dữ liệu nhạy cảm bị lộ | Minimum necessary, pseudonymous IDs, no-PHI logs, tenant isolation và access audit |
| Scope phình thành EHR mới | Giữ system-of-record bên ngoài; chỉ build detect/task/audit loop |
| Không chứng minh ROI | Thu baseline trước pilot và định nghĩa metric trước khi bật cảnh báo |

## 16. Definition of Done cho MVP

- Hai Policy Pack/pathway được clinical và compliance owner phê duyệt.
- Không còn nội dung chưa xác định trong rule, owner, evidence threshold hoặc acceptance criteria thuộc phạm vi pilot.
- Các AC-01 đến AC-08 pass bằng dữ liệu synthetic/de-identified.
- Tenant isolation, authorization, no-PHI-log và idempotency tests pass.
- Mọi AI finding có source span + policy citation hoặc abstain.
- Manual fallback, connector reconciliation và kill switch được diễn tập.
- Dashboard tính được metric từ định nghĩa cố định, không dùng số demo hard-code.
- Training ngắn cho từng vai trò và runbook sự cố sẵn sàng.
- Legal/DPO của cơ sở xác nhận data flow, retention, consent và vendor trước production pilot.

## 17. Quyết định cần chốt trước khi build

1. Loại phòng khám và hai pathway pilot cụ thể.
2. HIS/EHR/PMS đầu tiên và dữ liệu/event thực sự truy cập được.
3. Clinical owner, Compliance owner và ai được override từng severity.
4. 15–25 obligation đầu tiên cùng evidence threshold.
5. Kênh follow-up hiện có: SMS, Zalo, app, cuộc gọi hay scheduling task.
6. Baseline hiện tại cho hồ sơ thiếu, follow-up quá hạn và thời gian rework.
7. Data retention, deployment region và điều khoản của model provider sau thẩm định pháp lý.

## 18. Kết luận

CareGuard nên được định vị là **compliance control plane cho hành trình điều trị**, không phải một AI scribe hay EHR mới. Bốn năng lực không được cắt khỏi MVP là: Policy Pack được phê duyệt, evidence-linked evaluation, task/handoff khép kín và human/audit control. Phần còn lại chỉ được thêm khi pilot cho thấy nó cải thiện KPI hoặc loại bỏ một nút thắt triển khai cụ thể.
