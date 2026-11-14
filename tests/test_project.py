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
from app.models import User, Workspace, WorkspaceMember
from app.models.enums import TokenType, UserRole, WorkspaceRole

ROOT = Path(__file__).resolve().parents[1]
API = "/api/v1/projects/"


class ProjectTests(unittest.IsolatedAsyncioTestCase):
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

        url = "sqlite+aiosqlite:///" + (base / "project.db").as_posix()
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

            ws1 = Workspace(name="WS1", owner_id=self.uid["alice"])
            ws2 = Workspace(name="WS2", owner_id=self.uid["dave"])
            session.add_all([ws1, ws2])
            await session.flush()
            self.ws_id = {"ws1": ws1.id, "ws2": ws2.id}

            members = [
                WorkspaceMember(
                    workspace_id=ws1.id,
                    user_id=self.uid["alice"],
                    role=WorkspaceRole.OWNER,
                ),
                WorkspaceMember(
                    workspace_id=ws1.id,
                    user_id=self.uid["bob"],
                    role=WorkspaceRole.EDITOR,
                ),
                WorkspaceMember(
                    workspace_id=ws1.id,
                    user_id=self.uid["carol"],
                    role=WorkspaceRole.VIEWER,
                ),
                WorkspaceMember(
                    workspace_id=ws2.id,
                    user_id=self.uid["dave"],
                    role=WorkspaceRole.OWNER,
                ),
            ]
            session.add_all(members)
            await session.commit()

    def auth(self, who: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens[who]}"}

    async def test_create_and_get_project_rbac(self):
        r = await self.client.post(
            API,
            json={"workspace_id": self.ws_id["ws1"], "name": "Alice Project"},
            headers=self.auth("alice"),
        )
        self.assertEqual(r.status_code, 201)
        p1 = r.json()
        self.assertEqual(p1["name"], "Alice Project")

        r = await self.client.post(
            API,
            json={"workspace_id": self.ws_id["ws1"], "name": "Bob Project"},
            headers=self.auth("bob"),
        )
        self.assertEqual(r.status_code, 201)

        r = await self.client.post(
            API,
            json={"workspace_id": self.ws_id["ws1"], "name": "Carol Project"},
            headers=self.auth("carol"),
        )
        self.assertEqual(r.status_code, 403)

        r = await self.client.post(
            API,
            json={"workspace_id": self.ws_id["ws1"], "name": "Dave Project"},
            headers=self.auth("dave"),
        )
        self.assertEqual(r.status_code, 404)

        r = await self.client.post(
            API,
            json={"workspace_id": self.ws_id["ws1"], "name": "Admin Project"},
            headers=self.auth("root"),
        )
        self.assertEqual(r.status_code, 201)

        r = await self.client.get(f"{API}{p1['id']}", headers=self.auth("carol"))
        self.assertEqual(r.status_code, 200)

        r = await self.client.get(f"{API}{p1['id']}", headers=self.auth("dave"))
        self.assertEqual(r.status_code, 404)

    async def test_list_projects_and_filtering(self):
        for name in ("P1", "P2"):
            await self.client.post(
                API,
                json={"workspace_id": self.ws_id["ws1"], "name": name},
                headers=self.auth("alice"),
            )
        await self.client.post(
            API,
            json={"workspace_id": self.ws_id["ws2"], "name": "Dave P"},
            headers=self.auth("dave"),
        )

        r = await self.client.get(API, headers=self.auth("bob"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["total"], 2)

        r = await self.client.get(
            API,
            params={"workspace_id": self.ws_id["ws1"]},
            headers=self.auth("bob"),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["total"], 2)

        r = await self.client.get(
            API,
            params={"workspace_id": self.ws_id["ws2"]},
            headers=self.auth("bob"),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["total"], 0)

        r = await self.client.get(API, headers=self.auth("root"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["total"], 3)

    async def test_update_and_delete_project_rbac(self):
        r = await self.client.post(
            API,
            json={"workspace_id": self.ws_id["ws1"], "name": "Core"},
            headers=self.auth("alice"),
        )
        p_id = r.json()["id"]

        r = await self.client.patch(
            f"{API}{p_id}",
            json={"name": "Core Renamed"},
            headers=self.auth("bob"),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["name"], "Core Renamed")

        r = await self.client.patch(
            f"{API}{p_id}",
            json={"name": "Carol Renamed"},
            headers=self.auth("carol"),
        )
        self.assertEqual(r.status_code, 403)

        r = await self.client.patch(
            f"{API}{p_id}",
            json={"name": None},
            headers=self.auth("alice"),
        )
        self.assertEqual(r.status_code, 422)

        r = await self.client.delete(f"{API}{p_id}", headers=self.auth("bob"))
        self.assertEqual(r.status_code, 403)

        r = await self.client.delete(f"{API}{p_id}", headers=self.auth("carol"))
        self.assertEqual(r.status_code, 403)

        r = await self.client.delete(f"{API}{p_id}", headers=self.auth("alice"))
        self.assertEqual(r.status_code, 204)

        r = await self.client.get(f"{API}{p_id}", headers=self.auth("alice"))
        self.assertEqual(r.status_code, 404)

