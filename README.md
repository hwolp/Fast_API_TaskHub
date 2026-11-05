# FastAPI TaskHub

TaskHub là hệ thống backend quản lý công việc và dự án, được xây dựng theo kiến trúc phân tầng (Layered Architecture) trên nền tảng FastAPI, kết hợp SQLAlchemy 2.x Async, Pydantic v2 và Repository Pattern.

---

# Cấu trúc thư mục

```text
Fast_API_TaskHub/
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── endpoints/
│   │       │   └── task.py         # Endpoints CRUD cho resource Task
│   │       └── router.py           # Tổng hợp router v1 (/api/v1)
│   ├── core/
│   │   ├── config.py               # Cấu hình Settings và biến môi trường
│   │   └── database.py             # Khởi tạo Async Engine, SessionFactory và get_db
│   ├── models/                     # Định nghĩa SQLAlchemy Models
│   │   ├── enums.py                # Các Enum dùng chung trong hệ thống
│   │   ├── user.py                 # Model bảng users
│   │   ├── workspace.py            # Model bảng workspaces và workspace_members
│   │   ├── project.py              # Model bảng projects
│   │   ├── task.py                 # Model bảng tasks
│   │   ├── label.py                # Model bảng labels và task_labels
│   │   ├── comment.py              # Model bảng comments
│   │   └── __init__.py             # Export toàn bộ models phục vụ migration
│   ├── repositories/               # Tầng tương tác CSDL (Repository Pattern)
│   │   ├── base.py                 # BaseRepository[ModelT] generic async CRUD & pagination
│   │   └── task.py                 # TaskRepository xử lý truy vấn cho Task
│   ├── schemas/                    # Pydantic Schemas (Data Transfer Objects)
│   │   └── task.py                 # Request/Response models cho Task
│   ├── services/                   # Tầng xử lý logic nghiệp vụ
│   │   └── task.py                 # TaskService điều phối nghiệp vụ Task
│   ├── dependencies.py             # Dependency injection chung
│   └── main.py                     # Entry point khởi tạo ứng dụng FastAPI và lifespan
├── .env                            # File cấu hình môi trường cục bộ
├── .gitignore                      # Cấu hình loại trừ file của Git
├── requirements.txt                # Danh sách thư viện phụ thuộc
└── README.md                       # Tài liệu mô tả nội dung và cấu trúc dự án
```
