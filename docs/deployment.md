# Deployment — CareGuard synthetic demo

Tài liệu này chỉ áp dụng cho dữ liệu synthetic. `X-Demo-Role` và demo access key không phải hệ thống identity đủ dùng cho dữ liệu bệnh nhân thật.

## 1. Kiến trúc khuyến nghị

### Render

```text
careguard-web.onrender.com (Vite static site)
             │ HTTPS/CORS
             ▼
careguard-api.onrender.com (FastAPI Docker web service)
             │ private DATABASE_URL
             ▼
careguard-db (Render PostgreSQL 16)
```

`render.yaml` khai báo cả ba resource. API và database dùng gói always-on nhỏ nhất vì pre-deploy migration và database bền vững không phù hợp với một demo cần giữ dữ liệu nếu dùng tài nguyên hết hạn/sleep.

### VPS một domain

```text
https://demo.example.com
          │
       Caddy :443
          │
       nginx web ── /api/* ──► FastAPI ──► PostgreSQL
```

Chỉ Caddy publish `80/443`. API và PostgreSQL ở Docker network nội bộ.

## 2. Deploy lên Render

### Chuẩn bị

1. Push branch đã qua CI lên GitHub/GitLab/Bitbucket.
2. Tạo Render account và kết nối repository.
3. Xác nhận tên `careguard-web` và `careguard-api` còn khả dụng. Nếu đổi tên, cập nhật cả:
   - `VITE_API_BASE_URL` của static site;
   - `ALLOWED_ORIGINS` và `ALLOWED_HOSTS` của API.
4. Chỉ sử dụng synthetic scenarios trong `002_demo_scenarios.sql`.

### Tạo Blueprint

1. Chọn **New → Blueprint** trong Render Dashboard.
2. Chọn repository và file `render.yaml`.
3. Review ba resource: `careguard-db`, `careguard-api`, `careguard-web`.
4. Apply Blueprint và chờ database được tạo.
5. API build image, chạy `python /app/migrate.py` ở pre-deploy rồi mới start Uvicorn.
6. Frontend chạy `npm ci && npm run build` và publish `dist`.

Migration runner giữ PostgreSQL advisory lock, lưu checksum trong `schema_migrations` và từ chối nếu nội dung một migration đã áp dụng bị sửa.

### Access key

`render.yaml` tạo `DEMO_ACCESS_TOKEN` cho API. Đặt lại thành một key dài do nhóm quản lý nếu cần chia sẻ dễ hơn, lưu trong password manager, sau đó nhập key vào ô **Demo access key** trên giao diện. Key chỉ nằm trong `sessionStorage`, không được đưa vào URL hoặc commit.

### URL kiểm tra

```text
https://careguard-api.onrender.com/api/health/live
https://careguard-api.onrender.com/api/health/ready
https://careguard-web.onrender.com/encounter?id=30000000-0000-0000-0000-000000000001&role=DENTIST
```

`live` phải trả `200 {"status":"ok"}`. `ready` chỉ trả 200 khi API kết nối được database. URL thật phụ thuộc tên service được Render chấp nhận.

### Custom domain

Sau khi URL `onrender.com` chạy ổn:

1. Thêm domain, ví dụ `demo.example.com`, vào static site.
2. Cập nhật DNS theo hướng dẫn Render.
3. Đổi `ALLOWED_ORIGINS` sang `https://demo.example.com`.
4. Rebuild frontend nếu API URL thay đổi.

## 3. Deploy lên VPS bằng Compose

Yêu cầu: Ubuntu LTS, Docker Engine + Compose plugin, domain đã trỏ DNS về VPS, firewall chỉ mở `22` từ IP quản trị và `80/443` từ internet.

```sh
cp .env.example .env
# Sửa .env bằng password/access key ngẫu nhiên và domain thật.
chmod 600 .env
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps -a
```

Caddy tự xin/gia hạn TLS khi DNS đúng và cổng 80/443 truy cập được. Không chạy `docker-compose.dev.yml` trên VPS.

## 4. Backup và restore

Named volume không thay thế backup. Trước migration và theo lịch vận hành:

```sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T db \
  pg_dump -U careguard -d careguard -Fc > careguard-$(date +%F).dump
```

Mã hóa và chuyển dump ra storage khác VPS. Định kỳ restore vào database tạm để chứng minh backup dùng được.

## 5. Smoke test và rollback

Trước khi chia sẻ URL:

1. CI pass toàn bộ test, compile, Vite build và production image build.
2. Database trống chạy được `000` → `003` và có rows trong `schema_migrations`.
3. Refresh trực tiếp `/encounter`, `/coordination`, `/compliance` không 404.
4. Request thiếu/sai demo access key bị `401 DEMO_ACCESS_DENIED`.
5. PostgreSQL/API ports không public ở deployment VPS.
6. Restart containers không mất dữ liệu.
7. `demo-reset` chỉ chạy thủ công khi thật sự muốn reset năm scenario.

Rollback code bằng image/commit trước đó. Không rollback schema bằng cách xóa migration đã áp dụng; dùng forward-fix migration mới và restore backup nếu có data corruption.

## 6. Không dùng dữ liệu thật

Trước dữ liệu bệnh nhân thật, tối thiểu phải thay demo role/access key bằng OIDC/session hoặc JWT, bind user với organization/patient/resource phía server, bổ sung least privilege, audit truy cập, encryption/key management, retention/deletion, incident response và các yêu cầu pháp lý áp dụng. Deployment demo này không đáp ứng các điều kiện đó.
