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

# Authentication

Auth dùng JWT RS256 cho access token (15 phút) và refresh token (7 ngày), mật khẩu
băm Argon2. Refresh token được lưu SHA-256 trong bảng `refresh_tokens` ở revision
`0002`; không lưu token gốc. Mỗi lần refresh trả cặp token mới và vô hiệu hóa
refresh token cũ. Dùng lại token cũ sẽ thu hồi cả chuỗi refresh token của phiên đó.

## Cài đặt và chạy

```powershell
python -m pip install -r requirements.txt
python scripts/generate_auth_keys.py
python -m alembic upgrade head
python -m uvicorn app.main:app --reload
```

Script tạo khóa RSA 2048 bit trong `.keys/` (đã bỏ qua trong Git), từ chối ghi đè
nếu khóa đã tồn tại. Khóa cục bộ đã được tạo khi triển khai tính năng này, nên bỏ
qua bước tạo khóa khi chạy lại trong workspace hiện tại. Cấu hình
`JWT_PRIVATE_KEY_PATH`, `JWT_PUBLIC_KEY_PATH`, `JWT_KEY_ID`, `JWT_ISSUER`,
`JWT_AUDIENCE`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS` trong
`.env` khi cần. Đường dẫn khóa tương đối được tính từ thư mục gốc dự án.
Ứng dụng không dùng `SECRET_KEY` mặc định để ký JWT; cần có khóa RSA hợp lệ.

Trên production, cấp khóa riêng qua secret volume, giới hạn quyền đọc private key,
dùng HTTPS và chia sẻ cùng bộ khóa giữa các instance. Header JWT có `kid`;
`GET /.well-known/jwks.json` công bố public key hiện tại. Thay bộ khóa hiện tại sẽ
làm token ký bằng khóa cũ mất hiệu lực; cần mở rộng danh sách khóa xác minh nếu
muốn rotation không gián đoạn.

## API

| Method | Endpoint | JSON body / xác thực | Kết quả |
| --- | --- | --- | --- |
| POST | `/api/v1/auth/register` | `email`, `password` (8–128 ký tự), `full_name` | 201, thông tin user với role MEMBER |
| POST | `/api/v1/auth/login` | `email`, `password` | 200, `access_token`, `refresh_token`, `token_type`, `expires_in` |
| POST | `/api/v1/auth/refresh` | `refresh_token` | 200, cặp token mới |
| POST | `/api/v1/auth/logout` | `refresh_token` | 204, thu hồi chuỗi refresh token của phiên |
| GET | `/api/v1/auth/me` | `Authorization: Bearer <access_token>` | 200, thông tin user hiện tại |

Ví dụ body đăng ký:

```json
{
  "email": "member@example.com",
  "password": "a-long-private-password",
  "full_name": "TaskHub Member"
}
```

Login dùng JSON. Email được chuyển về chữ thường; email trùng trả 409, dữ liệu
không hợp lệ trả 422, sai thông tin đăng nhập trả 401. Access token và refresh token
không thay thế được cho nhau. User bị vô hiệu hóa không thể login, refresh hay dùng
`/me`. Client cần lưu cặp token mới sau mỗi lần refresh và tránh gọi refresh song song.

Logout thu hồi refresh token của phiên hiện tại, không ảnh hưởng phiên đăng nhập
khác. Access token đã cấp tiếp tục có hiệu lực đến khi hết hạn. API task hiện tại
vẫn giữ hành vi truy cập cũ; dùng `Depends(get_current_user)` từ
`app.dependencies` khi bổ sung bảo vệ resource và kiểm tra quyền sở hữu.

Với client trình duyệt, giữ access token trong bộ nhớ; refresh token nên được xử lý
qua BFF/cookie HttpOnly, Secure với bảo vệ CSRF. Các endpoint hiện tại nhận và trả
token bằng JSON, không tự đặt cookie.

## Migration và kiểm thử

Database đang ở `0001` chỉ cần chạy `python -m alembic upgrade head` để thêm bảng
refresh token. MySQL database cần tồn tại trước khi chạy migration.

```powershell
python -m alembic current
python -m alembic history
python -m alembic check
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

Test dùng khóa RSA và SQLite tạm, không thay đổi database trong `.env`.
Bao gồm đăng ký, trùng email, mật khẩu sai, user vô hiệu hóa, JWT hết hạn/sai chữ ký,
refresh rotation/reuse, logout và migration. Luồng ký JWT và băm mật khẩu tham khảo
[FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/) và
[PyJWT](https://pyjwt.readthedocs.io/en/stable/usage.html).

