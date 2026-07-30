from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jamasp.db import get_session
from jamasp.models.user import User
from jamasp.schemas.auth import LoginRequest, UserOut
from jamasp.security.deps import current_user
from jamasp.security.password import verify_password
from jamasp.security.tokens import SESSION_COOKIE, issue_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
async def login(
    payload: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> UserOut:
    user = (
        await session.scalars(select(User).where(User.email == payload.email))
    ).one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        # One message for both cases: distinguishing them enumerates accounts.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")

    response.set_cookie(
        SESSION_COOKIE,
        issue_token(str(user.id), str(user.role)),
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=12 * 3600,
        path="/",
    )
    return UserOut(id=user.id, email=user.email, role=str(user.role), locale=user.locale)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)) -> UserOut:
    return UserOut(id=user.id, email=user.email, role=str(user.role), locale=user.locale)
