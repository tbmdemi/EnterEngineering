import hmac
import os

from .contracts import Role
from .errors import AppError


def parse_demo_role(value):
    if not value:
        raise AppError("DEMO_ROLE_REQUIRED", "X-Demo-Role header is required", status_code=401)
    try:
        return Role(value)
    except ValueError:
        raise AppError("DEMO_ROLE_INVALID", "X-Demo-Role is not allowed", {"role": value}, 403)


def require_demo_access(value):
    expected = os.environ.get("DEMO_ACCESS_TOKEN", "")
    if not expected:
        return
    if not value or not hmac.compare_digest(value, expected):
        raise AppError("DEMO_ACCESS_DENIED", "A valid demo access key is required", status_code=401)
