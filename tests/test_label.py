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
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_token, read_key
from app.main import app
from app.models import Label, Project, TaskLabel, User, Workspace, WorkspaceMember
from app.models.enums import ProjectStatus, TokenType, UserRole, WorkspaceRole

ROOT = Path(__file__).resolve().parents[1]
API = "/api/v1/labels/"
TASK_API = "/api/v1/tasks/"


class LabelTests(unittest.IsolatedAsyncioTestCase):
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

        url = "sqlite+aiosqlite:///" + (base / "label.db").as_posix()
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
            for name in ("alice", "bob", "erin", "carol", "dave", "root"):
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

            session.add_all(
                [
                    WorkspaceMember(
                        workspace_id=ws1.id,
                        user_id=self.uid["bob"],
                        role=WorkspaceRole.EDITOR,
                    ),
                    WorkspaceMember(
                        workspace_id=ws1.id,
                        user_id=self.uid["erin"],
                        role=WorkspaceRole.EDITOR,
                    ),
                    WorkspaceMember(
                        workspace_id=ws1.id,
                        user_id=self.uid["carol"],
                        role=WorkspaceRole.VIEWER,
                    ),
                ]
            )
            p1 = Project(workspace_id=ws1.id, name="P1")
            p1_other = Project(workspace_id=ws1.id, name="P1 Other")
            p2 = Project(workspace_id=ws2.id, name="P2")
            session.add_all([p1, p1_other, p2])
            await session.flush()
            self.ws1 = ws1.id
            self.p1 = p1.id
            self.p1_other = p1_other.id
            self.p2 = p2.id
            await session.commit()

    def call(self, method: str, path: str, user: str | None = None, **kwargs):
        headers = {"Authorization": f"Bearer {self.tokens[user]}"} if user else {}
        return self.client.request(method, path, headers=headers, **kwargs)

    async def make_label(self, user: str = "alice", project_id: int | None = None, **extra):
        payload = {
            "project_id": project_id or self.p1,
            "name": "Bug",
            **extra,
        }
        res = await self.call("POST", API, user, json=payload)
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()

    async def make_task(self, user: str = "alice", project_id: int | None = None, **extra):
        payload = {
            "project_id": project_id or self.p1,
            "title": "Sample Task",
            **extra,
        }
        res = await self.call("POST", TASK_API, user, json=payload)
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()

    async def test_every_label_endpoint_requires_authentication(self):
        for method, path in (
            ("POST", API),
            ("GET", API),
            ("GET", f"{API}1"),
            ("PATCH", f"{API}1"),
            ("DELETE", f"{API}1"),
            ("POST", f"{TASK_API}1/labels/1"),
            ("DELETE", f"{TASK_API}1/labels/1"),
        ):
            res = await self.call(method, path, json={"name": "x", "project_id": 1})
            self.assertEqual(res.status_code, 401, (method, path))
            self.assertEqual(res.json()["detail"], "token_missing")

    async def test_label_crud_and_rbac(self):
        label = await self.make_label("bob", name="Backend")
        self.assertEqual(label["name"], "Backend")
        self.assertEqual(label["color"], "#3B82F6")
        self.assertEqual(label["project_id"], self.p1)

        # VIEWER can read, but cannot create, update, or delete
        get_res = await self.call("GET", f"{API}{label['id']}", "carol")
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(
            (
                await self.call(
                    "POST", API, "carol", json={"project_id": self.p1, "name": "No"}
                )
            ).status_code,
            403,
        )
        self.assertEqual(
            (
                await self.call(
                    "PATCH", f"{API}{label['id']}", "carol", json={"name": "No"}
                )
            ).status_code,
            403,
        )
        self.assertEqual(
            (await self.call("DELETE", f"{API}{label['id']}", "carol")).status_code,
            403,
        )

        # Non-member receives 404 (IDOR protection)
        create_idor = await self.call(
            "POST", API, "dave", json={"project_id": self.p1, "name": "Leak"}
        )
        self.assertEqual(
            (create_idor.status_code, create_idor.json()["detail"]),
            (404, "project_not_found"),
        )
        for method, kw in (
            ("GET", {}),
            ("PATCH", {"json": {"name": "Leak"}}),
            ("DELETE", {}),
        ):
            r = await self.call(method, f"{API}{label['id']}", "dave", **kw)
            self.assertEqual(
                (r.status_code, r.json()["detail"]), (404, "label_not_found"), method
            )

        # Reject null for required columns
        for field in ("name", "color"):
            bad_null = await self.call(
                "PATCH", f"{API}{label['id']}", "alice", json={field: None}
            )
            self.assertEqual(bad_null.status_code, 422, field)

        # EDITOR / OWNER / ADMIN can update and delete
        patch_res = await self.call(
            "PATCH",
            f"{API}{label['id']}",
            "erin",
            json={"name": "Urgent", "color": "#EF4444"},
        )
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.json()["name"], "Urgent")
        self.assertEqual(patch_res.json()["color"], "#EF4444")

        del_res = await self.call("DELETE", f"{API}{label['id']}", "alice")
        self.assertEqual(del_res.status_code, 204)
        self.assertEqual(
            (await self.call("GET", f"{API}{label['id']}", "alice")).status_code, 404
        )

    async def test_list_labels_filtering_and_pagination(self):
        for i in range(3):
            await self.make_label("alice", project_id=self.p1, name=f"L{i}")
        await self.make_label("alice", project_id=self.p1_other, name="OtherProj")
        await self.make_label("dave", project_id=self.p2, name="DaveLabel")

        res_carol = await self.call("GET", API, "carol")
        self.assertEqual(res_carol.status_code, 200)
        self.assertEqual(res_carol.json()["total"], 4)

        res_p1 = await self.call("GET", f"{API}?project_id={self.p1}", "carol")
        self.assertEqual(res_p1.status_code, 200)
        self.assertEqual(res_p1.json()["total"], 3)
        self.assertTrue(
            all(item["project_id"] == self.p1 for item in res_p1.json()["items"])
        )

        res_page = await self.call(
            "GET", f"{API}?project_id={self.p1}&page=2&limit=2", "carol"
        )
        self.assertEqual(res_page.status_code, 200)
        self.assertEqual(len(res_page.json()["items"]), 1)
        self.assertEqual(res_page.json()["total"], 3)

        res_dave = await self.call("GET", API, "dave")
        self.assertEqual(res_dave.json()["total"], 1)

        res_root = await self.call("GET", API, "root")
        self.assertEqual(res_root.json()["total"], 5)

        self.assertEqual(
            (await self.call("GET", f"{API}?limit=0", "alice")).status_code, 422
        )

    async def test_attach_and_detach_label_rbac_and_project_mismatch(self):
        label = await self.make_label("alice", project_id=self.p1)
        other_label = await self.make_label("alice", project_id=self.p1_other)
        dave_label = await self.make_label("dave", project_id=self.p2)

        task_bob = await self.make_task("bob", assignee_id=self.uid["erin"])
        task_alice = await self.make_task("alice")

        url = f"{TASK_API}{task_bob['id']}/labels/{label['id']}"

        # Creator (bob) and assignee (erin) can attach/detach (idempotent attach)
        self.assertEqual((await self.call("POST", url, "bob")).status_code, 204)
        self.assertEqual((await self.call("POST", url, "erin")).status_code, 204)
        self.assertEqual((await self.call("DELETE", url, "erin")).status_code, 204)
        # Detach unattached label returns 404 label_not_attached
        unattached_res = await self.call("DELETE", url, "bob")
        self.assertEqual(
            (unattached_res.status_code, unattached_res.json()["detail"]),
            (404, "label_not_attached"),
        )

        # Unrelated EDITOR (bob on alice's unassigned task) and VIEWER get 403
        alice_task_url = f"{TASK_API}{task_alice['id']}/labels/{label['id']}"
        self.assertEqual(
            (await self.call("POST", alice_task_url, "bob")).status_code, 403
        )
        self.assertEqual(
            (await self.call("DELETE", alice_task_url, "bob")).status_code, 403
        )
        self.assertEqual((await self.call("POST", url, "carol")).status_code, 403)
        self.assertEqual((await self.call("DELETE", url, "carol")).status_code, 403)

        # Non-member gets 404
        self.assertEqual((await self.call("POST", url, "dave")).status_code, 404)
        self.assertEqual(
            (
                await self.call(
                    "POST",
                    f"{TASK_API}{task_bob['id']}/labels/{dave_label['id']}",
                    "alice",
                )
            ).status_code,
            404,
        )

        # Label from another project in the same workspace returns 400 label_project_mismatch
        mismatch_url = f"{TASK_API}{task_bob['id']}/labels/{other_label['id']}"
        mismatch_res = await self.call("POST", mismatch_url, "alice")
        self.assertEqual(
            (mismatch_res.status_code, mismatch_res.json()["detail"]),
            (400, "label_project_mismatch"),
        )

    async def test_cannot_manage_or_attach_labels_in_archived_project(self):
        label = await self.make_label("alice")
        task = await self.make_task("alice")
        attach_url = f"{TASK_API}{task['id']}/labels/{label['id']}"
        self.assertEqual((await self.call("POST", attach_url, "alice")).status_code, 204)

        async with self.sessions() as session:
            await session.execute(
                update(Project)
                .where(Project.id == self.p1)
                .values(status=ProjectStatus.ARCHIVED)
            )
            await session.commit()

        # VIEWER receives 403 before 400 archived check (404 -> 403 -> 400)
        for method, path, payload in (
            ("POST", API, {"project_id": self.p1, "name": "v"}),
            ("PATCH", f"{API}{label['id']}", {"name": "v"}),
            ("DELETE", f"{API}{label['id']}", None),
            ("POST", attach_url, None),
            ("DELETE", attach_url, None),
        ):
            kw = {"json": payload} if payload is not None else {}
            v_res = await self.call(method, path, "carol", **kw)
            self.assertEqual(v_res.status_code, 403, (method, path))

        # OWNER receives 400 project_archived
        for method, path, payload in (
            ("POST", API, {"project_id": self.p1, "name": "archived"}),
            ("PATCH", f"{API}{label['id']}", {"name": "archived"}),
            ("DELETE", f"{API}{label['id']}", None),
            ("POST", attach_url, None),
            ("DELETE", attach_url, None),
        ):
            kw = {"json": payload} if payload is not None else {}
            o_res = await self.call(method, path, "alice", **kw)
            self.assertEqual(
                (o_res.status_code, o_res.json()["detail"]),
                (400, "project_archived"),
                (method, path),
            )

        # Unarchive project -> operations succeed, cascade delete cleans up labels
        unarchive = await self.call(
            "PATCH", f"/api/v1/projects/{self.p1}", "alice", json={"status": "ACTIVE"}
        )
        self.assertEqual(unarchive.status_code, 200)
        self.assertEqual(
            (
                await self.call(
                    "PATCH", f"{API}{label['id']}", "alice", json={"name": "Restored"}
                )
            ).status_code,
            200,
        )
        self.assertEqual(
            (await self.call("DELETE", f"/api/v1/projects/{self.p1}", "alice")).status_code,
            204,
        )
        self.assertEqual(
            (await self.call("GET", f"{API}{label['id']}", "alice")).status_code,
            404,
        )

    async def test_duplicate_label_name_in_same_project_returns_409(self):
        # Create first label
        res1 = await self.call(
            "POST", API, "alice", json={"project_id": self.p1, "name": "Bug"}
        )
        self.assertEqual(res1.status_code, 201)
        label1_id = res1.json()["id"]

        # Duplicate create in same project -> 409
        dup_create = await self.call(
            "POST", API, "alice", json={"project_id": self.p1, "name": "Bug"}
        )
        self.assertEqual(
            (dup_create.status_code, dup_create.json()["detail"]),
            (409, "label_name_exists"),
        )

        # Create second label with different name
        res2 = await self.call(
            "POST", API, "alice", json={"project_id": self.p1, "name": "Feature"}
        )
        self.assertEqual(res2.status_code, 201)
        label2_id = res2.json()["id"]

        # Rename to duplicate -> 409
        dup_rename = await self.call(
            "PATCH", f"{API}{label2_id}", "alice", json={"name": "Bug"}
        )
        self.assertEqual(
            (dup_rename.status_code, dup_rename.json()["detail"]),
            (409, "label_name_exists"),
        )

        # Same name in a different project -> 201 (scoped to project)
        other_proj_create = await self.call(
            "POST", API, "alice", json={"project_id": self.p1_other, "name": "Bug"}
        )
        self.assertEqual(other_proj_create.status_code, 201)

    async def test_task_labels_read_back_and_cascade_delete(self):
        task = await self.make_task("alice")
        label = await self.make_label("alice", project_id=self.p1, name="Frontend")
        task_url = f"{TASK_API}{task['id']}"
        attach_url = f"{task_url}/labels/{label['id']}"

        # Initial task read-back has empty labels
        init_task = (await self.call("GET", task_url, "alice")).json()
        self.assertEqual(init_task["labels"], [])

        # Attach label
        self.assertEqual((await self.call("POST", attach_url, "alice")).status_code, 204)

        # Task read-back includes attached label
        with_label = (await self.call("GET", task_url, "alice")).json()
        self.assertEqual(len(with_label["labels"]), 1)
        self.assertEqual(with_label["labels"][0]["id"], label["id"])
        self.assertEqual(with_label["labels"][0]["name"], "Frontend")

        # Detach label
        self.assertEqual((await self.call("DELETE", attach_url, "alice")).status_code, 204)

        # Task read-back has empty labels again
        after_detach = (await self.call("GET", task_url, "alice")).json()
        self.assertEqual(after_detach["labels"], [])

        # Re-attach and test delete label cascades to task_labels
        self.assertEqual((await self.call("POST", attach_url, "alice")).status_code, 204)
        del_label = await self.call("DELETE", f"{API}{label['id']}", "alice")
        self.assertEqual(del_label.status_code, 204)

        # Task read-back reflects deleted label
        after_del_label = (await self.call("GET", task_url, "alice")).json()
        self.assertEqual(after_del_label["labels"], [])

        # Direct DB check on task_labels
        async with self.sessions() as session:
            count = (
                await session.scalars(
                    select(TaskLabel).where(TaskLabel.label_id == label["id"])
                )
            ).all()
            self.assertEqual(len(count), 0)

    async def test_label_validation_blank_name_and_invalid_color(self):
        # Blank name -> 422
        res_blank = await self.call(
            "POST", API, "alice", json={"project_id": self.p1, "name": "   "}
        )
        self.assertEqual(res_blank.status_code, 422)

        # Invalid hex color -> 422
        res_bad_color = await self.call(
            "POST",
            API,
            "alice",
            json={"project_id": self.p1, "name": "Test", "color": "blue"},
        )
        self.assertEqual(res_bad_color.status_code, 422)

        # Invalid project_id (<= 0) -> 422
        res_bad_proj = await self.call(
            "POST", API, "alice", json={"project_id": 0, "name": "Test"}
        )
        self.assertEqual(res_bad_proj.status_code, 422)
