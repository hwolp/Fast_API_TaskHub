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
from app.models import Comment, Project, User, Workspace, WorkspaceMember
from app.models.enums import ProjectStatus, TokenType, UserRole, WorkspaceRole

ROOT = Path(__file__).resolve().parents[1]
API = "/api/v1/comments/"
TASK_API = "/api/v1/tasks/"


class CommentTests(unittest.IsolatedAsyncioTestCase):
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

        url = "sqlite+aiosqlite:///" + (base / "comment.db").as_posix()
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
            p2 = Project(workspace_id=ws2.id, name="P2")
            session.add_all([p1, p2])
            await session.flush()
            self.ws1 = ws1.id
            self.p1 = p1.id
            self.p2 = p2.id
            await session.commit()

    def call(self, method: str, path: str, user: str | None = None, **kwargs):
        headers = {"Authorization": f"Bearer {self.tokens[user]}"} if user else {}
        return self.client.request(method, path, headers=headers, **kwargs)

    async def make_task(self, user: str = "alice", project_id: int | None = None):
        res = await self.call(
            "POST",
            TASK_API,
            user,
            json={"project_id": project_id or self.p1, "title": "Task"},
        )
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()

    async def make_comment(
        self, user: str = "bob", task_id: int | None = None, content: str = "Hello"
    ):
        res = await self.call(
            "POST", API, user, json={"task_id": task_id, "content": content}
        )
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()

    async def test_every_comment_endpoint_requires_authentication(self):
        for method, path in (
            ("POST", API),
            ("GET", API),
            ("GET", f"{API}1"),
            ("PATCH", f"{API}1"),
            ("DELETE", f"{API}1"),
        ):
            res = await self.call(method, path, json={"task_id": 1, "content": "x"})
            self.assertEqual(res.status_code, 401, (method, path))
            self.assertEqual(res.json()["detail"], "token_missing")

    async def test_comment_crud_and_rbac(self):
        task = await self.make_task("alice")
        comment = await self.make_comment("bob", task_id=task["id"], content="Initial")
        self.assertEqual(comment["author_id"], self.uid["bob"])
        self.assertEqual(comment["task_id"], task["id"])
        self.assertEqual(comment["content"], "Initial")

        # VIEWER can read, but cannot create, update, or delete
        self.assertEqual(
            (await self.call("GET", f"{API}{comment['id']}", "carol")).status_code, 200
        )
        self.assertEqual(
            (
                await self.call(
                    "POST", API, "carol", json={"task_id": task["id"], "content": "No"}
                )
            ).status_code,
            403,
        )
        self.assertEqual(
            (
                await self.call(
                    "PATCH", f"{API}{comment['id']}", "carol", json={"content": "No"}
                )
            ).status_code,
            403,
        )
        self.assertEqual(
            (await self.call("DELETE", f"{API}{comment['id']}", "carol")).status_code,
            403,
        )

        # Non-member receives 404 (IDOR protection)
        create_idor = await self.call(
            "POST", API, "dave", json={"task_id": task["id"], "content": "Leak"}
        )
        self.assertEqual(
            (create_idor.status_code, create_idor.json()["detail"]),
            (404, "task_not_found"),
        )
        for method, kw in (
            ("GET", {}),
            ("PATCH", {"json": {"content": "Leak"}}),
            ("DELETE", {}),
        ):
            r = await self.call(method, f"{API}{comment['id']}", "dave", **kw)
            self.assertEqual(
                (r.status_code, r.json()["detail"]), (404, "comment_not_found"), method
            )

        # Reject null for content
        bad_null = await self.call(
            "PATCH", f"{API}{comment['id']}", "bob", json={"content": None}
        )
        self.assertEqual(bad_null.status_code, 422)

        # Only the author (with write role) can modify a comment
        self.assertEqual(
            (
                await self.call(
                    "PATCH", f"{API}{comment['id']}", "erin", json={"content": "Hack"}
                )
            ).status_code,
            403,
        )
        self.assertEqual(
            (
                await self.call(
                    "PATCH", f"{API}{comment['id']}", "alice", json={"content": "OwnerEdit"}
                )
            ).status_code,
            403,
        )
        ok_edit = await self.call(
            "PATCH", f"{API}{comment['id']}", "bob", json={"content": "Edited by author"}
        )
        self.assertEqual(ok_edit.status_code, 200)
        self.assertEqual(ok_edit.json()["content"], "Edited by author")

        # Delete rules: other EDITOR cannot delete, author / OWNER / ADMIN can delete
        self.assertEqual(
            (await self.call("DELETE", f"{API}{comment['id']}", "erin")).status_code,
            403,
        )
        self.assertEqual(
            (await self.call("DELETE", f"{API}{comment['id']}", "bob")).status_code,
            204,
        )

        c2 = await self.make_comment("bob", task_id=task["id"], content="Owner will delete")
        self.assertEqual(
            (await self.call("DELETE", f"{API}{c2['id']}", "alice")).status_code, 204
        )

    async def test_list_comments_filtering_and_pagination(self):
        t1 = await self.make_task("alice")
        t2 = await self.make_task("alice")
        t_dave = await self.make_task("dave", project_id=self.p2)

        for i in range(3):
            await self.make_comment("bob", task_id=t1["id"], content=f"C{i}")
        await self.make_comment("alice", task_id=t2["id"], content="OtherTask")
        await self.make_comment("dave", task_id=t_dave["id"], content="DaveComment")

        res_carol = await self.call("GET", API, "carol")
        self.assertEqual(res_carol.status_code, 200)
        self.assertEqual(res_carol.json()["total"], 4)

        res_t1 = await self.call("GET", f"{API}?task_id={t1['id']}", "carol")
        self.assertEqual(res_t1.status_code, 200)
        self.assertEqual(res_t1.json()["total"], 3)
        self.assertTrue(
            all(item["task_id"] == t1["id"] for item in res_t1.json()["items"])
        )

        res_page = await self.call(
            "GET", f"{API}?task_id={t1['id']}&page=2&limit=2", "carol"
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

    async def test_cannot_create_or_modify_comments_in_archived_project(self):
        task = await self.make_task("alice")
        comment = await self.make_comment("bob", task_id=task["id"], content="Before archive")

        async with self.sessions() as session:
            await session.execute(
                update(Project)
                .where(Project.id == self.p1)
                .values(status=ProjectStatus.ARCHIVED)
            )
            await session.commit()

        # VIEWER receives 403 before 400 archived check (404 -> 403 -> 400)
        for method, path, payload in (
            ("POST", API, {"task_id": task["id"], "content": "v"}),
            ("PATCH", f"{API}{comment['id']}", {"content": "v"}),
            ("DELETE", f"{API}{comment['id']}", None),
        ):
            kw = {"json": payload} if payload is not None else {}
            v_res = await self.call(method, path, "carol", **kw)
            self.assertEqual(v_res.status_code, 403, (method, path))

        # Authorized user receives 400 project_archived
        for method, path, payload in (
            ("POST", API, {"task_id": task["id"], "content": "archived"}),
            ("PATCH", f"{API}{comment['id']}", {"content": "archived"}),
            ("DELETE", f"{API}{comment['id']}", None),
        ):
            kw = {"json": payload} if payload is not None else {}
            b_res = await self.call(method, path, "bob", **kw)
            self.assertEqual(
                (b_res.status_code, b_res.json()["detail"]),
                (400, "project_archived"),
                (method, path),
            )

        # Unarchive project -> update and cascade delete work
        unarchive = await self.call(
            "PATCH", f"/api/v1/projects/{self.p1}", "alice", json={"status": "ACTIVE"}
        )
        self.assertEqual(unarchive.status_code, 200)
        self.assertEqual(
            (
                await self.call(
                    "PATCH", f"{API}{comment['id']}", "bob", json={"content": "Restored"}
                )
            ).status_code,
            200,
        )
        self.assertEqual(
            (await self.call("DELETE", f"{TASK_API}{task['id']}", "alice")).status_code,
            204,
        )
        self.assertEqual(
            (await self.call("GET", f"{API}{comment['id']}", "alice")).status_code,
            404,
        )

    async def test_comment_validation_and_blank_content(self):
        task = await self.make_task("alice")

        # Whitespace-only content -> 422
        res_ws = await self.call(
            "POST", API, "alice", json={"task_id": task["id"], "content": "   "}
        )
        self.assertEqual(res_ws.status_code, 422)

        # Empty content -> 422
        res_empty = await self.call(
            "POST", API, "alice", json={"task_id": task["id"], "content": ""}
        )
        self.assertEqual(res_empty.status_code, 422)

        # Invalid task_id (<= 0) -> 422
        res_bad_task = await self.call(
            "POST", API, "alice", json={"task_id": 0, "content": "Valid"}
        )
        self.assertEqual(res_bad_task.status_code, 422)

        # Valid create then whitespace-only update -> 422
        comment = await self.make_comment("alice", task_id=task["id"], content="Valid")
        res_update_ws = await self.call(
            "PATCH", f"{API}{comment['id']}", "alice", json={"content": " \t\n "}
        )
        self.assertEqual(res_update_ws.status_code, 422)

    async def test_comment_rbac_demoted_viewer_and_removed_member(self):
        task = await self.make_task("alice")
        comment = await self.make_comment("bob", task_id=task["id"], content="Bob comment")

        # Demote Bob to VIEWER
        demote_res = await self.call(
            "PATCH",
            f"/api/v1/workspaces/{self.ws1}/members/{self.uid['bob']}",
            "alice",
            json={"role": "VIEWER"},
        )
        self.assertEqual(demote_res.status_code, 200)

        # Demoted VIEWER cannot modify or delete own comment -> 403
        patch_res = await self.call(
            "PATCH", f"{API}{comment['id']}", "bob", json={"content": "Hacked"}
        )
        self.assertEqual(patch_res.status_code, 403)
        del_res = await self.call("DELETE", f"{API}{comment['id']}", "bob")
        self.assertEqual(del_res.status_code, 403)

        # Remove Bob from workspace
        remove_res = await self.call(
            "DELETE",
            f"/api/v1/workspaces/{self.ws1}/members/{self.uid['bob']}",
            "alice",
        )
        self.assertEqual(remove_res.status_code, 204)

        # Non-member receives 404
        non_member_patch = await self.call(
            "PATCH", f"{API}{comment['id']}", "bob", json={"content": "Hacked"}
        )
        self.assertEqual(non_member_patch.status_code, 404)
        non_member_del = await self.call("DELETE", f"{API}{comment['id']}", "bob")
        self.assertEqual(non_member_del.status_code, 404)

        # OWNER can still delete the comment (moderation)
        owner_del = await self.call("DELETE", f"{API}{comment['id']}", "alice")
        self.assertEqual(owner_del.status_code, 204)
        self.assertEqual(
            (await self.call("GET", f"{API}{comment['id']}", "alice")).status_code,
            404,
        )

    async def test_delete_task_cascades_comments(self):
        task = await self.make_task("alice")
        c1 = await self.make_comment("alice", task_id=task["id"], content="C1")
        c2 = await self.make_comment("bob", task_id=task["id"], content="C2")

        # Delete task
        del_task = await self.call("DELETE", f"{TASK_API}{task['id']}", "alice")
        self.assertEqual(del_task.status_code, 204)

        # Both comments return 404 via API
        self.assertEqual((await self.call("GET", f"{API}{c1['id']}", "alice")).status_code, 404)
        self.assertEqual((await self.call("GET", f"{API}{c2['id']}", "alice")).status_code, 404)

        # Directly check database: comments for this task are deleted
        async with self.sessions() as session:
            rows = (
                await session.scalars(
                    select(Comment).where(Comment.task_id == task["id"])
                )
            ).all()
            self.assertEqual(len(rows), 0)
