from .contracts import Role
from .errors import AppError


def parse_demo_role(value):
    if not value:
        raise AppError("DEMO_ROLE_REQUIRED", "X-Demo-Role header is required", status_code=401)
    try:
        return Role(value)
    except ValueError:
        raise AppError("DEMO_ROLE_INVALID", "X-Demo-Role is not allowed", {"role": value}, 403)
