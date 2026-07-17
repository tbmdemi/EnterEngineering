# Quy tắc branch và merge

Mọi feature branch tách từ commit foundation của `feat/compliance-integration`; không merge chéo feature branch.

| Nhánh | Đường dẫn sở hữu |
|---|---|
| `feat/encounter` | `backend/app/features/encounter/`, `frontend/src/features/encounter/`, `tests/encounter/` |
| `feat/documentation-ai` | `backend/app/features/documentation_ai/`, `frontend/src/features/documentation-ai/`, `tests/documentation_ai/` |
| `feat/pre-treatment` | `backend/app/features/pre_treatment/`, `frontend/src/features/pre-treatment/`, `tests/pre_treatment/` |
| `feat/post-treatment-chat` | `backend/app/features/post_treatment_chat/`, `frontend/src/features/post-treatment-chat/`, `tests/post_treatment_chat/` |
| `feat/coordination` | `backend/app/features/coordination/`, `frontend/src/features/coordination/`, `tests/coordination/` |
| `feat/compliance-integration` | bootstrap, registry, navigation, Compose, shared contracts/schema, evaluator, audit/dashboard |

Feature có thể thêm duy nhất `db/init/<NN>_<feature>.sql` và sửa module spec của mình. Không sửa dependency manifests, core schema/enums, app bootstrap/router registry/navigation hoặc Compose; cần thay contract thì ghi rõ trong handoff, không tự đổi.

Trước bàn giao: rebase lên foundation nếu cần, chạy test module, ghi commit hash và đúng ba dòng handoff trong module spec. Integrator merge tuần tự và chạy `make check` sau từng merge; chỉ integrator giải quyết conflict shared file.
