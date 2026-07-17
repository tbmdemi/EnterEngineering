# CareGuard Dental Demo

Demo nha khoa synthetic, không dùng cho quyết định lâm sàng.

```sh
make setup
make check
make run
make reset-demo
open http://localhost:5173
```

`make setup` cài dependency đã khóa; `make check` không tải dependency và chỉ chạy sau setup.

API health: `http://localhost:8000/api/health`. Vai trò demo được truyền qua header `X-Demo-Role`.

Xem [đặc tả 20 giờ](docs/20h-dental-demo-spec.md) và [quy tắc branch](docs/branch-rules.md).
