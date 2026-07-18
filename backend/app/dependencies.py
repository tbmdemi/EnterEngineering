from fastapi import Header

from .core.security import parse_demo_role


def require_demo_role(x_demo_role: str = Header(None, alias="X-Demo-Role")):
    return parse_demo_role(x_demo_role)
