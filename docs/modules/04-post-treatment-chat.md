# Module 04 — Post-treatment & Patient Chat

## Mục tiêu và pain point

Đảm bảo hướng dẫn/follow-up không bị quên và bệnh nhân chỉ nhận thông tin đã phát hành, có nguồn và escalation an toàn.

## Phạm vi / không làm

Care instructions, recall, complication-monitoring task, release summary và chatbot ba intent. Không chẩn đoán, kê đơn, general medical bot, realtime staff chat hoặc lưu raw chat.

Branch này ưu tiên thay đổi dễ merge. Các phần journey mới chỉ là UX chạy trong bộ nhớ của React; branch không thêm bảng, cột hoặc API persistence cho acknowledgement, check-in, callback, feedback hay release versioning.

## Đường dẫn sở hữu

`backend/app/features/post_treatment_chat/`, `frontend/src/features/post-treatment-chat/`, `tests/post_treatment_chat/`, `db/init/50_post_treatment_chat.sql`.

Không sửa core schema/enums, bootstrap/router registry, navigation, Compose hoặc dependency manifests. Integrator chịu trách nhiệm wire router và frontend route.

## Contract hiện tại

- React export bắt buộc: `export const route = { path, label, Component }`; integrator import vào `frontend/src/routes.js`.
- Evidence: `POST_CARE_INSTRUCTIONS`, `POST_RECALL`, `POST_COMPLICATION_MONITORING`.
- `POST /api/v1/encounters/{id}/release` với payload legacy `{care_instructions, recall_at, monitor_until}` → released summary và follow-up task.
- `POST /api/v1/portal/chat` với body `{message}` → `{intent, answer, citations, escalation, record?}`.
- Intent: `MY_RECORD`, `CLINIC_FAQ`, `SYMPTOM_INFO`; nguồn chỉ released record, seeded FAQ hoặc approved dental content.
- `GET /api/v1/post-treatment/templates` (`DENTIST`) → catalog tĩnh gồm năm loại điều trị, mỗi loại có nội dung `vi` và `en` được duyệt độc lập.
- `db/init/50_post_treatment_chat.sql` chỉ giữ migration gốc của Branch 4: đánh dấu evidence đã release và chặn update/delete evidence đã release. Không có journey table mới.

Template endpoint là read-only. Chọn template chỉ điền nội dung vào draft; release vẫn dùng payload legacy và không lưu template selection/provenance riêng.

## UX merge-safe đã triển khai

| Slice | Hành vi hiện tại | Persistence |
|---|---|---|
| Release stepper | `Draft → Review → Released`; dentist phải review trước khi phát hành. | Chỉ release summary dùng API hiện có. |
| Approved templates | Chọn procedure/locale, xem approval/version/source và điền draft để dentist review. | Catalog là fixture tĩnh; lựa chọn UI không lưu riêng. |
| Patient timeline | Hiển thị release, acknowledgement, các mốc 24h/72h/168h và recall trong phiên đang mở. | Session-only; refresh/unmount xóa trạng thái bổ sung. |
| Acknowledgement | Demo “đã đọc và hiểu”. Không coi là informed consent. | Session-only; không gửi server. |
| Recovery check-in | Form cấu trúc về xu hướng, đau và red flags; red flag luôn hiện fixed escalation trước kết quả khác. | Session-only; không gửi server và không tạo staff task. |
| Callback | Có thể tạo callback draft để minh họa luồng. UI phải nói rõ clinic chưa nhận yêu cầu này. | Session-only; không gửi server. |
| Feedback | Câu trả lời cấu trúc, không free text mặc định. | Session-only; không gửi server. |
| Chat transcript | Bubble history và Clear action để test chat. | Chỉ component memory; không `localStorage`/`sessionStorage`, DB hoặc audit raw message. |
| Print | Print released summary, dates, warning signs và citations hiện có. | Không tạo bản ghi mới. |

Mọi control session-only phải hiển thị rõ “không được lưu/không được gửi”. Không được hứa clinic đã nhận callback, nhân viên đang theo dõi hoặc trạng thái check-in là chẩn đoán lâm sàng.

