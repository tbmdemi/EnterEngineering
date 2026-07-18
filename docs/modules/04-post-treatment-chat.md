# Module 04 — Post-treatment & Patient Chat

Frontend export contract: `export const route = { path, label, Component }`.

## Mục tiêu

Phát hành hướng dẫn/follow-up có kiểm soát và cho Patient hỏi từ nguồn đã duyệt. Draft hoặc staff-only content không được đi qua portal.

## Phạm vi

- Care instructions, recall, complication monitoring và follow-up task.
- Patient chat cho released record, clinic FAQ và approved symptom information.
- Red-flag escalation deterministic.
- Không chẩn đoán, kê đơn, general medical bot, realtime chat hoặc lưu raw chat.

Code nằm tại `backend/app/features/post_treatment_chat/`, `frontend/src/features/post-treatment-chat/`, `tests/post_treatment_chat/`. Release column/index được định nghĩa trong `db/init/50_post_treatment_chat.sql` và migration tích hợp.

## Release contract

`POST /api/v1/encounters/{encounter_id}/release`

```json
{
  "care_instructions": "Keep the area clean...",
  "recall_at": "2026-08-01T09:00:00+07:00",
  "monitor_until": "2026-07-25T09:00:00+07:00"
}
```

Chỉ `DENTIST` được release và Encounter phải đang đúng `POST_TREATMENT`:

- stage khác trả `409 ENCOUNTER_NOT_RELEASABLE`;
- `CLOSED` trả `409 ENCOUNTER_CLOSED`.

Một release atomically:

1. khóa Encounter;
2. upsert/release `POST_CARE_INSTRUCTIONS`, `POST_RECALL`, `POST_COMPLICATION_MONITORING`;
3. ensure một `PATIENT_FOLLOW_UP` task cho `ASSISTANT` bằng key `post-complication:{encounter_id}`;
4. append audit chỉ chứa evidence codes và task ID.

Response có `released=true` và `idempotent_replay`.

### Semantic idempotency

Retry cùng Encounter và cùng payload, khi released evidence cùng task due date đã tồn tại, trả lại logical result với `idempotent_replay=true`; không tạo evidence/task/audit trùng.

Nếu payload thay đổi khi Encounter vẫn ở `POST_TREATMENT`, release cập nhật nội dung/due date. Khi due date đổi, một follow-up task terminal có thể được reopen để công việc mới không bị bỏ quên.

## Patient chat contract

`POST /api/v1/portal/chat` bắt buộc body:

```json
{
  "encounter_id": "30000000-0000-0000-0000-000000000005",
  "message": "Lịch tái khám của tôi là khi nào?"
}
```

- Chỉ `PATIENT` được gọi.
- Không còn fallback sang một Encounter seed hard-code; caller phải gửi `encounter_id`.
- Encounter không tồn tại trả `404 ENCOUNTER_NOT_FOUND` trước khi answer/audit, thay vì lỗi khóa ngoại hoặc response giả.
- `MY_RECORD` chỉ query evidence `VERIFIED` có `released_to_patient_at`.
- `CLINIC_FAQ` và `SYMPTOM_INFO` chỉ trả approved card kèm citation.
- Ngoài nguồn cho phép thì abstain.
- Khó thở/nuốt, sưng lan nhanh, chảy máu không kiểm soát hoặc chấn thương nặng luôn trả fixed escalation, không chẩn đoán.

Response:

```json
{
  "intent": "MY_RECORD",
  "answer": "...",
  "citations": ["RELEASED_RECORD#POST_RECALL"],
  "escalation": false
}
```

Demo hiện dùng dữ liệu synthetic và role header; kiểm tra tồn tại không thay thế authorization ownership. Target product phải kiểm tra patient/proxy grant để bảo đảm Patient chỉ truy cập Encounter của mình.

## CLOSED invariant và follow-up

Sau `CLOSED`, không được release lại hoặc sửa post-treatment clinical evidence. Tuy nhiên released follow-up task đúng obligation/key đã được tạo trước close không được bị stranded: owner vẫn có thể acknowledge rồi complete, hoặc complete trực tiếp từ `OPEN`.

Ngoại lệ này không cho phép tạo follow-up mới, đổi released clinical content, chạy lại coordination evaluation hoặc reopen Encounter.

## Audit/privacy

Raw patient message không được ghi vào audit. `PORTAL_CHAT_ANSWERED` chỉ ghi intent, kết quả `ANSWERED/ABSTAINED/ESCALATED`, citation count và object/actor context.

## Acceptance và verification

- Release sai role/stage hoặc sau close bị từ chối atomically.
- Retry payload giống hệt không nhân bản dữ liệu/audit.
- Chat luôn yêu cầu `encounter_id` và chỉ đọc released evidence.
- Record answer có citation; ngoài nguồn abstain; red flag luôn escalation.
- Existing follow-up task có thể hoàn tất sau close nhưng không mở đường cho clinical write mới.

```powershell
python -m unittest tests.post_treatment_chat.test_feature -v
```
