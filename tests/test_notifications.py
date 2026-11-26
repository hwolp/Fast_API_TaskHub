from datetime import datetime, timezone
import os
from pathlib import Path
import smtplib
import ssl
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import (
    DEFAULT_SMTP_FROM_EMAIL,
    DEFAULT_SMTP_PORT,
    DEFAULT_SMTP_TIMEOUT_SECONDS,
    Settings,
    settings,
)
from app.core.database import get_db
from app.core.notifications import (
    LoggingAndSmtpTaskNotifier,
    TaskAssignedEvent,
    dispatch_task_assigned,
)
from app.core.security import create_token, read_key
from app.dependencies import get_task_assignment_notifier
from app.main import app
from app.models import Project, Task, User, Workspace, WorkspaceMember
from app.models.enums import ProjectStatus, TokenType, UserRole, WorkspaceRole

ROOT = Path(__file__).resolve().parents[1]
TASKS_API = "/api/v1/tasks/"


class RecordingNotifier:
    def __init__(self) -> None:
        self.events: list[TaskAssignedEvent] = []

    async def notify_task_assigned(self, event: TaskAssignedEvent) -> None:
        self.events.append(event)


class FailingNotifier:
    async def notify_task_assigned(self, event: TaskAssignedEvent) -> None:
        raise RuntimeError(f"SMTP outage for task {event.task_id}")


