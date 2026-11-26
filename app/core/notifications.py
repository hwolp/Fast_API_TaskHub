from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
import logging
import smtplib
import ssl
from typing import Protocol

from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)

DEFAULT_SMTP_PORT = 587
DEFAULT_SMTP_FROM_EMAIL = "noreply@taskhub.local"
DEFAULT_SMTP_TIMEOUT_SECONDS = 5.0


def _sanitize_header(value: str) -> str:
    return " ".join(value.splitlines()).strip()


@dataclass(frozen=True, slots=True)
class TaskAssignedEvent:
    task_id: int
    task_title: str
    project_id: int
    workspace_id: int
    assignee_id: int
    assignee_email: str
    assignee_name: str
    assigned_by_id: int
    assigned_by_name: str
    priority: str
    due_date: datetime | None = None


class TaskAssignmentNotifier(Protocol):
    async def notify_task_assigned(self, event: TaskAssignedEvent) -> None: ...


class LoggingAndSmtpTaskNotifier:
    def __init__(
        self,
        *,
        smtp_host: str = "",
        smtp_port: int = DEFAULT_SMTP_PORT,
        smtp_username: str = "",
        smtp_password: str = "",
        smtp_from_email: str = DEFAULT_SMTP_FROM_EMAIL,
        smtp_use_tls: bool = True,
        smtp_timeout_seconds: float = DEFAULT_SMTP_TIMEOUT_SECONDS,
    ) -> None:
        self.smtp_host = smtp_host.strip()
        self.smtp_port = smtp_port
        self.smtp_username = smtp_username
        self.smtp_password = smtp_password
        self.smtp_from_email = (
            smtp_from_email.strip() or smtp_username.strip() or DEFAULT_SMTP_FROM_EMAIL
        )
        self.smtp_use_tls = smtp_use_tls
        self.smtp_timeout_seconds = smtp_timeout_seconds

    async def notify_task_assigned(self, event: TaskAssignedEvent) -> None:
        logger.info(
            "Task assigned notification: task_id=%s project_id=%s workspace_id=%s "
            "assignee_id=%s assigned_by_id=%s priority=%s title=%r",
            event.task_id,
            event.project_id,
            event.workspace_id,
            event.assignee_id,
            event.assigned_by_id,
            event.priority,
            event.task_title,
            extra={
                "event": "task_assigned",
                "task_id": event.task_id,
                "project_id": event.project_id,
                "workspace_id": event.workspace_id,
                "assignee_id": event.assignee_id,
                "assigned_by_id": event.assigned_by_id,
            },
        )
        if self.smtp_host:
            await run_in_threadpool(self._send_email_sync, event)

    def _build_email_message(self, event: TaskAssignedEvent) -> EmailMessage:
        safe_title = _sanitize_header(event.task_title)
        message = EmailMessage()
        message["From"] = _sanitize_header(self.smtp_from_email)
        message["To"] = _sanitize_header(event.assignee_email)
        message["Subject"] = f"[TaskHub] You were assigned to task #{event.task_id}: {safe_title}"
        due_line = (
            f"Due date: {event.due_date.isoformat()}\n"
            if event.due_date is not None
            else ""
        )
        message.set_content(
            f"Hi {event.assignee_name},\n\n"
            f"{event.assigned_by_name} assigned you to a task in TaskHub.\n\n"
            f"Task: #{event.task_id} - {safe_title}\n"
            f"Project ID: {event.project_id}\n"
            f"Workspace ID: {event.workspace_id}\n"
            f"Priority: {event.priority}\n"
            f"{due_line}"
        )
        return message

    def _send_email_sync(self, event: TaskAssignedEvent) -> None:
        message = self._build_email_message(event)
        with smtplib.SMTP(
            self.smtp_host,
            self.smtp_port,
            timeout=self.smtp_timeout_seconds,
        ) as client:
            client.ehlo()
            if self.smtp_use_tls:
                client.starttls(context=ssl.create_default_context())
                client.ehlo()
            if self.smtp_username:
                client.login(self.smtp_username, self.smtp_password)
            client.send_message(message)


async def dispatch_task_assigned(
    notifier: TaskAssignmentNotifier,
    event: TaskAssignedEvent,
) -> None:
    try:
        await notifier.notify_task_assigned(event)
    except Exception:
        logger.exception(
            "Failed to deliver task assignment notification for task_id=%s assignee_id=%s",
            event.task_id,
            event.assignee_id,
        )
