# Module 04 — Post-treatment & Patient Chat

## Mục tiêu và pain point
Đảm bảo hướng dẫn/follow-up không bị quên và bệnh nhân chỉ nhận thông tin đã phát hành, có nguồn và escalation an toàn.

## Phạm vi / không làm
Care instructions, recall, complication task, release summary và chatbot ba intent. Không chẩn đoán, kê đơn, general medical bot, realtime chat hoặc lưu raw chat.

## Đường dẫn sở hữu
`backend/app/features/post_treatment_chat/`, `frontend/src/features/post-treatment-chat/`, `tests/post_treatment_chat/`, `db/init/50_post_treatment_chat.sql`.

## Consumes / produces
- Dùng encounter/evidence/task và core services.
- Evidence: `POST_CARE_INSTRUCTIONS`, `POST_RECALL`, `POST_COMPLICATION_MONITORING`.
- `POST /api/v1/encounters/{id}/release` → released summary.
- `POST /api/v1/portal/chat` body `{message}` → `{intent,answer,citations,escalation}`.
- Intent: `MY_RECORD`, `CLINIC_FAQ`, `SYMPTOM_INFO`; nguồn chỉ released record, seeded FAQ hoặc approved dental content.

## Các bước
1. Test draft isolation, citations, abstain, release và fixed red-flag response.
2. Viết release/chat deterministic bằng keyword nhỏ; red flags: khó thở/nuốt, sưng lan nhanh, chảy máu không kiểm soát, chấn thương nặng.
3. Không ghi raw message vào audit; export router/route.

## Acceptance
Patient không đọc draft; answer record có citation; ngoài nguồn abstain; red flag luôn escalation và không có chẩn đoán/đơn thuốc.

## Handoff integrator
Router export: ghi import path và prefix.
Route export: ghi import path và URL.
Verification: ghi lệnh test, red-flag fixture và commit hash.
