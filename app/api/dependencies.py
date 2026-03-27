"""Shared API dependencies."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.services.admin_auth import AdminSession, get_session, parse_bearer_token


async def require_admin(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> AdminSession:
    token = parse_bearer_token(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    session = get_session(token)
    if not session or not session.is_admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    return session


AdminDependency = Annotated[AdminSession, Depends(require_admin)]
