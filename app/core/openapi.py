from app.schemas.pagination import MAX_LIMIT

API_VERSION = "1.0.0"

OPENAPI_DESCRIPTION = f"""
REST API for collaborative project and task management with RS256 JWT authentication, workspace RBAC, and Redis-backed task list caching.

## Authentication in Swagger UI
1. Create an account via **POST `/api/v1/auth/register`**.
2. Sign in via **POST `/api/v1/auth/login`** and copy the returned `access_token`.
3. Click **Authorize**, paste the token into **HTTPBearer**, and send protected requests.
4. Public RS256 verification keys are published at **GET `/.well-known/jwks.json`**.

## Role-Based Access Control (RBAC)
- **System roles**: `ADMIN` (global access) and `MEMBER` (scoped by workspace membership).
- **Workspace roles**: `OWNER` (full workspace control), `EDITOR` (create/edit projects, tasks, labels, and comments within workspace rules), and `VIEWER` (read-only access to workspace, projects, tasks, labels, and comments).
- **Archived projects**: Projects in `ARCHIVED` status block mutations on child tasks, labels, and comments.

## Conventions
- **Pagination**: List endpoints accept `page` (>= 1) and `limit` (1-{MAX_LIMIT}) and return `{{"items": [...], "total": <int>}}`.
- **Errors**: Domain and auth errors (`400`, `401`, `403`, `404`, `409`) return `ErrorResponse` (`{{"detail": "<error_code>"}}`); request validation errors (`422`) return FastAPI's `HTTPValidationError` where `detail` is a list of validation error objects.
""".strip()

OPENAPI_TAGS = [
    {
        "name": "auth",
        "description": "User registration, RS256 JWT login/refresh rotation, logout revocation, profile lookup, and JWKS discovery.",
    },
    {
        "name": "workspaces",
        "description": "Workspace CRUD and workspace membership / role management (`OWNER`, `EDITOR`, `VIEWER`).",
    },
    {
        "name": "projects",
        "description": "Project management within workspaces, including active/archived lifecycle status.",
    },
    {
        "name": "tasks",
        "description": "Task CRUD, assignee/status/priority updates, paginated task listing, and task-label attachment.",
    },
    {
        "name": "labels",
        "description": "Project-scoped labels with unique names and hex color validation.",
    },
    {
        "name": "comments",
        "description": "Task discussion comments with author/workspace permission checks.",
    },
    {
        "name": "system",
        "description": "Service liveness and version metadata.",
    },
]

SWAGGER_UI_PARAMETERS = {
    "persistAuthorization": True,
    "displayRequestDuration": True,
    "docExpansion": "list",
    "filter": True,
}
