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
├── alembic.ini                     # Cấu hình Alembic
├── alembic/
│   ├── env.py                      # Kết nối async và metadata của models
│   ├── script.py.mako              # Template cho revision mới
│   └── versions/                   # Lịch sử migration được lưu trong Git
├── .gitignore                      # Cấu hình loại trừ file của Git
├── requirements.txt                # Danh sách thư viện phụ thuộc
└── README.md                       # Tài liệu mô tả nội dung và cấu trúc dự án
```

# Quản lý phiên bản database với Alembic

Chạy các lệnh từ thư mục gốc dự án, trong môi trường Python đã cài dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Tạo `.env` từ `.env.example` nếu chưa có và cấu hình `DATABASE_URL`.
Alembic dùng chung Settings với ứng dụng, hỗ trợ URL async như
`mysql+aiomysql://...` hoặc `sqlite+aiosqlite:///./taskhub.db`.
Với MySQL, cần tạo database `taskhub_db` trước; migration tạo các bảng bên trong database.

## Database mới

```powershell
python -m alembic upgrade head
python -m alembic current
python -m uvicorn app.main:app --reload
```

Revision đầu tiên tạo toàn bộ 8 bảng hiện tại, kèm khóa ngoại và index.
Bảng `alembic_version` lưu revision đang áp dụng. Chạy migration trước khi khởi động
ứng dụng; ứng dụng không tự chạy migration khi startup.

## Khi thay đổi models

```powershell
python -m alembic revision --autogenerate -m "add task field"
# Đọc và kiểm tra upgrade()/downgrade() trong file vừa tạo trước khi áp dụng.
python -m alembic upgrade head
python -m alembic check
```

Database cần ở revision mới nhất trước khi tạo revision tiếp theo. Commit các file
trong `alembic/versions/` cùng thay đổi models; tạo revision mới thay vì sửa revision
đã được áp dụng ở môi trường khác. Autogenerate không tự hiểu mọi thay đổi, đặc biệt
việc đổi tên bảng/cột và chuyển đổi dữ liệu, nên cần kiểm tra SQL và sửa thủ công.

## Migration dữ liệu

Tạo revision trống để backfill hoặc chuyển đổi dữ liệu:

```powershell
python -m alembic revision -m "backfill label colors"
```

Ví dụ nội dung hai hàm trong revision vừa tạo:

```python
def upgrade() -> None:
    labels = sa.table("labels", sa.column("color", sa.String(20)))
    op.execute(
        labels.update()
        .where(labels.c.color == "#3B82F6")
        .values(color="#2563EB")
    )


def downgrade() -> None:
    # Không thể phân biệt màu mới có sẵn với màu được chuyển đổi.
    raise NotImplementedError("Data migration này không hỗ trợ rollback tự động")
```

Dùng `op.bulk_insert()` cho dữ liệu khởi tạo; dùng `op.execute()` hoặc
`op.get_bind()` cho chuyển đổi dữ liệu. Khai báo bảng/cột ngay trong revision,
tránh import ORM models có thể thay đổi trong tương lai. Nếu cần rollback chính xác,
lưu dữ liệu gốc hoặc thiết kế phép chuyển đổi đảo ngược được trước khi chạy.

## Lịch sử, rollback và xuất SQL

```powershell
python -m alembic history --verbose
python -m alembic heads
python -m alembic current
python -m alembic downgrade -1
python -m alembic upgrade head
python -m alembic upgrade head --sql
```

`downgrade -1` chạy hàm `downgrade()` của revision hiện tại. Rollback revision đầu
tiên sẽ xóa các bảng và dữ liệu; sao lưu trước khi chạy trên database quan trọng.
`--sql` xuất SQL mà không kết nối database; migration dữ liệu cần đọc dữ liệu hiện
có qua `op.get_bind()` phải chạy online. Với MySQL, thay đổi DDL có thể tự commit,
nên lỗi giữa migration có thể cần xử lý thủ công.

## Database đã có bảng trước khi tích hợp Alembic

Không chạy revision tạo bảng trực tiếp lên database đã có các bảng đó.
Sao lưu, đối chiếu toàn bộ schema hiện tại với revision `0001` (bảng, cột, index,
khóa ngoại, kiểu dữ liệu và nullable). Chỉ khi chúng khớp hoàn toàn mới đánh dấu:

```powershell
python -m alembic stamp 0001
python -m alembic check
python -m alembic upgrade head
```

`stamp` chỉ ghi phiên bản, không tạo bảng hay chuyển đổi dữ liệu. Nếu schema khác,
cần lập migration điều chỉnh phù hợp trước khi đánh dấu phiên bản.

Tham khảo: [Alembic Tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html).

## Kiểm tra migration

```powershell
python -m unittest discover -s tests -v
```

Các test dùng SQLite tạm để kiểm tra upgrade, schema khớp models, giữ dữ liệu khi
chạy lại upgrade và downgrade/upgrade; đồng thời kiểm tra xuất SQL cho MySQL.
Không kết nối hay thay đổi database trong `.env`.
