from fastapi import Header

from .core.security import parse_demo_role, require_demo_access


def require_demo_role(
    x_demo_role: str = Header(None, alias="X-Demo-Role"),
    x_demo_access_token: str = Header(None, alias="X-Demo-Access-Token"),
):
    require_demo_access(x_demo_access_token)
    return parse_demo_role(x_demo_role)
