# CareGuard Dental Demo

CareGuard là demo workflow nha khoa tích hợp các module Encounter, Documentation AI, Pre-treatment, Coordination, Post-treatment/Patient Chat và Compliance.

> Dự án chỉ sử dụng dữ liệu synthetic để phát triển và trình diễn. Không nhập dữ liệu bệnh nhân thật và không dùng kết quả của demo để đưa ra quyết định lâm sàng.

## 1. Kiến trúc chạy local

Toàn bộ dự án dùng **một PostgreSQL duy nhất**:

```text
Browser :5173
    │
    ▼
web (React/Vite) ── /api proxy ──► api (FastAPI) :8000
                                           │
                                           ▼
                                  db (PostgreSQL) :5432
                                           ▲
                                           │
                                  migrate (job chạy một lần)
```

Các service Docker Compose:

| Service | Chức năng | Trạng thái bình thường |
|---|---|---|
| `db` | PostgreSQL dùng chung cho tất cả feature | `Up (healthy)` |
| `migrate` | Dùng `psql` để áp dụng migration rồi kết thúc | `Exited (0)` |
| `api` | FastAPI backend | `Up` |
| `web` | React/Vite frontend | `Up` |

Docker Desktop có thể hiển thị cả `db` và `migrate` dưới image `postgres:16-alpine`. Đây không phải hai database: chỉ `db` chạy PostgreSQL server; `migrate` là job tạm thời và dừng với exit code `0` là đúng thiết kế.

## 2. Yêu cầu

Bắt buộc để chạy demo:

- Git.
- Docker Desktop hoặc Docker Engine đang chạy.
- Docker Compose v2 (`docker compose`, không phải `docker-compose`).
- Các cổng `5173`, `8000` và `5432` chưa bị ứng dụng khác sử dụng.

Python 3.12 và Node.js 22 chỉ cần khi muốn chạy test/build trực tiếp ngoài Docker.

Kiểm tra Docker trước khi bắt đầu:

```powershell
docker version
docker compose version
```

`docker version` phải hiển thị cả phần `Client` và `Server`. Nếu chỉ có `Client`, chờ Docker Desktop báo **Engine running**, sau đó đóng và mở lại terminal.

## 3. Cài đặt và chạy lần đầu

Mở terminal tại thư mục gốc của repository, nơi có `docker-compose.yml`:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

Lệnh đầu kiểm tra cấu hình Compose. Lệnh thứ hai build image, tạo database volume, chạy migration và khởi động ứng dụng ở chế độ hot reload.

Kiểm tra trạng thái:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml ps -a
```

Kết quả mong đợi là `db`, `api`, `web` đang `Up`; `db` có trạng thái `healthy`; `migrate` là `Exited (0)`.

Mở ứng dụng:

| Màn hình | Địa chỉ |
|---|---|
| Encounter | http://localhost:5173/encounter |
| Documentation & Staff AI | http://localhost:5173/documentation-ai |
| Pre-treatment | http://localhost:5173/pre-treatment |
| Coordination | http://localhost:5173/coordination |
| Post-treatment & Patient Chat | http://localhost:5173/post-treatment |
| Compliance | http://localhost:5173/compliance |
| OpenAPI/Swagger | http://localhost:8000/docs |

Encounter demo mặc định:

```text
00000000-0000-0000-0000-000000000003
```

Có thể mở trực tiếp với role:

```text
http://localhost:5173/encounter?id=00000000-0000-0000-0000-000000000003&role=DENTIST
```

## 4. Làm việc hằng ngày

### Sau khi đã cài lần đầu

Không cần `--build` mỗi lần chạy:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

`docker-compose.dev.yml` bind mount source và bật hot reload:

- Sửa file Python trong `backend/app/`: API tự reload.
- Sửa JSX/CSS trong `frontend/`: Vite tự cập nhật trình duyệt.
- Không cần rebuild image khi chỉ sửa source code.

Sau khi pull/merge code mới, nên chạy:

```powershell
git pull
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
docker compose -f docker-compose.yml -f docker-compose.dev.yml ps -a
```

Job `migrate` sẽ áp dụng các migration idempotent mới trước khi API chạy.

### Khi nào phải rebuild?

| Thay đổi | Việc cần làm |
|---|---|
| Python/JSX/CSS thông thường | Chỉ lưu file; hot reload tự xử lý |
| `backend/requirements.txt` hoặc backend Dockerfile | Rebuild `api` |
| `frontend/package*.json` hoặc frontend Dockerfile | Rebuild `web` và cập nhật volume `node_modules` |
| File trong `db/migrations/` | Chạy lại `migrate`/Compose |
| Compose hoặc biến môi trường | Chạy lại `up -d`, thêm `--build` nếu image cũng đổi |

Rebuild backend:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build api
```

