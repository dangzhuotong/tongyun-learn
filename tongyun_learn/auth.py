import hashlib
import hmac
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from tongyun_learn.config import Settings, get_settings
from tongyun_learn.db import get_db
from tongyun_learn.errors import ApiError
from tongyun_learn.limits import bump_requests, rate_limiter


@dataclass(frozen=True)
class Principal:
    name: Literal["web", "axue"]


def get_principal(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise ApiError(
            status=401,
            code="unauthorized",
            message="缺少或无效的令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header[7:].strip()
    if not token:
        raise ApiError(
            status=401,
            code="unauthorized",
            message="缺少或无效的令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_sha = hashlib.sha256(token.encode("utf-8")).hexdigest()

    web_hash = settings.token_web_sha256.strip()
    axue_hash = settings.token_axue_sha256.strip()

    match_web = False
    match_axue = False

    if web_hash:
        if hmac.compare_digest(token_sha, web_hash):
            match_web = True
    else:
        hmac.compare_digest(token_sha, "0" * 64)

    if axue_hash:
        if hmac.compare_digest(token_sha, axue_hash):
            match_axue = True
    else:
        hmac.compare_digest(token_sha, "0" * 64)

    if not match_web and not match_axue:
        raise ApiError(
            status=401,
            code="unauthorized",
            message="缺少或无效的令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    principal_name: Literal["web", "axue"] = "web" if match_web else "axue"

    ok, retry_after = rate_limiter.check(principal_name, settings)
    if not ok:
        raise ApiError(
            status=429,
            code="rate_limited",
            message="请求太频繁",
            headers={"Retry-After": str(retry_after)},
        )

    bump_requests(db, principal_name, settings)

    return Principal(name=principal_name)


def require(*names: Literal["web", "axue"]) -> Callable[..., Principal]:
    def dependency(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
        if principal.name not in names:
            raise ApiError(status=403, code="forbidden", message="无权限")
        return principal

    return dependency
