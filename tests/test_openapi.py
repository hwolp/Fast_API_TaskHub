import unittest
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.core import messages
from app.core.config import Settings, settings
from app.core.openapi import API_VERSION
from app.main import create_app
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest
from app.schemas.comment import CommentCreate, CommentUpdate
from app.schemas.common import HEALTH_MESSAGE_OK, HEALTH_STATUS_OK
from app.schemas.label import LabelCreate, LabelUpdate
from app.schemas.pagination import MAX_LIMIT
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.schemas.task import TaskCreate, TaskUpdate
from app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceMemberAdd,
    WorkspaceMemberUpdate,
    WorkspaceUpdate,
)

HTTP_METHODS = ("get", "post", "put", "patch", "delete")
ERROR_CODES = ("400", "401", "403", "404", "409")
EXPECTED_ERROR_EXAMPLES = {
    "400": messages.PROJECT_ARCHIVED,
    "401": messages.TOKEN_MISSING,
    "403": messages.FORBIDDEN,
    "404": messages.WORKSPACE_NOT_FOUND,
    "409": messages.MEMBER_ALREADY_EXISTS,
}
EXPECTED_ERROR_RESPONSES: dict[tuple[str, str], set[str]] = {
    ("get", "/healthy"): set(),
    ("get", "/.well-known/jwks.json"): set(),
    ("post", "/api/v1/auth/register"): {"409"},
    ("post", "/api/v1/auth/login"): {"401"},
    ("post", "/api/v1/auth/refresh"): {"401"},
    ("post", "/api/v1/auth/logout"): {"401"},
    ("get", "/api/v1/auth/me"): {"401"},
    ("post", "/api/v1/workspaces/"): {"401"},
    ("get", "/api/v1/workspaces/"): {"401"},
    ("get", "/api/v1/workspaces/{workspace_id}"): {"401", "404"},
    ("patch", "/api/v1/workspaces/{workspace_id}"): {"401", "403", "404"},
    ("delete", "/api/v1/workspaces/{workspace_id}"): {"401", "403", "404"},
    ("get", "/api/v1/workspaces/{workspace_id}/members"): {"401", "404"},
    ("post", "/api/v1/workspaces/{workspace_id}/members"): {"401", "403", "404", "409"},
    ("patch", "/api/v1/workspaces/{workspace_id}/members/{member_user_id}"): {
        "400",
        "401",
        "403",
        "404",
    },
    ("delete", "/api/v1/workspaces/{workspace_id}/members/{member_user_id}"): {
        "400",
        "401",
        "403",
        "404",
    },
    ("post", "/api/v1/projects/"): {"401", "403", "404"},
    ("get", "/api/v1/projects/"): {"401"},
    ("get", "/api/v1/projects/{project_id}"): {"401", "404"},
    ("patch", "/api/v1/projects/{project_id}"): {"401", "403", "404"},
    ("delete", "/api/v1/projects/{project_id}"): {"401", "403", "404"},
    ("post", "/api/v1/tasks/"): {"400", "401", "403", "404"},
    ("get", "/api/v1/tasks/"): {"401"},
    ("get", "/api/v1/tasks/{task_id}"): {"401", "404"},
    ("patch", "/api/v1/tasks/{task_id}"): {"400", "401", "403", "404"},
    ("delete", "/api/v1/tasks/{task_id}"): {"400", "401", "403", "404"},
    ("post", "/api/v1/tasks/{task_id}/labels/{label_id}"): {"400", "401", "403", "404"},
    ("delete", "/api/v1/tasks/{task_id}/labels/{label_id}"): {
        "400",
        "401",
        "403",
        "404",
    },
    ("post", "/api/v1/labels/"): {"400", "401", "403", "404", "409"},
    ("get", "/api/v1/labels/"): {"401"},
    ("get", "/api/v1/labels/{label_id}"): {"401", "404"},
    ("patch", "/api/v1/labels/{label_id}"): {"400", "401", "403", "404", "409"},
    ("delete", "/api/v1/labels/{label_id}"): {"400", "401", "403", "404"},
    ("post", "/api/v1/comments/"): {"400", "401", "403", "404"},
    ("get", "/api/v1/comments/"): {"401"},
    ("get", "/api/v1/comments/{comment_id}"): {"401", "404"},
    ("patch", "/api/v1/comments/{comment_id}"): {"400", "401", "403", "404"},
    ("delete", "/api/v1/comments/{comment_id}"): {"400", "401", "403", "404"},
}
PROTECTED_PREFIXES = (
    "/api/v1/workspaces",
    "/api/v1/projects",
    "/api/v1/tasks",
    "/api/v1/labels",
    "/api/v1/comments",
)
PUBLIC_OPERATIONS = {
    ("get", "/.well-known/jwks.json"),
    ("post", "/api/v1/auth/register"),
    ("post", "/api/v1/auth/login"),
    ("post", "/api/v1/auth/refresh"),
    ("post", "/api/v1/auth/logout"),
    ("get", "/healthy"),
}
EXPECTED_TAGS = {
    "auth",
    "workspaces",
    "projects",
    "tasks",
    "labels",
    "comments",
    "system",
}
REQUEST_SCHEMA_MODELS = {
    "LoginRequest": LoginRequest,
    "RegisterRequest": RegisterRequest,
    "RefreshRequest": RefreshRequest,
    "WorkspaceCreate": WorkspaceCreate,
    "WorkspaceUpdate": WorkspaceUpdate,
    "WorkspaceMemberAdd": WorkspaceMemberAdd,
    "WorkspaceMemberUpdate": WorkspaceMemberUpdate,
    "ProjectCreate": ProjectCreate,
    "ProjectUpdate": ProjectUpdate,
    "TaskCreate": TaskCreate,
    "TaskUpdate": TaskUpdate,
    "LabelCreate": LabelCreate,
    "LabelUpdate": LabelUpdate,
    "CommentCreate": CommentCreate,
    "CommentUpdate": CommentUpdate,
}