class TaskAssignmentNotificationTests(unittest.IsolatedAsyncioTestCase):
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

        url = "sqlite+aiosqlite:///" + (base / "notifications.db").as_posix()
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

        self.notifier = RecordingNotifier()
        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_task_assignment_notifier] = lambda: self.notifier
        self.addCleanup(app.dependency_overrides.clear)
        self.client = AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        )
        self.addAsyncCleanup(self.client.aclose)
        await self.seed()

    async def seed(self):
        async with self.sessions() as session:
            users = {
                name: User(
                    email=f"{name}@example.com",
                    full_name=name.title(),
                    hashed_password="not-a-real-hash",
                    role=UserRole.ADMIN if name == "root" else UserRole.MEMBER,
                    is_active=(name != "inactive"),
                )
                for name in ("alice", "bob", "carol", "dave", "inactive", "outsider", "root")
            }
            session.add_all(users.values())
            await session.flush()
            self.uid = {name: user.id for name, user in users.items()}
            self.urole = {name: user.role for name, user in users.items()}

            ws = Workspace(name="Engineering", owner_id=self.uid["alice"])
            session.add(ws)
            await session.flush()
            self.ws_id = ws.id

            session.add_all(
                [
                    WorkspaceMember(
                        workspace_id=ws.id,
                        user_id=self.uid["bob"],
                        role=WorkspaceRole.EDITOR,
                    ),
                    WorkspaceMember(
                        workspace_id=ws.id,
                        user_id=self.uid["carol"],
                        role=WorkspaceRole.EDITOR,
                    ),
                    WorkspaceMember(
                        workspace_id=ws.id,
                        user_id=self.uid["dave"],
                        role=WorkspaceRole.VIEWER,
                    ),
                    WorkspaceMember(
                        workspace_id=ws.id,
                        user_id=self.uid["inactive"],
                        role=WorkspaceRole.EDITOR,
                    ),
                ]
            )

            active_proj = Project(
                workspace_id=ws.id, name="Active API", status=ProjectStatus.ACTIVE
            )
            archived_proj = Project(
                workspace_id=ws.id, name="Archived API", status=ProjectStatus.ARCHIVED
            )
            session.add_all([active_proj, archived_proj])
            await session.flush()
            self.active_project_id = active_proj.id
            self.archived_project_id = archived_proj.id

            archived_task = Task(
                project_id=archived_proj.id,
                title="Frozen task",
                created_by=self.uid["alice"],
            )
            session.add(archived_task)
            await session.flush()
            self.archived_task_id = archived_task.id
            await session.commit()

    def headers(self, user_name: str) -> dict[str, str]:
        token, _ = create_token(
            self.uid[user_name], self.urole[user_name].value, TokenType.ACCESS
        )
        return {"Authorization": f"Bearer {token}"}

    async def test_create_task_with_assignee_dispatches_background_notification(self):
        due = "2026-12-01T17:00:00Z"
        response = await self.client.post(
            TASKS_API,
            headers=self.headers("alice"),
            json={
                "project_id": self.active_project_id,
                "title": "Build background notifications",
                "priority": "HIGH",
                "due_date": due,
                "assignee_id": self.uid["bob"],
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        task_id = response.json()["id"]

        self.assertEqual(len(self.notifier.events), 1)
        event = self.notifier.events[0]
        self.assertEqual(event.task_id, task_id)
        self.assertEqual(event.task_title, "Build background notifications")
        self.assertEqual(event.project_id, self.active_project_id)
        self.assertEqual(event.workspace_id, self.ws_id)
        self.assertEqual(event.assignee_id, self.uid["bob"])
        self.assertEqual(event.assignee_email, "bob@example.com")
        self.assertEqual(event.assignee_name, "Bob")
        self.assertEqual(event.assigned_by_id, self.uid["alice"])
        self.assertEqual(event.assigned_by_name, "Alice")
        self.assertEqual(event.priority, "HIGH")
        self.assertIsNotNone(event.due_date)

    async def test_admin_assigning_task_dispatches_notification(self):
        created = await self.client.post(
            TASKS_API,
            headers=self.headers("root"),
            json={
                "project_id": self.active_project_id,
                "title": "Admin assigned task",
                "assignee_id": self.uid["bob"],
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(len(self.notifier.events), 1)
        self.assertEqual(self.notifier.events[0].assigned_by_id, self.uid["root"])
        self.assertEqual(self.notifier.events[0].assigned_by_name, "Root")
        self.assertEqual(self.notifier.events[0].assignee_id, self.uid["bob"])

    async def test_create_task_unassigned_or_self_assigned_skips_notification(self):
        unassigned = await self.client.post(
            TASKS_API,
            headers=self.headers("alice"),
            json={"project_id": self.active_project_id, "title": "Unassigned task"},
        )
        self.assertEqual(unassigned.status_code, 201, unassigned.text)

        self_assigned = await self.client.post(
            TASKS_API,
            headers=self.headers("alice"),
            json={
                "project_id": self.active_project_id,
                "title": "Self assigned task",
                "assignee_id": self.uid["alice"],
            },
        )
        self.assertEqual(self_assigned.status_code, 201, self_assigned.text)
        self.assertEqual(self.notifier.events, [])

    async def test_update_task_assignment_transitions(self):
        created = await self.client.post(
            TASKS_API,
            headers=self.headers("alice"),
            json={"project_id": self.active_project_id, "title": "Track transitions"},
        )
        self.assertEqual(created.status_code, 201, created.text)
        task_id = created.json()["id"]
        self.assertEqual(self.notifier.events, [])

        # Assign unassigned task -> Bob notified.
        res = await self.client.patch(
            f"{TASKS_API}{task_id}",
            headers=self.headers("alice"),
            json={"assignee_id": self.uid["bob"]},
        )
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(len(self.notifier.events), 1)
        self.assertEqual(self.notifier.events[0].assignee_id, self.uid["bob"])

        # Update title without touching assignee -> no duplicate notification.
        res = await self.client.patch(
            f"{TASKS_API}{task_id}",
            headers=self.headers("alice"),
            json={"title": "Updated title"},
        )
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(len(self.notifier.events), 1)

        # Explicitly resend the same assignee -> no duplicate notification.
        res = await self.client.patch(
            f"{TASKS_API}{task_id}",
            headers=self.headers("alice"),
            json={"assignee_id": self.uid["bob"]},
        )
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(len(self.notifier.events), 1)

        # Reassign from Bob to Carol -> Carol notified.
        res = await self.client.patch(
            f"{TASKS_API}{task_id}",
            headers=self.headers("alice"),
            json={"assignee_id": self.uid["carol"]},
        )
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(len(self.notifier.events), 2)
        self.assertEqual(self.notifier.events[1].assignee_id, self.uid["carol"])
        self.assertEqual(self.notifier.events[1].assignee_email, "carol@example.com")

        # Self-reassign (Alice assigns to Alice) -> no notification.
        res = await self.client.patch(
            f"{TASKS_API}{task_id}",
            headers=self.headers("alice"),
            json={"assignee_id": self.uid["alice"]},
        )
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(len(self.notifier.events), 2)

        # Unassign -> no notification.
        res = await self.client.patch(
            f"{TASKS_API}{task_id}",
            headers=self.headers("alice"),
            json={"assignee_id": None},
        )
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(len(self.notifier.events), 2)

    async def test_failed_task_mutations_never_notify(self):
        # Seed a valid unassigned task (0 notifications) to verify failed PATCH paths.
        seed_res = await self.client.post(
            TASKS_API,
            headers=self.headers("alice"),
            json={"project_id": self.active_project_id, "title": "Base task"},
        )
        self.assertEqual(seed_res.status_code, 201, seed_res.text)
        task_id = seed_res.json()["id"]
        self.assertEqual(self.notifier.events, [])

        post_cases = [
            (
                "alice",
                {
                    "project_id": self.active_project_id,
                    "title": "Bad viewer assignee",
                    "assignee_id": self.uid["dave"],
                },
                400,
            ),
            (
                "alice",
                {
                    "project_id": self.active_project_id,
                    "title": "Bad outsider assignee",
                    "assignee_id": self.uid["outsider"],
                },
                400,
            ),
            (
                "alice",
                {
                    "project_id": self.active_project_id,
                    "title": "Inactive assignee",
                    "assignee_id": self.uid["inactive"],
                },
                400,
            ),
            (
                "dave",
                {
                    "project_id": self.active_project_id,
                    "title": "Forbidden create",
                    "assignee_id": self.uid["bob"],
                },
                403,
            ),
            (
                "alice",
                {
                    "project_id": 99999,
                    "title": "Missing project",
                    "assignee_id": self.uid["bob"],
                },
                404,
            ),
            (
                "alice",
                {
                    "project_id": self.archived_project_id,
                    "title": "Archived project task",
                    "assignee_id": self.uid["bob"],
                },
                400,
            ),
        ]
        for actor, payload, expected_status in post_cases:
            res = await self.client.post(
                TASKS_API, headers=self.headers(actor), json=payload
            )
            self.assertEqual(res.status_code, expected_status, res.text)

        patch_cases = [
            ("alice", task_id, {"assignee_id": self.uid["dave"]}, 400),
            ("alice", task_id, {"assignee_id": self.uid["outsider"]}, 400),
            ("alice", task_id, {"assignee_id": self.uid["inactive"]}, 400),
            ("dave", task_id, {"assignee_id": self.uid["bob"]}, 403),
            ("carol", task_id, {"assignee_id": self.uid["bob"]}, 403),
            ("alice", 99999, {"assignee_id": self.uid["bob"]}, 404),
            ("alice", self.archived_task_id, {"assignee_id": self.uid["bob"]}, 400),
        ]
        for actor, target_id, payload, expected_status in patch_cases:
            res = await self.client.patch(
                f"{TASKS_API}{target_id}", headers=self.headers(actor), json=payload
            )
            self.assertEqual(res.status_code, expected_status, res.text)

        self.assertEqual(self.notifier.events, [])

    async def test_notifier_failure_is_fail_open_and_logged(self):
        app.dependency_overrides[get_task_assignment_notifier] = lambda: FailingNotifier()

        with self.assertLogs("app.core.notifications", level="ERROR") as logs:
            res = await self.client.post(
                TASKS_API,
                headers=self.headers("alice"),
                json={
                    "project_id": self.active_project_id,
                    "title": "Fail open check",
                    "assignee_id": self.uid["bob"],
                },
            )

        self.assertEqual(res.status_code, 201, res.text)
        task_id = res.json()["id"]
        fetched = await self.client.get(
            f"{TASKS_API}{task_id}", headers=self.headers("alice")
        )
        self.assertEqual(fetched.status_code, 200, fetched.text)
        self.assertTrue(
            any("Failed to deliver task assignment notification" in line for line in logs.output)
        )

    async def test_default_di_notifier_logs_in_background_without_smtp(self):
        app.dependency_overrides.pop(get_task_assignment_notifier, None)

        with (
            patch.object(settings, "SMTP_HOST", ""),
            patch("app.core.notifications.smtplib.SMTP") as smtp_cls,
            self.assertLogs("app.core.notifications", level="INFO") as logs,
        ):
            res = await self.client.post(
                TASKS_API,
                headers=self.headers("alice"),
                json={
                    "project_id": self.active_project_id,
                    "title": "Log only notification",
                    "assignee_id": self.uid["bob"],
                },
            )

        self.assertEqual(res.status_code, 201, res.text)
        task_id = res.json()["id"]
        smtp_cls.assert_not_called()
        self.assertTrue(
            any(
                f"task_id={task_id}" in line and f"assignee_id={self.uid['bob']}" in line
                for line in logs.output
            )
        )


class LoggingAndSmtpTaskNotifierUnitTests(unittest.IsolatedAsyncioTestCase):
    def _sample_event(
        self,
        title: str = "Ship API",
        due_date: datetime | None = datetime(2026, 12, 1, 17, 0, tzinfo=timezone.utc),
    ) -> TaskAssignedEvent:
        return TaskAssignedEvent(
            task_id=42,
            task_title=title,
            project_id=7,
            workspace_id=3,
            assignee_id=2,
            assignee_email="bob@example.com",
            assignee_name="Bob",
            assigned_by_id=1,
            assigned_by_name="Alice",
            priority="URGENT",
            due_date=due_date,
        )

    async def test_smtp_enabled_sends_sanitized_tls_email_and_authenticates(self):
        notifier = LoggingAndSmtpTaskNotifier(
            smtp_host="smtp.example.com",
            smtp_port=2525,
            smtp_username="mailer",
            smtp_password="secret",
            smtp_from_email="tasks@example.com",
            smtp_use_tls=True,
            smtp_timeout_seconds=3.5,
        )
        event = self._sample_event(title="Fix login\r\nBcc: attacker@evil.test")

        smtp_client = MagicMock()
        smtp_cm = MagicMock()
        smtp_cm.__enter__.return_value = smtp_client

        with (
            patch("app.core.notifications.smtplib.SMTP", return_value=smtp_cm) as smtp_cls,
            self.assertLogs("app.core.notifications", level="INFO"),
        ):
            await dispatch_task_assigned(notifier, event)

        smtp_cls.assert_called_once_with("smtp.example.com", 2525, timeout=3.5)
        self.assertEqual(smtp_client.ehlo.call_count, 2)
        smtp_client.starttls.assert_called_once()
        tls_kwargs = smtp_client.starttls.call_args.kwargs
        self.assertIsInstance(tls_kwargs["context"], ssl.SSLContext)
        smtp_client.login.assert_called_once_with("mailer", "secret")
        smtp_client.send_message.assert_called_once()

        sent_msg = smtp_client.send_message.call_args.args[0]
        self.assertEqual(sent_msg["From"], "tasks@example.com")
        self.assertEqual(sent_msg["To"], "bob@example.com")
        self.assertNotIn("\r", sent_msg["Subject"])
        self.assertNotIn("\n", sent_msg["Subject"])
        self.assertIn("Fix login Bcc: attacker@evil.test", sent_msg["Subject"])
        body = sent_msg.get_content()
        self.assertIn("Alice assigned you to a task in TaskHub", body)
        self.assertIn("2026-12-01T17:00:00+00:00", body)

    async def test_smtp_without_tls_or_auth_and_blank_from_or_due_date(self):
        notifier = LoggingAndSmtpTaskNotifier(
            smtp_host="localhost",
            smtp_port=1025,
            smtp_username="   ",
            smtp_from_email="",
            smtp_use_tls=False,
        )
        smtp_client = MagicMock()
        smtp_cm = MagicMock()
        smtp_cm.__enter__.return_value = smtp_client

        with (
            patch("app.core.notifications.smtplib.SMTP", return_value=smtp_cm) as smtp_cls,
            self.assertLogs("app.core.notifications", level="INFO"),
        ):
            await notifier.notify_task_assigned(self._sample_event(due_date=None))

        smtp_cls.assert_called_once_with(
            "localhost", 1025, timeout=DEFAULT_SMTP_TIMEOUT_SECONDS
        )
        smtp_client.starttls.assert_not_called()
        smtp_client.login.assert_not_called()
        smtp_client.send_message.assert_called_once()
        sent_msg = smtp_client.send_message.call_args.args[0]
        self.assertEqual(sent_msg["From"], DEFAULT_SMTP_FROM_EMAIL)
        self.assertNotIn("Due date:", sent_msg.get_content())

    async def test_blank_from_email_does_not_reuse_api_key_username(self):
        notifier = LoggingAndSmtpTaskNotifier(
            smtp_host="smtp.sendgrid.net",
            smtp_username="apikey",
            smtp_password="sg-secret",
            smtp_from_email="",
        )
        self.assertEqual(notifier.smtp_from_email, DEFAULT_SMTP_FROM_EMAIL)

    async def test_smtp_exception_is_caught_fail_open_by_dispatcher(self):
        notifier = LoggingAndSmtpTaskNotifier(smtp_host="smtp.example.com")

        with (
            patch(
                "app.core.notifications.smtplib.SMTP",
                side_effect=smtplib.SMTPException("connection refused"),
            ),
            self.assertLogs("app.core.notifications", level="ERROR") as logs,
        ):
            await dispatch_task_assigned(notifier, self._sample_event())

        self.assertTrue(
            any("Failed to deliver task assignment notification" in line for line in logs.output)
        )

    def test_smtp_settings_validation(self):
        default_cfg = Settings(_env_file=None, DATABASE_URL="sqlite+aiosqlite://")
        self.assertEqual(default_cfg.SMTP_HOST, "")
        self.assertEqual(default_cfg.SMTP_PORT, DEFAULT_SMTP_PORT)
        self.assertEqual(default_cfg.SMTP_FROM_EMAIL, DEFAULT_SMTP_FROM_EMAIL)
        self.assertTrue(default_cfg.SMTP_USE_TLS)
        self.assertEqual(
            default_cfg.SMTP_TIMEOUT_SECONDS, DEFAULT_SMTP_TIMEOUT_SECONDS
        )

        self.assertFalse(
            Settings(
                _env_file=None,
                DATABASE_URL="sqlite+aiosqlite://",
                SMTP_USE_TLS="off",
            ).SMTP_USE_TLS
        )
        self.assertTrue(
            Settings(
                _env_file=None,
                DATABASE_URL="sqlite+aiosqlite://",
                SMTP_USE_TLS="on",
            ).SMTP_USE_TLS
        )
        for bad_kwargs in (
            {"SMTP_USE_TLS": "maybe"},
            {"SMTP_PORT": 0},
            {"SMTP_PORT": 65536},
            {"SMTP_TIMEOUT_SECONDS": 0},
            {"SMTP_TIMEOUT_SECONDS": -1},
        ):
            with self.assertRaises(ValidationError):
                Settings(
                    _env_file=None,
                    DATABASE_URL="sqlite+aiosqlite://",
                    **bad_kwargs,
                )
