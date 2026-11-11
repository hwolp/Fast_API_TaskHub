"""Authorization / RBAC / resource-ownership tests for the task endpoints.

Run with: python -m unittest discover -s tests -v
"""

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
from app.core.security import create_token
from app.main import app
from app.models import Project, User, Workspace, WorkspaceMember
from app.models.enums import UserRole, WorkspaceRole

ROOT = Path(__file__).resolve().parents[1]
API = "/api/v1/tasks/"


class TaskAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    """Fixture: ws1 (owner alice; bob+erin EDITOR; carol VIEWER) with project p1,
    ws2 (owner dave) with project p2, plus a system ADMIN `root` outside both."""

    async def asyncSetUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        base = Path(directory.name)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        (base / "private.pem").write_bytes(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        (base / "public.pem").write_bytes(key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
        for name, file in (("JWT_PRIVATE_KEY_PATH", "private.pem"),
                           ("JWT_PUBLIC_KEY_PATH", "public.pem")):
            patcher = patch.object(settings, name, str(base / file))
            patcher.start()
            self.addCleanup(patcher.stop)

        url = "sqlite+aiosqlite:///" + (base / "rbac.db").as_posix()
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT,
            env={**os.environ, "DATABASE_URL": url}, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        engine = create_async_engine(url)
        self.addAsyncCleanup(engine.dispose)
        self.sessions = async_sessionmaker(engine, expire_on_commit=False)

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
        await self.seed()

    async def seed(self):
        async with self.sessions() as session:
            users = {}
            for name in ("alice", "bob", "erin", "carol", "dave", "root"):
                users[name] = User(
                    email=f"{name}@example.com", full_name=name.title(),
                    hashed_password="not-a-real-hash",
                    role=UserRole.ADMIN if name == "root" else UserRole.MEMBER,
                )
            session.add_all(users.values())
            await session.flush()
            self.uid = {name: user.id for name, user in users.items()}
            self.tokens = {
                name: create_token(user.id, user.role.value, "access")[0]
                for name, user in users.items()
            }
            ws1 = Workspace(name="ws1", owner_id=self.uid["alice"])
            ws2 = Workspace(name="ws2", owner_id=self.uid["dave"])
            session.add_all([ws1, ws2])
            await session.flush()
            session.add_all([
                WorkspaceMember(workspace_id=ws1.id, user_id=self.uid["bob"], role=WorkspaceRole.EDITOR),
                WorkspaceMember(workspace_id=ws1.id, user_id=self.uid["erin"], role=WorkspaceRole.EDITOR),
                WorkspaceMember(workspace_id=ws1.id, user_id=self.uid["carol"], role=WorkspaceRole.VIEWER),
            ])
            p1 = Project(workspace_id=ws1.id, name="p1")
            p2 = Project(workspace_id=ws2.id, name="p2")
            session.add_all([p1, p2])
            await session.flush()
            self.p1, self.p2 = p1.id, p2.id
            await session.commit()

    def call(self, method, path, user=None, **kwargs):
        headers = {"Authorization": "Bearer " + self.tokens[user]} if user else {}
        return self.client.request(method, path, headers=headers, **kwargs)

    async def make_task(self, user, project=None, **extra):
        response = await self.call(
            "POST", API, user, json={"title": "t", "project_id": project or self.p1, **extra},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    async def test_every_endpoint_requires_authentication(self):
        for method, path in (("POST", API), ("GET", API), ("GET", API + "1"),
                             ("PATCH", API + "1"), ("DELETE", API + "1")):
            response = await self.call(method, path, json={"title": "x", "project_id": 1})
            self.assertEqual(response.status_code, 401, (method, path))
            self.assertEqual(response.json()["detail"], "token_missing")

    async def test_created_by_comes_from_token_not_body(self):
        task = await self.make_task("bob", created_by=self.uid["alice"])
        self.assertEqual(task["created_by"], self.uid["bob"])

    async def test_viewer_is_read_only(self):
        task = await self.make_task("alice")
        self.assertEqual((await self.call("GET", API + str(task["id"]), "carol")).status_code, 200)
        create = await self.call("POST", API, "carol", json={"title": "x", "project_id": self.p1})
        self.assertEqual(create.status_code, 403)
        self.assertEqual((await self.call(
            "PATCH", API + str(task["id"]), "carol", json={"title": "y"})).status_code, 403)
        self.assertEqual((await self.call("DELETE", API + str(task["id"]), "carol")).status_code, 403)

    async def test_non_member_cannot_see_or_touch_anything_in_workspace(self):
        task = await self.make_task("alice")
        url = API + str(task["id"])
        for method, kwargs in (("GET", {}), ("PATCH", {"json": {"title": "y"}}), ("DELETE", {})):
            response = await self.call(method, url, "dave", **kwargs)
            self.assertEqual(response.status_code, 404, method)
            self.assertEqual(response.json()["detail"], "task_not_found")
        create = await self.call("POST", API, "dave", json={"title": "x", "project_id": self.p1})
        self.assertEqual((create.status_code, create.json()["detail"]), (404, "project_not_found"))

    async def test_editor_may_only_modify_own_or_assigned_tasks(self):
        own = await self.make_task("bob")
        assigned = await self.make_task("alice", assignee_id=self.uid["bob"])
        others = await self.make_task("alice")
        patch_ok = await self.call("PATCH", f"{API}{own['id']}", "bob", json={"status": "DONE"})
        self.assertEqual((patch_ok.status_code, patch_ok.json()["status"]), (200, "DONE"))
        self.assertEqual((await self.call(
            "PATCH", f"{API}{assigned['id']}", "bob", json={"title": "mine now"})).status_code, 200)
        self.assertEqual((await self.call(
            "PATCH", f"{API}{others['id']}", "bob", json={"title": "z"})).status_code, 403)
        self.assertEqual((await self.call(
            "PATCH", f"{API}{own['id']}", "erin", json={"title": "z"})).status_code, 403)

    async def test_editor_may_only_delete_tasks_they_created(self):
        own = await self.make_task("bob")
        assigned = await self.make_task("alice", assignee_id=self.uid["bob"])
        self.assertEqual((await self.call("DELETE", f"{API}{assigned['id']}", "bob")).status_code, 403)
        self.assertEqual((await self.call("DELETE", f"{API}{own['id']}", "erin")).status_code, 403)
        self.assertEqual((await self.call("DELETE", f"{API}{own['id']}", "bob")).status_code, 204)
        self.assertEqual((await self.call("GET", f"{API}{own['id']}", "bob")).status_code, 404)

    async def test_workspace_owner_and_system_admin_manage_any_task(self):
        task = await self.make_task("bob")
        self.assertEqual((await self.call(
            "PATCH", f"{API}{task['id']}", "alice", json={"title": "by owner"})).status_code, 200)
        self.assertEqual((await self.call(
            "PATCH", f"{API}{task['id']}", "root", json={"title": "by admin"})).status_code, 200)
        self.assertEqual((await self.call("DELETE", f"{API}{task['id']}", "root")).status_code, 204)
        foreign = await self.make_task("dave", project=self.p2)
        self.assertEqual((await self.call("DELETE", f"{API}{foreign['id']}", "alice")).status_code, 404)

    async def test_assignee_must_belong_to_workspace(self):
        bad = await self.call("POST", API, "alice", json={
            "title": "x", "project_id": self.p1, "assignee_id": self.uid["dave"]})
        self.assertEqual((bad.status_code, bad.json()["detail"]), (400, "assignee_not_in_workspace"))
        task = await self.make_task("alice")
        bad_patch = await self.call(
            "PATCH", f"{API}{task['id']}", "alice", json={"assignee_id": self.uid["dave"]})
        self.assertEqual(bad_patch.status_code, 400)
        good = await self.call(
            "PATCH", f"{API}{task['id']}", "alice", json={"assignee_id": self.uid["carol"]})
        self.assertEqual((good.status_code, good.json()["assignee_id"]), (200, self.uid["carol"]))

    async def test_list_is_scoped_to_visible_workspaces_and_paginated(self):
        for _ in range(3):
            await self.make_task("alice")
        await self.make_task("dave", project=self.p2)
        mine = await self.call("GET", API, "carol")
        self.assertEqual(mine.status_code, 200)
        body = mine.json()
        self.assertEqual(body["total"], 3)
        self.assertTrue(all(t["project_id"] == self.p1 for t in body["items"]))
        page = await self.call("GET", API + "?page=2&limit=2", "carol")
        page_body = page.json()
        self.assertEqual(len(page_body["items"]), 1)
        self.assertEqual(page_body["total"], 3)
        self.assertEqual((await self.call("GET", API, "dave")).json()["total"], 1)
        self.assertEqual((await self.call("GET", API, "root")).json()["total"], 4)
        outsider = await self.call("GET", API, "erin")  # member of ws1 only
        self.assertEqual(outsider.json()["total"], 3)
        self.assertEqual((await self.call("GET", API + "?limit=0", "root")).status_code, 422)

    async def test_null_for_required_fields_is_a_422_not_a_500(self):
        task = await self.make_task("alice")
        for field in ("title", "status", "priority"):
            response = await self.call(
                "PATCH", f"{API}{task['id']}", "alice", json={field: None})
            self.assertEqual(response.status_code, 422, field)
        cleared = await self.call(
            "PATCH", f"{API}{task['id']}", "alice", json={"due_date": None, "assignee_id": None})
        self.assertEqual(cleared.status_code, 200)

    async def test_inactive_user_loses_access_immediately(self):
        from sqlalchemy import update
        async with self.sessions() as session:
            await session.execute(update(User).where(User.id == self.uid["bob"]).values(is_active=False))
            await session.commit()
        self.assertEqual((await self.call("GET", API, "bob")).status_code, 401)


if __name__ == "__main__":
    unittest.main()