class OpenAPIDocsTests(unittest.IsolatedAsyncioTestCase):
    async def _get_openapi_schema(self, application=None) -> dict:
        target_app = application or create_app(enable_docs=True)
        async with AsyncClient(
            transport=ASGITransport(app=target_app), base_url="http://test"
        ) as client:
            response = await client.get("/openapi.json")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_openapi_metadata_tags_and_security_scheme(self):
        schema = await self._get_openapi_schema()

        info = schema["info"]
        self.assertEqual(info["title"], settings.PROJECT_NAME)
        self.assertEqual(info["version"], API_VERSION)
        description = info.get("description", "").strip()
        self.assertTrue(description)
        self.assertIn(f"(1-{MAX_LIMIT})", description)
        self.assertIn("422", description)
        self.assertNotIn("plus commenting", description)

        declared_tags = {
            tag["name"]: tag.get("description", "").strip()
            for tag in schema.get("tags", [])
        }
        self.assertEqual(set(declared_tags.keys()), EXPECTED_TAGS)
        for name, desc in declared_tags.items():
            self.assertTrue(desc, f"Tag '{name}' must have a non-empty description")

        schemes = schema["components"]["securitySchemes"]
        self.assertIn("HTTPBearer", schemes)
        bearer = schemes["HTTPBearer"]
        self.assertEqual(bearer["type"], "http")
        self.assertEqual(bearer["scheme"], "bearer")
        self.assertEqual(bearer["bearerFormat"], "JWT")
        self.assertTrue(bearer.get("description", "").strip())

    async def test_all_operations_have_summaries_valid_tags_and_error_models(self):
        schema = await self._get_openapi_schema()
        declared_tags = {tag["name"] for tag in schema["tags"]}
        seen_operations: set[tuple[str, str]] = set()

        for path, path_item in schema["paths"].items():
            for method, op in path_item.items():
                if method not in HTTP_METHODS:
                    continue
                op_key = (method, path)
                seen_operations.add(op_key)
                self.assertIn(
                    op_key,
                    EXPECTED_ERROR_RESPONSES,
                    f"Unexpected operation {method.upper()} {path}; update EXPECTED_ERROR_RESPONSES",
                )
                self.assertTrue(
                    op.get("summary", "").strip(),
                    f"{method.upper()} {path} must define summary",
                )
                tags = op.get("tags", [])
                self.assertTrue(tags, f"{method.upper()} {path} must define tags")
                for tag in tags:
                    self.assertIn(tag, declared_tags)

                responses = op.get("responses", {})
                declared_error_codes = {
                    code for code in responses if code in ERROR_CODES
                }
                self.assertEqual(
                    declared_error_codes,
                    EXPECTED_ERROR_RESPONSES[op_key],
                    f"{method.upper()} {path} error status codes mismatch",
                )
                for code in declared_error_codes:
                    app_json = responses[code].get("content", {}).get("application/json", {})
                    ref = app_json.get("schema", {}).get("$ref")
                    self.assertEqual(
                        ref,
                        "#/components/schemas/ErrorResponse",
                        f"{method.upper()} {path} {code} must reference ErrorResponse",
                    )
                    example_detail = app_json.get("example", {}).get("detail")
                    self.assertEqual(
                        example_detail,
                        EXPECTED_ERROR_EXAMPLES[code],
                        f"{method.upper()} {path} {code} example detail mismatch",
                    )

        self.assertEqual(seen_operations, set(EXPECTED_ERROR_RESPONSES.keys()))

        jwks_ref = schema["paths"]["/.well-known/jwks.json"]["get"]["responses"]["200"][
            "content"
        ]["application/json"]["schema"]["$ref"]
        self.assertEqual(jwks_ref, "#/components/schemas/JWKSResponse")

        healthy_ref = schema["paths"]["/healthy"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]["$ref"]
        self.assertEqual(healthy_ref, "#/components/schemas/HealthResponse")

    async def test_protected_routes_require_bearer_and_document_401(self):
        schema = await self._get_openapi_schema()

        for path, path_item in schema["paths"].items():
            for method, op in path_item.items():
                if method not in HTTP_METHODS:
                    continue
                is_protected = path == "/api/v1/auth/me" or any(
                    path.startswith(prefix) for prefix in PROTECTED_PREFIXES
                )
                if is_protected:
                    self.assertIn(
                        {"HTTPBearer": []},
                        op.get("security", []),
                        f"{method.upper()} {path} must require HTTPBearer",
                    )
                    self.assertIn(
                        "401",
                        op.get("responses", {}),
                        f"{method.upper()} {path} must document 401 Unauthorized",
                    )
                elif (method, path) in PUBLIC_OPERATIONS:
                    self.assertNotIn(
                        "security",
                        op,
                        f"Public {method.upper()} {path} must not require security",
                    )
                else:
                    self.fail(
                        f"Unclassified operation {method.upper()} {path}; "
                        "add it to PROTECTED_PREFIXES or PUBLIC_OPERATIONS"
                    )

    async def test_request_schema_examples_exist_and_validate(self):
        schema = await self._get_openapi_schema()
        schemas = schema["components"]["schemas"]

        for name, model_cls in REQUEST_SCHEMA_MODELS.items():
            self.assertIn(name, schemas)
            self.assertIn("example", schemas[name], f"{name} missing OpenAPI example")
            validated = model_cls.model_validate(schemas[name]["example"])
            self.assertIsInstance(validated, model_cls)

    async def test_docs_enabled_and_disabled_toggle_and_healthy(self):
        enabled_app = create_app(enable_docs=True)
        async with AsyncClient(
            transport=ASGITransport(app=enabled_app), base_url="http://test"
        ) as client:
            docs_res = await client.get("/docs")
            redoc_res = await client.get("/redoc")
            openapi_res = await client.get("/openapi.json")
            healthy_res = await client.get("/healthy")

        self.assertEqual(docs_res.status_code, 200)
        self.assertIn("text/html", docs_res.headers["content-type"])
        self.assertIn('"persistAuthorization": true', docs_res.text)
        self.assertEqual(redoc_res.status_code, 200)
        self.assertIn("text/html", redoc_res.headers["content-type"])
        self.assertIn("redoc", redoc_res.text.lower())
        self.assertEqual(openapi_res.status_code, 200)
        self.assertEqual(healthy_res.status_code, 200)
        self.assertEqual(
            healthy_res.json(),
            {
                "status": HEALTH_STATUS_OK,
                "message": HEALTH_MESSAGE_OK,
                "version": API_VERSION,
            },
        )

        disabled_app = create_app(enable_docs=False)
        async with AsyncClient(
            transport=ASGITransport(app=disabled_app), base_url="http://test"
        ) as client:
            self.assertEqual((await client.get("/docs")).status_code, 404)
            self.assertEqual((await client.get("/redoc")).status_code, 404)
            self.assertEqual((await client.get("/openapi.json")).status_code, 404)
            self.assertEqual((await client.get("/healthy")).status_code, 200)

        with patch.object(settings, "ENABLE_DOCS", False):
            default_disabled_app = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=default_disabled_app), base_url="http://test"
        ) as client:
            self.assertEqual((await client.get("/docs")).status_code, 404)
            self.assertEqual((await client.get("/openapi.json")).status_code, 404)

        default_settings = Settings(
            _env_file=None,
            DATABASE_URL="sqlite+aiosqlite://",
        )
        self.assertFalse(default_settings.ENABLE_DOCS)

        for raw_true in ("true", "1", "yes", "on", "TRUE"):
            self.assertTrue(
                Settings(
                    _env_file=None,
                    DATABASE_URL="sqlite+aiosqlite://",
                    ENABLE_DOCS=raw_true,
                ).ENABLE_DOCS,
                f"Expected ENABLE_DOCS={raw_true!r} to parse as True",
            )

        for raw_false in ("false", "0", "no", "off", "disabled", "none", "OFF"):
            self.assertFalse(
                Settings(
                    _env_file=None,
                    DATABASE_URL="sqlite+aiosqlite://",
                    ENABLE_DOCS=raw_false,
                ).ENABLE_DOCS,
                f"Expected ENABLE_DOCS={raw_false!r} to parse as False",
            )

        for raw_invalid in ("maybe", "enabled-ish", ""):
            with self.assertRaises(
                ValidationError,
                msg=f"Expected ENABLE_DOCS={raw_invalid!r} to fail validation",
            ):
                Settings(
                    _env_file=None,
                    DATABASE_URL="sqlite+aiosqlite://",
                    ENABLE_DOCS=raw_invalid,
                )
