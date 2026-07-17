# CareGuard Dental Demo

Demo nha khoa synthetic, không dùng cho quyết định lâm sàng.

```sh
docker compose build
make run
make reset-demo
make check
open http://localhost:5173
```

API health: `http://localhost:8000/api/health`. Vai trò demo được truyền qua header `X-Demo-Role`.

Xem [đặc tả 20 giờ](docs/20h-dental-demo-spec.md) và [quy tắc branch](docs/branch-rules.md).
