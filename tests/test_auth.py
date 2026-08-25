"""Auth: signup, signin, signout, session persistence, and the failure paths a
real attacker would actually try."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_signup_then_me_returns_the_user(client: AsyncClient):
    r = await client.post("/api/auth/signup", json={
        "name": "Aarav Sharma", "email": "aarav@example.com", "password": "correct-horse-battery",
    })
    assert r.status_code == 201
    assert r.json()["email"] == "aarav@example.com"
    assert "sendrun_session" in r.cookies

    r = await client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == "aarav@example.com"


@pytest.mark.asyncio
async def test_me_without_a_session_is_null_not_an_error(client: AsyncClient):
    r = await client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json() is None


@pytest.mark.asyncio
async def test_duplicate_signup_is_rejected(client: AsyncClient):
    body = {"name": "A", "email": "dup@example.com", "password": "correct-horse-battery"}
    assert (await client.post("/api/auth/signup", json=body)).status_code == 201
    r = await client.post("/api/auth/signup", json=body)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_signin_with_wrong_password_is_rejected(client: AsyncClient):
    await client.post("/api/auth/signup", json={
        "name": "A", "email": "user@example.com", "password": "correct-horse-battery",
    })
    r = await client.post("/api/auth/signin", json={
        "email": "user@example.com", "password": "wrong-password",
    })
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_signin_with_nonexistent_email_gives_the_same_error(client: AsyncClient):
    """Same status and message as a wrong password — the point is that a caller
    cannot distinguish "no such account" from "wrong password" by the response."""
    r = await client.post("/api/auth/signin", json={
        "email": "ghost@example.com", "password": "whatever12345",
    })
    assert r.status_code == 401
    assert "incorrect email or password" in r.json()["detail"]


@pytest.mark.asyncio
async def test_signout_ends_the_session(client: AsyncClient):
    await client.post("/api/auth/signup", json={
        "name": "A", "email": "out@example.com", "password": "correct-horse-battery",
    })
    assert (await client.get("/api/auth/me")).json() is not None

    r = await client.post("/api/auth/signout")
    assert r.status_code == 204

    assert (await client.get("/api/auth/me")).json() is None


@pytest.mark.asyncio
async def test_tampered_session_cookie_is_rejected(client: AsyncClient):
    await client.post("/api/auth/signup", json={
        "name": "A", "email": "tamper@example.com", "password": "correct-horse-battery",
    })
    client.cookies.set("sendrun_session", client.cookies.get("sendrun_session") + "x")
    r = await client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json() is None
