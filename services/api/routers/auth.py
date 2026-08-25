"""Sign up, sign in, sign out.

Session cookie is httponly + samesite=lax, and `Secure` whenever the app is
actually served over HTTPS. `Secure` is not something a browser "relaxes" for
local dev — it is enforced at the transport layer: a browser (and httpx's test
client) will not attach a Secure cookie to a plain http:// request at all, so
hardcoding secure=True silently breaks every session on http://localhost and
under a test client. `COOKIE_SECURE` must be true in any real deployment, since
Vercel/Render both terminate TLS in front of the app."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from packages.shared.auth import (
    COOKIE_NAME,
    create_session,
    get_user_by_email,
    hash_password,
    revoke_session,
    verify_password,
)
from packages.shared.config import get_settings
from packages.shared.models import User

from ..deps import get_current_user, get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE_MAX_AGE = get_settings().session_ttl_hours * 3600


def _set_cookie(response: Response, value: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        value,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=get_settings().cookie_secure,
        path="/",
    )


class SignUpRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class SignInRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    name: str
    email: str

    @classmethod
    def from_model(cls, user: User) -> UserOut:
        return cls(id=str(user.id), name=user.name, email=user.email)


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def signup(
    body: SignUpRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    email = body.email.lower().strip()
    if await get_user_by_email(db, email) is not None:
        # Same message a wrong password gets on sign-in — do not let account
        # enumeration become a side channel of the signup form.
        raise HTTPException(status.HTTP_409_CONFLICT, "an account with this email already exists")

    user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password))
    db.add(user)
    await db.flush()

    result = await create_session(db, user, user_agent=request.headers.get("user-agent"))
    await db.commit()
    _set_cookie(response, result.cookie_value)
    return UserOut.from_model(user)


@router.post("/signin", response_model=UserOut)
async def signin(
    body: SignInRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    user = await get_user_by_email(db, body.email)
    # Verify against a real hash even on a missing user, so response timing does
    # not distinguish "no such account" from "wrong password."
    ok = verify_password(body.password, user.password_hash) if user else verify_password(
        body.password, hash_password("decoy-does-not-matter")
    )
    if not user or not ok or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "incorrect email or password")

    result = await create_session(db, user, user_agent=request.headers.get("user-agent"))
    await db.commit()
    _set_cookie(response, result.cookie_value)
    return UserOut.from_model(user)


@router.post("/signout", status_code=status.HTTP_204_NO_CONTENT)
async def signout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> None:
    cookie_value = request.cookies.get(COOKIE_NAME)
    await revoke_session(db, cookie_value)
    await db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me", response_model=UserOut | None)
async def me(user: User | None = Depends(get_current_user)) -> UserOut | None:
    return UserOut.from_model(user) if user else None


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    s = _SLUG_RE.sub("-", name.lower()).strip("-")
    return s or "org"
