"""Authorization / RBAC / resource-ownership tests for the task endpoints.

Run with: python -m unittest discover -s tests -v
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.cache import (
    TASK_LIST_CACHE_PREFIX,
    RedisCache,
    TaskListCacheInvalidator,
    workspace_version_key,
)
from app.core.database import get_db
from app.core.security import create_token, read_key
from app.main import app
from app.models import Project, User, Workspace, WorkspaceMember
from app.models.enums import ProjectStatus, TokenType, UserRole, WorkspaceRole
from app.repositories.task import TaskRepository
from app.repositories.user import UserRepository
from app.services.user import UserService

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
        read_key.cache_clear()
        self.addCleanup(read_key.cache_clear)

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
                name: create_token(user.id, user.role.value, TokenType.ACCESS)[0]
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
            self.ws1 = ws1.id
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
        bad_viewer = await self.call(
            "PATCH", f"{API}{task['id']}", "alice", json={"assignee_id": self.uid["carol"]})
        self.assertEqual((bad_viewer.status_code, bad_viewer.json()["detail"]), (400, "assignee_invalid_role"))
        good = await self.call(
            "PATCH", f"{API}{task['id']}", "alice", json={"assignee_id": self.uid["bob"]})
        self.assertEqual((good.status_code, good.json()["assignee_id"]), (200, self.uid["bob"]))

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

    def install_task_cache(self):
        cache = RedisCache("redis://localhost:6379/0", 60)
        self.addAsyncCleanup(cache.close)
        values: dict[str, bytes] = {}
        state = {"offline": False}
        test_case = self

        class FakePipeline:
            def __init__(self) -> None:
                self._ops: list[tuple] = []

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            def set(
                self,
                key: str,
                payload: str,
                *,
                nx: bool = False,
                ex: int | None = None,
            ):
                self._ops.append(("set", key, payload, nx, ex))
                return self

            def mget(self, keys):
                self._ops.append(("mget", list(keys)))
                return self

            async def execute(self):
                if state["offline"]:
                    raise RedisConnectionError("offline")
                results = []
                for op in self._ops:
                    if op[0] == "set":
                        _, key, payload, nx, ex = op
                        test_case.assertIsNotNone(ex)
                        if not nx or key not in values:
                            values[key] = payload.encode()
                            results.append(True)
                        else:
                            results.append(False)
                    elif op[0] == "mget":
                        results.append([values.get(k) for k in op[1]])
                return results

        redis = AsyncMock(wraps=cache.client)

        def mget_values(keys):
            if state["offline"]:
                raise RedisConnectionError("offline")
            return [values.get(k) for k in keys]

        def set_value(key, payload, *, ex):
            if state["offline"]:
                raise RedisConnectionError("offline")
            values[key] = payload.encode()
            self.assertEqual(ex, 60)

        redis.mget.side_effect = mget_values
        redis.set.side_effect = set_value
        redis.pipeline = MagicMock(side_effect=lambda transaction=False: FakePipeline())
        cache.client = redis
        patcher = patch.object(app.state, "cache", cache, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        return redis, values, state

    async def assert_cache_warm(self, query: str, user: str) -> dict:
        first = await self.call("GET", query, user)
        self.assertEqual(first.status_code, 200, first.text)
        body = first.json()
        return await self.assert_cache_hit(query, user, expected=body)

    async def assert_cache_hit(
        self, query: str, user: str, expected: dict | None = None
    ) -> dict:
        with patch.object(
            TaskRepository, "list_visible", side_effect=AssertionError("cache miss")
        ):
            res = await self.call("GET", query, user)
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        if expected is not None:
            self.assertEqual(body, expected)
        return body

    async def test_task_list_cache_reuses_pages_isolates_users_and_workspaces(self):
        redis, values, _ = self.install_task_cache()
        visible = await self.make_task("alice")
        hidden = await self.make_task("dave", project=self.p2)
        query = f"{API}?project_id={self.p1}&limit=1"
        first = await self.assert_cache_warm(query, "carol")
        self.assertEqual(first["items"][0]["id"], visible["id"])
        redis.set.assert_awaited_once()

        second = await self.call("GET", query + "&page=2", "carol")
        self.assertEqual(second.json(), {"items": [], "total": 1})
        other = await self.call("GET", query, "dave")
        self.assertEqual(other.json(), {"items": [], "total": 0})
        unfiltered = await self.call("GET", f"{API}?limit=1", "dave")
        self.assertEqual(unfiltered.json()["items"][0]["id"], hidden["id"])
        page_keys = [k for k in values if k.startswith(TASK_LIST_CACHE_PREFIX)]
        self.assertEqual(len(page_keys), 4)

        # Corrupted JSON payload recovers from DB and rewrites cache
        key = redis.mget.await_args_list[0].args[0][0]
        values[key] = b"invalid JSON"
        recovered = await self.call("GET", query, "carol")
        self.assertEqual(recovered.json(), first)
        self.assertNotEqual(values[key], b"invalid JSON")

        # Cross-workspace isolation: mutating ws1 must not evict dave's ws2 cache
        await self.assert_cache_warm(API, "carol")
        dave_before = await self.assert_cache_warm(API, "dave")
        patch_ws1 = await self.call(
            "PATCH", f"{API}{visible['id']}", "alice", json={"title": "WS1 Updated"}
        )
        self.assertEqual(patch_ws1.status_code, 200)
        carol_after = await self.call("GET", API, "carol")
        self.assertEqual(carol_after.json()["items"][0]["title"], "WS1 Updated")
        await self.assert_cache_hit(API, "dave", expected=dave_before)

        # Evicted version key safely triggers cache miss and re-warms cache
        values.pop(workspace_version_key(self.ws1))
        after_evict = await self.call("GET", API, "carol")
        self.assertEqual(after_evict.status_code, 200)
        self.assertEqual(after_evict.json()["items"][0]["title"], "WS1 Updated")
        self.assertIn(workspace_version_key(self.ws1), values)
        await self.assert_cache_hit(API, "carol", expected=after_evict.json())

    async def test_warm_cache_invalidated_by_task_and_label_mutations(self):
        self.install_task_cache()

        with self.subTest("create_task"):
            self.assertEqual(
                await self.assert_cache_warm(API, "carol"), {"items": [], "total": 0}
            )
            self.assertEqual(
                await self.assert_cache_warm(API, "root"), {"items": [], "total": 0}
            )
            task1 = await self.make_task("alice", title="T1")
            self.assertEqual(
                (await self.call("GET", API, "carol")).json()["items"][0]["title"],
                "T1",
            )
            self.assertEqual(
                (await self.call("GET", API, "root")).json()["items"][0]["title"],
                "T1",
            )

        with self.subTest("update_task"):
            await self.assert_cache_warm(API, "carol")
            await self.assert_cache_warm(API, "root")
            upd = await self.call(
                "PATCH", f"{API}{task1['id']}", "alice", json={"title": "T1-Edited"}
            )
            self.assertEqual(upd.status_code, 200)
            self.assertEqual(
                (await self.call("GET", API, "carol")).json()["items"][0]["title"],
                "T1-Edited",
            )
            self.assertEqual(
                (await self.call("GET", API, "root")).json()["items"][0]["title"],
                "T1-Edited",
            )

        with self.subTest("attach_label_to_task"):
            label_res = await self.call(
                "POST",
                "/api/v1/labels/",
                "alice",
                json={"project_id": self.p1, "name": "Urgent"},
            )
            self.assertEqual(label_res.status_code, 201)
            label_id = label_res.json()["id"]
            # Warm cache AFTER creating label and immediately BEFORE attaching it
            warm_before_attach = await self.assert_cache_warm(API, "carol")
            self.assertEqual(warm_before_attach["items"][0]["labels"], [])
            attach = await self.call(
                "POST", f"{API}{task1['id']}/labels/{label_id}", "alice"
            )
            self.assertEqual(attach.status_code, 204)
            after_attach = (await self.call("GET", API, "carol")).json()
            self.assertEqual(
                [lbl["name"] for lbl in after_attach["items"][0]["labels"]],
                ["Urgent"],
            )

        with self.subTest("update_label"):
            await self.assert_cache_warm(API, "carol")
            upd_lbl = await self.call(
                "PATCH", f"/api/v1/labels/{label_id}", "alice", json={"name": "Critical"}
            )
            self.assertEqual(upd_lbl.status_code, 200)
            after_upd_lbl = (await self.call("GET", API, "carol")).json()
            self.assertEqual(
                [lbl["name"] for lbl in after_upd_lbl["items"][0]["labels"]],
                ["Critical"],
            )

        with self.subTest("detach_label_from_task"):
            await self.assert_cache_warm(API, "carol")
            detach = await self.call(
                "DELETE", f"{API}{task1['id']}/labels/{label_id}", "alice"
            )
            self.assertEqual(detach.status_code, 204)
            after_detach = (await self.call("GET", API, "carol")).json()
            self.assertEqual(after_detach["items"][0]["labels"], [])

        with self.subTest("delete_label"):
            reattach = await self.call(
                "POST", f"{API}{task1['id']}/labels/{label_id}", "alice"
            )
            self.assertEqual(reattach.status_code, 204)
            warm_before_del_lbl = await self.assert_cache_warm(API, "carol")
            self.assertEqual(
                [lbl["name"] for lbl in warm_before_del_lbl["items"][0]["labels"]],
                ["Critical"],
            )
            del_lbl = await self.call("DELETE", f"/api/v1/labels/{label_id}", "alice")
            self.assertEqual(del_lbl.status_code, 204)
            after_del_lbl = (await self.call("GET", API, "carol")).json()
            self.assertEqual(after_del_lbl["items"][0]["labels"], [])

        with self.subTest("delete_task"):
            await self.assert_cache_warm(API, "carol")
            await self.assert_cache_warm(API, "root")
            del_task = await self.call("DELETE", f"{API}{task1['id']}", "alice")
            self.assertEqual(del_task.status_code, 204)
            self.assertEqual(
                (await self.call("GET", API, "carol")).json(), {"items": [], "total": 0}
            )
            self.assertEqual(
                (await self.call("GET", API, "root")).json(), {"items": [], "total": 0}
            )

    async def test_warm_cache_invalidated_by_membership_project_workspace_and_user_mutations(self):
        self.install_task_cache()
        ws_api = "/api/v1/workspaces/"

        with self.subTest("update_member_role"):
            await self.make_task("alice", assignee_id=self.uid["bob"])
            warm_carol = await self.assert_cache_warm(API, "carol")
            self.assertEqual(warm_carol["items"][0]["assignee_id"], self.uid["bob"])
            warm_root = await self.assert_cache_warm(API, "root")
            self.assertEqual(warm_root["items"][0]["assignee_id"], self.uid["bob"])
            demote = await self.call(
                "PATCH",
                f"{ws_api}{self.ws1}/members/{self.uid['bob']}",
                "alice",
                json={"role": "VIEWER"},
            )
            self.assertEqual(demote.status_code, 200)
            self.assertIsNone(
                (await self.call("GET", API, "carol")).json()["items"][0]["assignee_id"]
            )
            self.assertIsNone(
                (await self.call("GET", API, "root")).json()["items"][0]["assignee_id"]
            )

        with self.subTest("delete_user"):
            task_erin = await self.make_task("alice", assignee_id=self.uid["erin"])
            warm_alice = await self.assert_cache_warm(f"{API}?limit=20", "alice")
            warm_by_id = {item["id"]: item for item in warm_alice["items"]}
            self.assertEqual(
                warm_by_id[task_erin["id"]]["assignee_id"], self.uid["erin"]
            )
            async with self.sessions() as session:
                root_user = await session.get(User, self.uid["root"])
                self.assertIsNotNone(root_user)
                await UserService(
                    UserRepository(session),
                    task_cache_invalidator=TaskListCacheInvalidator(app.state.cache),
                ).delete_user(self.uid["erin"], root_user)
            after_del_user = (await self.call("GET", f"{API}?limit=20", "alice")).json()
            after_by_id = {item["id"]: item for item in after_del_user["items"]}
            self.assertIsNone(after_by_id[task_erin["id"]]["assignee_id"])

        with self.subTest("add_member"):
            dave_query = f"{API}?project_id={self.p1}"
            self.assertEqual((await self.assert_cache_warm(dave_query, "dave"))["total"], 0)
            add_res = await self.call(
                "POST",
                f"{ws_api}{self.ws1}/members",
                "alice",
                json={"user_id": self.uid["dave"], "role": "VIEWER"},
            )
            self.assertEqual(add_res.status_code, 201)
            self.assertEqual((await self.call("GET", dave_query, "dave")).json()["total"], 2)

        with self.subTest("remove_member"):
            self.assertEqual((await self.assert_cache_warm(API, "carol"))["total"], 2)
            rem_res = await self.call(
                "DELETE", f"{ws_api}{self.ws1}/members/{self.uid['carol']}", "alice"
            )
            self.assertEqual(rem_res.status_code, 204)
            self.assertEqual(
                (await self.call("GET", API, "carol")).json(), {"items": [], "total": 0}
            )

        with self.subTest("delete_project"):
            p_extra = await self.call(
                "POST",
                "/api/v1/projects/",
                "alice",
                json={"workspace_id": self.ws1, "name": "Extra"},
            )
            self.assertEqual(p_extra.status_code, 201)
            p_extra_id = p_extra.json()["id"]
            await self.make_task("alice", project=p_extra_id)
            p_extra_query = f"{API}?project_id={p_extra_id}"
            self.assertEqual(
                (await self.assert_cache_warm(p_extra_query, "alice"))["total"], 1
            )
            del_proj = await self.call(
                "DELETE", f"/api/v1/projects/{p_extra_id}", "alice"
            )
            self.assertEqual(del_proj.status_code, 204)
            self.assertEqual(
                (await self.call("GET", p_extra_query, "alice")).json(),
                {"items": [], "total": 0},
            )

        with self.subTest("delete_workspace"):
            self.assertEqual((await self.assert_cache_warm(API, "alice"))["total"], 2)
            self.assertEqual((await self.assert_cache_warm(API, "root"))["total"], 2)
            del_ws = await self.call("DELETE", f"{ws_api}{self.ws1}", "alice")
            self.assertEqual(del_ws.status_code, 204)
            self.assertEqual(
                (await self.call("GET", API, "alice")).json(), {"items": [], "total": 0}
            )
            self.assertEqual((await self.call("GET", API, "root")).json()["total"], 0)

        with self.subTest("create_workspace"):
            self.assertEqual(
                await self.assert_cache_warm(API, "carol"), {"items": [], "total": 0}
            )
            ws_new = await self.call("POST", ws_api, "carol", json={"name": "Carol WS"})
            self.assertEqual(ws_new.status_code, 201)
            p_new = await self.call(
                "POST",
                "/api/v1/projects/",
                "carol",
                json={"workspace_id": ws_new.json()["id"], "name": "Carol P"},
            )
            self.assertEqual(p_new.status_code, 201)
            t_new = await self.make_task("carol", project=p_new.json()["id"])
            after_ws = (await self.call("GET", API, "carol")).json()
            self.assertEqual(after_ws["total"], 1)
            self.assertEqual(after_ws["items"][0]["id"], t_new["id"])

    async def test_task_list_cache_fail_open_and_disabled_noop(self):
        with self.subTest("cache_disabled_noop"):
            with patch.object(app.state, "cache", None, create=True):
                t_no_cache = await self.make_task("alice")
                listed = await self.call("GET", API, "carol")
                self.assertEqual((listed.status_code, listed.json()["total"]), (200, 1))
                patched = await self.call(
                    "PATCH",
                    f"{API}{t_no_cache['id']}",
                    "alice",
                    json={"title": "NoCache"},
                )
                self.assertEqual(
                    (patched.status_code, patched.json()["title"]), (200, "NoCache")
                )
                self.assertEqual(
                    (await self.call("DELETE", f"{API}{t_no_cache['id']}", "alice")).status_code,
                    204,
                )
                self.assertEqual((await self.call("GET", API, "carol")).json()["total"], 0)

        with self.subTest("redis_offline_fail_open"):
            _, _, state = self.install_task_cache()
            task = await self.make_task("alice")
            await self.assert_cache_warm(API, "carol")
            state["offline"] = True

            with self.assertLogs("app.core.cache", level="WARNING"):
                updated = await self.call(
                    "PATCH", f"{API}{task['id']}", "alice", json={"title": "Offline Updated"}
                )
            self.assertEqual(updated.status_code, 200)
            with self.assertLogs("app.core.cache", level="WARNING"):
                fallback = await self.call("GET", API, "carol")
            self.assertEqual(fallback.status_code, 200)
            self.assertEqual(fallback.json()["items"][0]["title"], "Offline Updated")

            state["offline"] = False
            self.assertEqual(
                (
                    await self.call(
                        "PATCH", f"{API}{task['id']}", "alice", json={"title": "Recovered"}
                    )
                ).status_code,
                200,
            )
            recovered = await self.call("GET", API, "carol")
            self.assertEqual(recovered.json()["items"][0]["title"], "Recovered")
            await self.assert_cache_hit(API, "carol", expected=recovered.json())

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

    async def test_task_description_and_filtering_by_project(self):
        task = await self.make_task("alice", description="Detailed description")
        self.assertEqual(task["description"], "Detailed description")
        patch_res = await self.call(
            "PATCH", f"{API}{task['id']}", "alice", json={"description": "Updated description"}
        )
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.json()["description"], "Updated description")

        res_p1 = await self.call("GET", f"{API}?project_id={self.p1}", "alice")
        self.assertEqual(res_p1.status_code, 200)
        self.assertTrue(all(t["project_id"] == self.p1 for t in res_p1.json()["items"]))

        res_p2 = await self.call("GET", f"{API}?project_id={self.p2}", "alice")
        self.assertEqual(res_p2.status_code, 200)
        self.assertEqual(res_p2.json()["total"], 0)

    async def test_cannot_create_or_modify_task_in_archived_project(self):
        task = await self.make_task("alice")
        from sqlalchemy import update
        async with self.sessions() as session:
            await session.execute(
                update(Project).where(Project.id == self.p1).values(status=ProjectStatus.ARCHIVED)
            )
            await session.commit()

        # VIEWER receives 403 before archived check (404 -> 403 -> 400)
        for method, path, payload in (
            ("POST", API, {"title": "v", "project_id": self.p1}),
            ("PATCH", f"{API}{task['id']}", {"title": "v"}),
            ("DELETE", f"{API}{task['id']}", None),
        ):
            kw = {"json": payload} if payload is not None else {}
            v_res = await self.call(method, path, "carol", **kw)
            self.assertEqual(v_res.status_code, 403, method)

        # OWNER receives 400 project_archived for create, update, and delete
        res = await self.call("POST", API, "alice", json={"title": "archived task", "project_id": self.p1})
        self.assertEqual((res.status_code, res.json()["detail"]), (400, "project_archived"))
        patch_res = await self.call("PATCH", f"{API}{task['id']}", "alice", json={"title": "new title"})
        self.assertEqual((patch_res.status_code, patch_res.json()["detail"]), (400, "project_archived"))
        del_res = await self.call("DELETE", f"{API}{task['id']}", "alice")
        self.assertEqual((del_res.status_code, del_res.json()["detail"]), (400, "project_archived"))

        # Unarchive project via PATCH /api/v1/projects/{id}, then update and delete succeed
        unarchive_res = await self.call(
            "PATCH", f"/api/v1/projects/{self.p1}", "alice", json={"status": "ACTIVE"}
        )
        self.assertEqual(unarchive_res.status_code, 200)
        ok_patch = await self.call("PATCH", f"{API}{task['id']}", "alice", json={"title": "restored"})
        self.assertEqual((ok_patch.status_code, ok_patch.json()["title"]), (200, "restored"))
        ok_del = await self.call("DELETE", f"{API}{task['id']}", "alice")
        self.assertEqual(ok_del.status_code, 204)

    async def test_assignee_cannot_be_inactive_user(self):
        from sqlalchemy import update
        async with self.sessions() as session:
            await session.execute(
                update(User).where(User.id == self.uid["bob"]).values(is_active=False)
            )
            await session.commit()
        res = await self.call("POST", API, "alice", json={
            "title": "task for inactive", "project_id": self.p1, "assignee_id": self.uid["bob"]
        })
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["detail"], "assignee_inactive")

    async def test_unassign_tasks_when_member_removed_or_demoted(self):
        task_erin = await self.make_task("alice", assignee_id=self.uid["erin"])
        task_bob = await self.make_task("alice", assignee_id=self.uid["bob"])
        self.assertEqual(task_erin["assignee_id"], self.uid["erin"])
        self.assertEqual(task_bob["assignee_id"], self.uid["bob"])

        ws_api = "/api/v1/workspaces/"
        # Demote bob EDITOR -> VIEWER -> task_bob is unassigned
        demote_res = await self.call(
            "PATCH", f"{ws_api}{self.ws1}/members/{self.uid['bob']}", "alice", json={"role": "VIEWER"}
        )
        self.assertEqual(demote_res.status_code, 200)
        get_bob_task = await self.call("GET", f"{API}{task_bob['id']}", "alice")
        self.assertEqual(get_bob_task.status_code, 200)
        self.assertIsNone(get_bob_task.json()["assignee_id"])

        # erin leaves workspace by themselves -> task_erin is unassigned
        leave_res = await self.call(
            "DELETE", f"{ws_api}{self.ws1}/members/{self.uid['erin']}", "erin"
        )
        self.assertEqual(leave_res.status_code, 204)
        get_erin_task = await self.call("GET", f"{API}{task_erin['id']}", "alice")
        self.assertEqual(get_erin_task.status_code, 200)
        self.assertIsNone(get_erin_task.json()["assignee_id"])

        # Owner removes remaining member (carol)
        del_res = await self.call(
            "DELETE", f"{ws_api}{self.ws1}/members/{self.uid['carol']}", "alice"
        )
        self.assertEqual(del_res.status_code, 204)


if __name__ == "__main__":
    unittest.main()