Sau khi dependency frontend thay đổi, cập nhật cả image và named volume chứa `node_modules`:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml build web
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm --no-deps web npm ci
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d web
```

Chạy lại migration và các service phụ thuộc:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d migrate api web
```

## 5. Dừng, chạy lại và xem log

```powershell
# Xem log gần nhất
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs --tail 100 db migrate api web

# Theo dõi log backend/frontend
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f api web

# Dừng để giải phóng RAM nhưng giữ container và dữ liệu
docker compose -f docker-compose.yml -f docker-compose.dev.yml stop

# Chạy lại các container đã dừng
docker compose -f docker-compose.yml -f docker-compose.dev.yml start

# Xóa container/network nhưng vẫn giữ database volume
docker compose -f docker-compose.yml -f docker-compose.dev.yml down

# Tạo lại container từ image hiện có
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

Không cần xóa container hoặc image sau mỗi lần test. Docker sẽ tái sử dụng image layer và volume.

## 6. Database, seed và migration

### Quy tắc chung

- Tất cả feature dùng database `careguard` trong service `db`.
- Không tạo thêm PostgreSQL service hoặc map thêm cổng database cho từng feature.
- Backend trong container kết nối bằng hostname `db`, không dùng `localhost`.
- Dữ liệu PostgreSQL được giữ trong named volume `dental_data`.
- `db/init/*.sql` chỉ tự chạy khi volume database được tạo lần đầu.
- Thay đổi cần áp dụng cho database đã tồn tại phải được viết trong `db/migrations/`.

### Thêm migration mới

Migration là shared integration scope. Thành viên chỉ tạo/sửa file theo ownership trong `docs/branch-rules.md`; nếu feature branch chưa được phép sửa `db/migrations/`, hãy ghi yêu cầu schema và SQL đề xuất trong handoff để integrator tạo migration.

Tạo file tuần tự, ví dụ:

```text
db/migrations/002_<feature>_<muc_dich>.sql
```

Migration của dự án được chạy lại qua job `migrate`, vì vậy phải idempotent:

- Bao migration trong `BEGIN`/`COMMIT` khi phù hợp.
- Dùng `CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`.
- Seed bằng `INSERT ... ON CONFLICT DO NOTHING/DO UPDATE`.
- Không xóa hoặc đổi nghĩa cột dùng chung khi chưa thống nhất contract với integrator.
- Dùng UUID/fixture deterministic cho dữ liệu demo; không dùng PHI thật.

Sau khi thêm migration:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d migrate api
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs migrate
```

`Exited (0)` nghĩa là migration thành công. Exit code khác `0` nghĩa là phải đọc log trước khi tiếp tục; code `2` của `psql` thường là lỗi kết nối, còn lỗi SQL sẽ chỉ rõ file và dòng gây lỗi.

### Reset riêng năm scenario synthetic

Sau khi đã chuyển stage, đóng ca hoặc hủy lịch trong lúc demo, dùng tool có scope hẹp dưới đây để đưa đúng năm scenario ở bảng bên dưới về trạng thái ban đầu. Lệnh không xóa volume và không đụng dữ liệu khác:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile tools run --rm demo-reset
```

Tool xóa dữ liệu phụ thuộc của năm Encounter cố định rồi seed lại bằng migration `002`; chạy lặp lại vẫn cho cùng kết quả.

### Reset toàn bộ database local

Lệnh dưới đây xóa vĩnh viễn database volume local và tạo lại seed từ đầu:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml down -v
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

Chỉ dùng `down -v` khi thực sự muốn mất toàn bộ dữ liệu local. Không dùng lệnh này như cách sửa lỗi migration thường ngày.

Database hiện có năm scenario synthetic ổn định để test UI mà không phải tự sửa cùng một Encounter:

| Scenario | Encounter ID | Kỳ vọng |
|---|---|---|
| Check-in trống | `30000000-0000-0000-0000-000000000001` | Có thể vào Pre-treatment vì appointment đã check-in |
| Pre-treatment chưa đủ | `30000000-0000-0000-0000-000000000002` | Bị chặn trước Treatment |
| Đang Treatment | `30000000-0000-0000-0000-000000000003` | Pre-treatment đã đạt; còn thiếu documentation để sang Post-treatment |
| Post-treatment bị chặn | `30000000-0000-0000-0000-000000000004` | Full close gate chỉ còn thiếu `POST_RECALL` |
| Post-treatment sẵn sàng | `30000000-0000-0000-0000-000000000005` | `ready_to_close=true` |

Mở một scenario bằng cách thay Encounter ID trên thanh context hoặc dùng URL, ví dụ:

```text
http://localhost:5173/encounter?id=30000000-0000-0000-0000-000000000002&role=DENTIST
```

Các scenario được tạo bởi `db/migrations/002_demo_scenarios.sql`, idempotent và chỉ chứa dữ liệu synthetic. Dùng `demo-reset` ở trên khi muốn chạy lại từ đầu trên volume hiện tại. Automated test vẫn là nơi kiểm tra authorization, transaction, idempotency và concurrency.

## 7. Luồng demo tích hợp

Encounter đi tuần tự:

```text
CHECK_IN → PRE_TREATMENT → TREATMENT → POST_TREATMENT → CLOSED
```

Role demo:

- `FRONT_DESK`, `ASSISTANT`, `DENTIST`: có thể đưa appointment đã check-in vào `PRE_TREATMENT`.
- Chỉ `DENTIST` được bắt đầu `TREATMENT`, kết thúc treatment và đóng Encounter.
- `QA`: đọc/đánh giá compliance nhưng không chuyển stage.
- `PATIENT`: chỉ truy cập dữ liệu đã được release cho bệnh nhân.

Backend áp dụng gate theo từng transition:

| Transition | Điều kiện |
|---|---|
| `CHECK_IN → PRE_TREATMENT` | Có appointment ở `CHECKED_IN` |
| `PRE_TREATMENT → TREATMENT` | Consent, treatment plan, khai báo `requires_imaging` và toàn bộ safety evidence applicable hợp lệ |
| `TREATMENT → POST_TREATMENT` | Documentation bắt buộc đã verified và có value hợp lệ |
| `POST_TREATMENT → CLOSED` | Full `dental-policy.v1` readiness |

Nhãn `VERIFIED` một mình không đủ: evaluator còn kiểm tra các field bắt buộc. Sau `CLOSED`, clinical content, stage, release và coordination write mới bị khóa; riêng task follow-up đã được tạo khi release vẫn có thể được acknowledge/complete để không làm kẹt chăm sóc sau khám. Appointment liên kết được chuyển atomically sang `FULFILLED`.

Encounter ID và role được giữ trong URL/session khi chuyển module. Luồng trình diễn đề xuất sau khi reset:

1. Mở Encounter bằng `DENTIST`, chuyển `CHECK_IN → PRE_TREATMENT`.
2. Sang Documentation AI, nhập documentation và để dentist xác nhận AI extraction.
3. Sang Pre-treatment, khai báo procedure có cần imaging hay không rồi hoàn tất safety checklist bằng `ASSISTANT` hoặc `DENTIST`. Medical history cần source reference; sterilization cần xác nhận và cycle/tray ID.
4. Sang Coordination, xử lý handoff, referral và schedule conflict theo đúng owner role. Resolve conflict yêu cầu status snapshot và reason code an toàn, không chứa PHI.
5. Trở lại Encounter và chuyển tới `POST_TREATMENT`.
6. Sang Post-treatment, release care instruction/recall/monitoring; `monitor_until` và `recall_at` phải có timezone, ở tương lai và `monitor_until <= recall_at`. Đổi sang `PATIENT` để thử chat.
7. Sang Compliance bằng `QA` hoặc `DENTIST`, chạy Evaluate và Readiness.
8. Khi `ready_to_close=true`, trở lại Encounter, xác nhận chuyển sang `CLOSED`.

Nếu close bị chặn, API trả `409 COMPLIANCE_NOT_READY`; `details.blockers` cho biết obligation, state và owner role cần xử lý.

Mỗi mutation Encounter phải gửi đúng `version`. Request dùng version cũ trả `409 STALE_ENCOUNTER_VERSION`; UI cần refresh rồi thử lại. Mỗi transition thành công được ghi append-only vào `audit_events` với metadata không chứa PHI.

## 8. Kiểm tra API nhanh

API yêu cầu header `X-Demo-Role`, kể cả health endpoint:

```powershell
$id = "00000000-0000-0000-0000-000000000003"
$headers = @{"X-Demo-Role" = "DENTIST"}

Invoke-RestMethod -Uri "http://localhost:8000/api/health" -Headers $headers
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/encounters/$id" -Headers $headers
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/encounters/$id/transitions" -Headers $headers
```

Ví dụ chuyển stage:

```powershell
$body = @{stage = "PRE_TREATMENT"; version = 1} | ConvertTo-Json
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/api/v1/encounters/$id/stage" `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $body
```

## 9. Cài dependency và chạy test ngoài Docker

### Windows PowerShell

Cài một lần:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Set-Location frontend
npm.cmd ci
Set-Location ..
```

Chạy unit/contract test và build check:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q backend
docker compose -f docker-compose.yml -f docker-compose.dev.yml config --quiet
Set-Location frontend
npm.cmd run build
Set-Location ..
```

Chạy toàn bộ test, bao gồm PostgreSQL concurrency, migration hardening và full-flow integration:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db migrate
$env:ENCOUNTER_TEST_DATABASE_URL = "postgresql://careguard:careguard@localhost:5432/careguard?connect_timeout=5"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
Remove-Item Env:ENCOUNTER_TEST_DATABASE_URL
```

Các integration test tạo fixture riêng và tự dọn dữ liệu. Chúng kiểm tra concurrent stage update, stage-specific safety gate, full close gate, appointment chuyển `FULFILLED` và tính bất biến sau `CLOSED`. Khi không đặt `ENCOUNTER_TEST_DATABASE_URL`, chúng được skip để unit test không bắt buộc Docker.

### Linux/macOS

Cài một lần:

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
(cd frontend && npm ci)
```

Chạy kiểm tra:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q backend
docker compose -f docker-compose.yml -f docker-compose.dev.yml config --quiet
(cd frontend && npm run build)
```

Chạy test cần PostgreSQL:

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db migrate
ENCOUNTER_TEST_DATABASE_URL='postgresql://careguard:careguard@localhost:5432/careguard?connect_timeout=5' \
  .venv/bin/python -m unittest discover -s tests -v
```

`Makefile` hiện là shortcut tùy chọn cho Linux/macOS và dùng base Compose. Khi phát triển hằng ngày hoặc làm việc trên Windows, ưu tiên các lệnh Compose có cả `docker-compose.dev.yml` ở trên.

## 10. Thêm hoặc cải tiến feature

Cấu trúc chính:

```text
backend/app/features/<feature>/       Backend router/service/model
frontend/src/features/<feature>/      React component và CSS của module
tests/<feature>/                      Unit/contract test của module
tests/integration/                    Test xuyên nhiều module
db/migrations/                        Thay đổi schema/seed cho DB đã tồn tại
docs/modules/                         Đặc tả và handoff từng module
```

Checklist khuyến nghị cho mỗi thay đổi:

1. Đọc `architecture.md`, `database.md`, `design.md` và module spec liên quan.
2. Xác định owner, role được phép, state transition, transaction và idempotency boundary.
3. Giữ API error contract chung; không hard-code role hoặc Encounter ID trong feature. POST retry phải dùng optimistic version, client/server idempotency key hoặc semantic idempotency được test rõ.
4. Nếu cần schema, chuẩn bị SQL idempotent theo branch ownership; integrator đưa thay đổi dùng chung vào migration. Không tạo database service riêng.
5. Backend feature nằm trong namespace của feature; validate content ở server, không chỉ tin UI hoặc cờ `VERIFIED`. Thay đổi shared core/router registry cần integrator duyệt.
6. Frontend export route theo contract hiện tại và giữ Encounter context qua URL/session.
7. Bổ sung test cho happy path, authorization, validation, stale state, retry và failure path. Mutation mới phải chứng minh bị chặn khi Encounter đã `CLOSED` hoặc đi qua amendment contract riêng.
8. Chạy unit test, integration test liên quan, frontend build và Compose config check.
9. Cập nhật module spec/handoff và README nếu cách chạy hoặc dependency thay đổi.

Quyền sở hữu file/branch và quy trình merge nằm trong [docs/branch-rules.md](docs/branch-rules.md). Khi feature cần sửa file dùng chung ngoài ownership, ghi rõ yêu cầu cho integrator thay vì âm thầm tạo phiên bản riêng.

## 11. Chạy image không có hot reload

Chế độ này phù hợp để trình diễn ổn định, không sửa source liên tục:

```powershell
# Lần đầu hoặc sau khi code/dependency thay đổi
docker compose up -d --build

# Những lần sau khi image không đổi
docker compose up -d
```

Trong chế độ này source nằm trong image, vì vậy thay đổi code yêu cầu rebuild service tương ứng.

## 12. Xử lý lỗi thường gặp

### Docker Desktop mở nhưng lệnh Docker không chạy

```powershell
docker version
docker context ls
```

Chờ Docker Desktop báo Engine running rồi mở terminal mới. Nếu terminal của chính bạn vẫn báo `permission denied`, kiểm tra quyền tài khoản Windows đối với nhóm `docker-users` và đăng xuất/đăng nhập lại sau khi cập nhật quyền.

### `migrate` không ở trạng thái Running

`migrate` là one-shot job. `Exited (0)` là thành công, không cần bật thủ công. Nếu exit code khác `0`:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs migrate
```

### Cổng đã được sử dụng

Trên Windows:

```powershell
Get-NetTCPConnection -LocalPort 5173,8000,5432 -ErrorAction SilentlyContinue
```

Dừng ứng dụng đang chiếm cổng hoặc thống nhất đổi port trong Compose; không tạo database thứ hai chỉ để né xung đột.

### UI mở được nhưng gọi API lỗi

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml ps -a
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs --tail 100 migrate api web
```

Kiểm tra `migrate` đã `Exited (0)`, API đang `Up`, Encounter ID hợp lệ và role đã được chọn.

### Sửa code nhưng giao diện không cập nhật

Đảm bảo đang chạy với cả hai file Compose. Base Compose đơn lẻ không bind mount source:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

### Database local không đúng trạng thái demo

Ưu tiên chạy migration và đọc log trước. Chỉ reset volume nếu thực sự muốn tạo lại toàn bộ dữ liệu:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d migrate api
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs migrate
```

## 13. Tài liệu dự án

- [Architecture](architecture.md)
- [Database design](database.md)
- [UI/UX design](design.md)
- [Đặc tả demo 20 giờ](docs/20h-dental-demo-spec.md)
- [Module Encounter](docs/modules/01-encounter.md)
- [Module Documentation & Staff AI](docs/modules/02-documentation-ai.md)
- [Module Pre-treatment](docs/modules/03-pre-treatment.md)
- [Module Post-treatment & Chat](docs/modules/04-post-treatment-chat.md)
- [Module Coordination](docs/modules/05-coordination.md)
- [Module Compliance & Integration](docs/modules/06-compliance-integration.md)
- [Quy tắc branch và merge](docs/branch-rules.md)
