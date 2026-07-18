# CareGuard Dental Demo

Demo nha khoa dùng dữ liệu synthetic, không dùng để đưa ra quyết định lâm sàng.

## Yêu cầu

- Docker Desktop hoặc Docker Engine có Docker Compose v2.
- Các cổng `5173`, `8000` và `5432` đang trống.
- Python/Node chỉ cần khi muốn chạy test trực tiếp ngoài Docker.

## Khởi động nhanh — có hot reload

Đây là chế độ khuyến nghị cho quá trình phát triển.

### Lần đầu hoặc sau khi đổi dependency/Dockerfile

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

### Những lần chạy tiếp theo

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

Mở giao diện:

- Trang chủ: http://localhost:5173
- Encounter: http://localhost:5173/encounter
- API: http://localhost:8000

Lần đầu mở Encounter, chọn một trong năm demo role. Có thể deep-link trực tiếp tới context cụ thể:

```text
http://localhost:5173/encounter?id=00000000-0000-0000-0000-000000000003&role=DENTIST
```

Source backend và frontend được bind mount. Khi sửa Python, JSX hoặc CSS, chỉ cần lưu file và refresh trình duyệt; không cần chạy lại Compose hoặc build image.

## Các lệnh development thường dùng

```sh
# Xem log API và web
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f api web

# Dừng container để giải phóng RAM, giữ database và container
docker compose -f docker-compose.yml -f docker-compose.dev.yml stop

# Chạy lại container đã dừng
docker compose -f docker-compose.yml -f docker-compose.dev.yml start

# Gỡ container/network nhưng giữ database volume
docker compose -f docker-compose.yml -f docker-compose.dev.yml down
```

Chỉ rebuild service có dependency hoặc Dockerfile thay đổi:

```sh
# Backend thay đổi requirements/Dockerfile
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build api

# Frontend thay đổi package.json, package-lock.json hoặc Dockerfile
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build web
```

## Reset dữ liệu demo

Lệnh sau xóa database volume và seed lại Encounter tại `CHECK_IN`:

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml down -v
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

Chỉ dùng `down -v` khi thực sự muốn xóa dữ liệu. Encounter seed:

```text
00000000-0000-0000-0000-000000000003
```

## Demo Encounter

Encounter giữ nguyên patient/appointment context và chỉ chuyển tuần tự:

```text
CHECK_IN → PRE_TREATMENT → TREATMENT → POST_TREATMENT → CLOSED
```

- `FRONT_DESK`, `ASSISTANT`, `DENTIST` được chuyển bước.
- `PATIENT`, `QA` không được chuyển bước.
- Mỗi mutation phải gửi đúng `version`.
- Version cũ trả `409 STALE_ENCOUNTER_VERSION`.
- Skip hoặc đi lùi trả `INVALID_STAGE_TRANSITION`.

Giao diện không hard-code role: role được chọn trên màn hình, lưu trong session và phản ánh trên URL. `PATIENT`/`QA` thấy context nhưng chỉ được đọc. Có thể bấm **Tiếp tục** với role được phép; trước khi chuyển sang `CLOSED`, giao diện yêu cầu xác nhận.

Nút **Làm mới** tải lại context và transition history. Khi quay lại tab, trang cũng tự refresh. Mỗi transition thành công được ghi append-only vào `audit_events` với action `ENCOUNTER_STAGE_CHANGED`; metadata chỉ chứa stage/version, không chứa PHI.

Response Encounter có contract rõ ràng:

```text
id, stage, version, patient, appointment, next_stage, can_advance
```

### Kiểm tra API bằng PowerShell

```powershell
$id = "00000000-0000-0000-0000-000000000003"
$headers = @{"X-Demo-Role" = "DENTIST"}

# Đọc Encounter
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/encounters/$id" -Headers $headers

# Đọc lịch sử chuyển stage
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/encounters/$id/transitions" -Headers $headers

# Chuyển từ CHECK_IN sang PRE_TREATMENT
$body = @{stage = "PRE_TREATMENT"; version = 1} | ConvertTo-Json
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/api/v1/encounters/$id/stage" `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $body
```

API health cũng yêu cầu demo role:

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/health" -Headers $headers
```

## Chạy test ngoài Docker

### Cài dependency một lần — Linux/macOS

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cd frontend && npm ci && cd ..
```

### Cài dependency một lần — Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Set-Location frontend
npm.cmd ci
Set-Location ..
```

### Test — Linux/macOS

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q backend
cd frontend && npm run build
```

PostgreSQL concurrency test cần database container đang chạy:

```sh
ENCOUNTER_TEST_DATABASE_URL='postgresql://careguard:careguard@localhost:5432/careguard?connect_timeout=5' \
  .venv/bin/python -m unittest tests.encounter.test_postgres_concurrency -v
```

### Test — Windows PowerShell

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q backend
Set-Location frontend
npm.cmd run build
Set-Location ..
```

PostgreSQL concurrency test trên Windows PowerShell:

```powershell
$env:ENCOUNTER_TEST_DATABASE_URL = "postgresql://careguard:careguard@localhost:5432/careguard?connect_timeout=5"
.\.venv\Scripts\python.exe -m unittest tests.encounter.test_postgres_concurrency -v
Remove-Item Env:ENCOUNTER_TEST_DATABASE_URL
```

Test này tạo fixture riêng, gửi đồng thời hai transition cùng version, yêu cầu đúng một request thành công, request còn lại nhận `STALE_ENCOUNTER_VERSION`, sau đó tự xóa fixture. Nếu không đặt `ENCOUNTER_TEST_DATABASE_URL`, test được skip để unit test không phụ thuộc Docker.

## Chạy không có hot reload

Phù hợp khi chỉ muốn demo, không sửa source liên tục:

```sh
# Build lần đầu hoặc sau khi code thay đổi
docker compose up -d --build

# Chạy lại khi image không đổi
docker compose up -d
```

Ở chế độ này source được đóng gói trong image, nên thay đổi code yêu cầu build lại service tương ứng.

## Tài liệu

- [Đặc tả demo 20 giờ](docs/20h-dental-demo-spec.md)
- [Module Encounter](docs/modules/01-encounter.md)
- [Quy tắc branch](docs/branch-rules.md)