## Safety và privacy invariants

- Red flags gồm khó thở/nuốt, sưng lan hoặc tăng nhanh, chảy máu không kiểm soát và chấn thương nặng. Fixed escalation phải chạy trước intent/check-in classification khác.
- Không sinh hướng dẫn lâm sàng tự do bằng LLM, không tự dịch runtime cho nội dung safety-critical và không đưa liều thuốc.
- Patient không đọc draft. `MY_RECORD` chỉ đọc evidence đã `VERIFIED` và đã release, kèm citation.
- Ngoài nguồn được duyệt phải abstain.
- Raw chat không vào DB/audit/browser storage. Chỉ request chat hiện tại được gửi tới endpoint hiện có để nhận câu trả lời deterministic.
- Emergency notice độc lập với acknowledgement và luôn còn khả dụng.

## Feature persistence đã hoãn

Các mục sau **không được implement trên branch này** vì cần database/shared contracts và dễ gây conflict khi merge:

| ID | Feature hoãn | Cần quyết định ở integration branch |
|---|---|---|
| `INT-POST-00` | Stable release identity và immutable amendments | Release aggregate/version lineage, current-version selection, backfill và concurrency invariant. |
| `INT-POST-01` | Persistent acknowledgement | Real patient/proxy identity, consent wording, retention và idempotency. |
| `INT-POST-02` | Scheduled check-in persistence | Checkpoint/response schema, sensitive-data policy, due-window rules và staff escalation. |
| `INT-POST-03` | Callback request | Staff queue, clinic hours, SLA, assignment và notifications. |
| `INT-POST-04` | Feedback persistence/analytics | Retention, reporting scope và cross-module analytics. |
| `INT-POST-05` | Appointment/notification delivery | Booking, SMS/email/push, retries và delivery status. |

Không tạo client call tới endpoint giả định cho các mục trên. Khi integrator duyệt contract, thay session-only action từng slice bằng API thật và thêm PostgreSQL tests trước khi đổi nhãn UI.

## Agent merge checklist

1. Chỉ stage allowlist của Branch 4; không dùng `git add .`.
2. Ship `frontend/src/features/post-treatment-chat/index.css` nếu được import. Không commit local harness `preview.html`, `preview.jsx`, `preview.css`.
3. Xác nhận release request vẫn chỉ có ba field legacy và release/chat tests cũ vẫn pass.
4. Xác nhận source không gọi endpoint journey/check-in/acknowledgement/callback/amendment/feedback và không dùng browser storage.
5. Xác nhận SQL không có journey table mới và vẫn enforce immutable released evidence.
6. Chạy module tests, full tests, frontend build, `git diff --check`, rồi so sánh shipping paths với `origin/feat/compliance-integration`.
7. Integrator import router/route trong shared registries và chạy `make check` sau merge. Chỉ integrator giải quyết shared-file conflict.

## Nguồn governance

- [NHS England — Clinical guidance for urgent and non-urgent dental care](https://www.england.nhs.uk/long-read/clinical-guidance-unscheduled-urgent-and-non-urgent-dental-care/) dùng làm governance input cho urgency/red-flag navigation; không thay thế phê duyệt lâm sàng cho từng template.
- [WHO — Ethics and governance of artificial intelligence for health](https://www.who.int/publications/i/item/9789240029200) củng cố yêu cầu human oversight, transparency, privacy và safety.

## Handoff integrator
Router export: `from backend.app.features.post_treatment_chat import router`; routes tự mang prefix `/api/v1`.
Route export: `frontend/src/features/post-treatment-chat/index.jsx`; URL `/post-treatment`.
Verification: module 21/21 + full suite 28/28 pass; Vite production build, direct feature bundle, database-free scan và `git diff --check` pass; 0 shipping-path overlap với `origin/feat/compliance-integration`; red flag `Tôi khó thở và sưng lan nhanh`; implementation commit `3902cc2`.
