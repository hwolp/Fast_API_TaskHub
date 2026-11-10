"""Seed demo users, workspace, members, and project for manual Swagger testing."""

import asyncio

from sqlalchemy import select

from app.core.database import AsyncSessionLocal, engine
from app.core.security import password_hash
from app.models.enums import UserRole, WorkspaceRole
from app.models.project import Project
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember

DEMO_USERS = [
    ("owner@example.com", "Owner User", UserRole.MEMBER, WorkspaceRole.OWNER),
    ("editor@example.com", "Editor User", UserRole.MEMBER, WorkspaceRole.EDITOR),
    ("viewer@example.com", "Viewer User", UserRole.MEMBER, WorkspaceRole.VIEWER),
    ("sysadmin@example.com", "System Admin", UserRole.ADMIN, None),
]
DEMO_PASSWORD = "Password123!"


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        users_by_email: dict[str, User] = {}
        for email, full_name, sys_role, _ in DEMO_USERS:
            user = await db.scalar(select(User).where(User.email == email))
            if not user:
                user = User(
                    email=email,
                    hashed_password=password_hash.hash(DEMO_PASSWORD),
                    full_name=full_name,
                    role=sys_role,
                )
                db.add(user)
                await db.flush()
            users_by_email[email] = user

        ws = await db.scalar(select(Workspace).where(Workspace.name == "Demo Workspace"))
        if not ws:
            ws = Workspace(
                name="Demo Workspace",
                owner_id=users_by_email["owner@example.com"].id,
            )
            db.add(ws)
            await db.flush()

        for email, _, _, ws_role in DEMO_USERS:
            if ws_role is None:
                continue
            uid = users_by_email[email].id
            member = await db.scalar(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == ws.id,
                    WorkspaceMember.user_id == uid,
                )
            )
            if not member:
                db.add(WorkspaceMember(workspace_id=ws.id, user_id=uid, role=ws_role))

        proj = await db.scalar(
            select(Project).where(Project.workspace_id == ws.id, Project.name == "Demo Project")
        )
        if not proj:
            proj = Project(
                workspace_id=ws.id,
                name="Demo Project",
                description="Demo project for testing Task RBAC in Swagger UI",
            )
            db.add(proj)
            await db.flush()

        await db.commit()
        print(f"Seeded successfully! Demo password for all accounts: {DEMO_PASSWORD}")
        print(f"Workspace ID : {ws.id} (name: {ws.name})")
        print(f"Project ID   : {proj.id} (use this as project_id in POST /api/v1/tasks/)")
        for email, _, sys_role, ws_role in DEMO_USERS:
            print(f"  - {email:22s} | id={users_by_email[email].id} | sys={sys_role.value} | ws={ws_role.value if ws_role else 'N/A'}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())

