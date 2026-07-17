# Module 01 — Encounter

## Mục tiêu và pain point
Cho mọi module cùng một patient/appointment/encounter context và timeline; tránh thao tác nhầm ca hoặc mất trạng thái khi chuyển bước.

## Phạm vi / không làm
Hiển thị hồ sơ synthetic, header, năm stage và chỉ cho chuyển sang stage kế tiếp. Không đánh giá compliance, không chứa form chuyên môn, không xây scheduling.

## Đường dẫn sở hữu
`backend/app/features/encounter/`, `frontend/src/features/encounter/`, `tests/encounter/`, `db/init/10_encounter.sql` (chỉ khi thật sự cần).

## Consumes / produces
- Đọc core `patients`, `appointments`, `encounters`; dùng `EncounterStage` và `X-Demo-Role`.
- `GET /api/v1/encounters/{id}` → patient, appointment, encounter, `stage`, `version`.
- `POST /api/v1/encounters/{id}/stage` body `{stage, version}` → encounter mới; lỗi `{code,message,details}`.
- Không tạo evidence.

## Các bước
1. Test lookup ca demo, transition hợp lệ, skip/backward và stale version bị từ chối.
2. Viết router/repository tối thiểu và React route timeline.
3. Export `router` và `route`; không nối registry.

## Acceptance
Mở được UUID seed; đi đúng năm stage không mất context/version; stage skip/backward hoặc version cũ trả lỗi rõ ràng.

## Handoff integrator
Router export: ghi import path và prefix.
Route export: ghi import path và URL.
Verification: ghi lệnh test, kết quả và commit hash.
