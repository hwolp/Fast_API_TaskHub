import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_token, read_key
from app.main import app
from app.models import User
from app.models.enums import TokenType, UserRole

ROOT = Path(__file__).resolve().parents[1]
API = "/api/v1/workspaces/"


class WorkspaceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        base = Path(directory.name)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        (base / "private.pem").write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        (base / "public.pem").write_bytes(
            key.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
        for name, file in (
            ("JWT_PRIVATE_KEY_PATH", "private.pem"),
            ("JWT_PUBLIC_KEY_PATH", "public.pem"),
        ):
            patcher = patch.object(settings, name, str(base / file))
            patcher.start()
            self.addCleanup(patcher.stop)
        read_key.cache_clear()
        self.addCleanup(read_key.cache_clear)

        url = "sqlite+aiosqlite:///" + (base / "workspace.db").as_posix()
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT,
            env={**os.environ, "DATABASE_URL": url},
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        engine = create_async_engine(url)
        self.addAsyncCleanup(engine.dispose)
        self.sessions = async_sessionmaker(engine, expire_on_commit=False)

        async def override_db():
            async with self.sessions() as session:
                try:
                    yield session
                except Exception:
                    await session.rollback()
                    raise

        app.dependency_overrides[get_db] = override_db
        self.addCleanup(app.dependency_overrides.clear)
        self.client = AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        )
        self.addAsyncCleanup(self.client.aclose)
        await self.seed()

    async def seed(self):
        async with self.sessions() as session:
            users = {}
            for name in ("alice", "bob", "carol", "dave", "root"):
                users[name] = User(
                    email=f"{name}@example.com",
                    full_name=name.title(),
                    hashed_password="not-a-real-hash",
                    role=UserRole.ADMIN if name == "root" else UserRole.MEMBER,
                )
            session.add_all(users.values())
            await session.flush()
            self.uid = {name: user.id for name, user in users.items()}
            self.tokens = {
                name: create_token(user.id, user.role.value, TokenType.ACCESS)[0]
                for name, user in users.items()
            }
            await session.commit()

    def auth(self, who: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens[who]}"}

    async def test_create_list_get_update_and_delete_workspace(self):
        r = await self.client.post(
            API, json={"name": "Alice Workspace"}, headers=self.auth("alice")
        )
        self.assertEqual(r.status_code, 201, r.text)
        ws1 = r.json()
        self.assertEqual(ws1["owner_id"], self.uid["alice"])

        r = await self.client.post(
            API, json={"name": "Dave Workspace"}, headers=self.auth("dave")
        )
        self.assertEqual(r.status_code, 201)
        ws2 = r.json()

        r = await self.client.get(API, headers=self.auth("alice"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["total"], 1)
        self.assertEqual([w["id"] for w in r.json()["items"]], [ws1["id"]])

        r = await self.client.get(API, headers=self.auth("root"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["total"], 2)

        r = await self.client.get(f"{API}{ws1['id']}", headers=self.auth("dave"))
        self.assertEqual(r.status_code, 404)

        r = await self.client.patch(
            f"{API}{ws1['id']}",
            json={"name": "Renamed Workspace"},
            headers=self.auth("alice"),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["name"], "Renamed Workspace")

        r = await self.client.delete(f"{API}{ws2['id']}", headers=self.auth("dave"))
        self.assertEqual(r.status_code, 204)

    async def test_member_management_and_rbac(self):
        r = await self.client.post(
            API, json={"name": "Team Hub"}, headers=self.auth("alice")
        )
        ws_id = r.json()["id"]

        r = await self.client.post(
            f"{API}{ws_id}/members",
            json={"user_id": self.uid["bob"], "role": "OWNER"},
            headers=self.auth("alice"),
        )
        self.assertEqual(r.status_code, 422)

        r = await self.client.post(
            f"{API}{ws_id}/members",
            json={"user_id": self.uid["bob"], "role": "EDITOR"},
            headers=self.auth("alice"),
        )
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["role"], "EDITOR")

        r = await self.client.post(
            f"{API}{ws_id}/members",
            json={"user_id": self.uid["bob"], "role": "VIEWER"},
            headers=self.auth("alice"),
        )
        self.assertEqual(r.status_code, 409)

        r = await self.client.patch(
            f"{API}{ws_id}",
            json={"name": "Bob Takeover"},
            headers=self.auth("bob"),
        )
        self.assertEqual(r.status_code, 403)

        r = await self.client.post(
            f"{API}{ws_id}/members",
            json={"user_id": self.uid["carol"], "role": "VIEWER"},
            headers=self.auth("bob"),
        )
        self.assertEqual(r.status_code, 403)

        r = await self.client.patch(
            f"{API}{ws_id}/members/{self.uid['bob']}",
            json={"role": "VIEWER"},
            headers=self.auth("alice"),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["role"], "VIEWER")

        r = await self.client.patch(
            f"{API}{ws_id}/members/{self.uid['alice']}",
            json={"role": "EDITOR"},
            headers=self.auth("alice"),
        )
        self.assertEqual(r.status_code, 400)

        r = await self.client.delete(
            f"{API}{ws_id}/members/{self.uid['alice']}",
            headers=self.auth("alice"),
        )
        self.assertEqual(r.status_code, 400)

        r = await self.client.get(
            f"{API}{ws_id}/members", headers=self.auth("bob")
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 2)

        r = await self.client.delete(
            f"{API}{ws_id}/members/{self.uid['bob']}",
            headers=self.auth("bob"),
        )
        self.assertEqual(r.status_code, 204)

        r = await self.client.get(f"{API}{ws_id}", headers=self.auth("bob"))
        self.assertEqual(r.status_code, 404)
