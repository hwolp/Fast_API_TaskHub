import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
import jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import get_db
from app.core.security import read_key, token_hash
from app.main import app
from app.models import RefreshToken, User

ROOT = Path(__file__).resolve().parents[1]


class AuthTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        directory = Path(self.directory.name)
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_path, public_path = directory / "private.pem", directory / "public.pem"
        private_path.write_bytes(private.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        public_path.write_bytes(private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
        for name, value in (("JWT_PRIVATE_KEY_PATH", str(private_path)),
                            ("JWT_PUBLIC_KEY_PATH", str(public_path))):
            patcher = patch.object(settings, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        url = "sqlite+aiosqlite:///" + (directory / "auth.db").as_posix()
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT,
            env={**os.environ, "DATABASE_URL": url}, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.engine = create_async_engine(url)
        self.addAsyncCleanup(self.engine.dispose)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

        async def override_db():
            async with self.sessions() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        app.dependency_overrides[get_db] = override_db
        self.addCleanup(app.dependency_overrides.clear)
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        self.addAsyncCleanup(self.client.aclose)
        self.account = {"email": "Member@example.com", "password": "test-password-123",
                        "full_name": "Test Member"}

    async def post(self, endpoint, data):
        return await self.client.post("/api/v1/auth/" + endpoint, json=data)

    async def register_login(self):
        response = await self.post("register", self.account)
        self.assertEqual(response.status_code, 201, response.text)
        response = await self.post("login", self.account)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_register_login_and_access_validation(self):
        tokens = await self.register_login()
        duplicate = await self.post("register", {**self.account, "email": "member@example.com"})
        self.assertEqual(duplicate.status_code, 409)
        response = await self.client.get("/api/v1/auth/me", headers={
            "Authorization": "Bearer " + tokens["access_token"],
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["role"], "MEMBER")
        self.assertNotIn("hashed_password", response.json())
        self.assertEqual((await self.client.get("/api/v1/auth/me")).status_code, 401)
        self.assertEqual((await self.client.get("/api/v1/auth/me", headers={
            "Authorization": "Bearer " + tokens["refresh_token"],
        })).status_code, 401)
        self.assertEqual((await self.post("refresh", {
            "refresh_token": tokens["access_token"],
        })).status_code, 401)
        async with self.sessions() as session:
            user = await session.scalar(select(User))
            self.assertNotEqual(user.hashed_password, self.account["password"])
            stored = await session.scalar(select(RefreshToken))
            self.assertEqual(stored.token_hash, token_hash(tokens["refresh_token"]))

    async def test_refresh_reuse_revokes_family_but_not_other_login(self):
        tokens = await self.register_login()
        other = (await self.post("login", self.account)).json()
        rotated = await self.post("refresh", {"refresh_token": tokens["refresh_token"]})
        self.assertEqual(rotated.status_code, 200, rotated.text)
        self.assertNotEqual(rotated.json()["refresh_token"], tokens["refresh_token"])
        reuse = await self.post("refresh", {"refresh_token": tokens["refresh_token"]})
        self.assertEqual(reuse.status_code, 401)
        self.assertEqual(reuse.json()["detail"], "refresh_token_reused")
        self.assertEqual((await self.post("refresh", {
            "refresh_token": rotated.json()["refresh_token"],
        })).status_code, 401)
        self.assertEqual((await self.post("refresh", {
            "refresh_token": other["refresh_token"],
        })).status_code, 200)

    async def test_logout_revokes_refresh_and_is_idempotent(self):
        tokens = await self.register_login()
        body = {"refresh_token": tokens["refresh_token"]}
        self.assertEqual((await self.post("logout", body)).status_code, 204)
        self.assertEqual((await self.post("logout", body)).status_code, 204)
        self.assertEqual((await self.post("refresh", body)).status_code, 401)
        # Access tokens remain valid until their short expiry after logout.
        self.assertEqual((await self.client.get("/api/v1/auth/me", headers={
            "Authorization": "Bearer " + tokens["access_token"],
        })).status_code, 200)

    async def test_bad_credentials_inactive_and_invalid_input(self):
        tokens = await self.register_login()
        self.assertEqual((await self.post("login", {
            **self.account, "password": "wrong-password",
        })).status_code, 401)
        self.assertEqual((await self.post("register", {
            **self.account, "email": "invalid", "password": "short",
        })).status_code, 422)
        async with self.sessions() as session:
            await session.execute(update(User).values(is_active=False))
            await session.commit()
        self.assertEqual((await self.post("login", self.account)).status_code, 401)
        self.assertEqual((await self.post("refresh", {
            "refresh_token": tokens["refresh_token"],
        })).status_code, 401)
        self.assertEqual((await self.client.get("/api/v1/auth/me", headers={
            "Authorization": "Bearer " + tokens["access_token"],
        })).status_code, 401)

    async def test_expired_forged_wrong_audience_and_jwks(self):
        tokens = await self.register_login()
        payload = jwt.decode(tokens["access_token"], options={"verify_signature": False})
        for change, error in (
            ({"exp": datetime.now(timezone.utc) - timedelta(minutes=1)}, "token_expired"),
            ({"aud": "another-api"}, "token_invalid"),
        ):
            encoded = jwt.encode({**payload, **change}, read_key(settings.JWT_PRIVATE_KEY_PATH), algorithm="RS256")
            result = await self.client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + encoded})
            self.assertEqual(result.status_code, 401)
            self.assertEqual(result.json()["detail"], error)
        forged = jwt.encode(payload, "attacker-secret-that-is-long-enough", algorithm="HS256")
        self.assertEqual((await self.client.get("/api/v1/auth/me", headers={
            "Authorization": "Bearer " + forged,
        })).status_code, 401)
        jwks = (await self.client.get("/.well-known/jwks.json")).json()
        self.assertEqual(jwks["keys"][0]["kid"], settings.JWT_KEY_ID)
        self.assertNotIn("d", jwks["keys"][0])
