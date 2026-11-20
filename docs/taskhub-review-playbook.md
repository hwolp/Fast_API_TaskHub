# Sổ tay review backend FastAPI TaskHub

Tài liệu học từ PR #1–#7, đối chiếu với code TaskHub tại commit `f4d608f`. Phần đầu tóm tắt ý của hai reviewer `giangnv-0040` và `huongnt-2545`. Phần sau bổ sung cách áp dụng, đo hiệu năng và tự kiểm tra. PR #7 có mô tả triển khai Redis, hiện chưa có nhận xét review.

## 1. Những gì reviewer đã góp ý

### PR #1 — Database và Alembic

- **Nối tính năng từ API đến DB.** Khai báo ORM model chưa làm cho endpoint có tính lưu trữ. PR mô tả Alembic cần có migration chạy được, task repository cần truy vấn DB và test phải dùng DB riêng. [Review #1](https://github.com/hwolp/Fast_API_TaskHub/pull/1#pullrequestreview-5855612409)
- **Đặt giao dịch ở tầng điều phối.** Repository dùng `flush()` và `refresh()` khi cần. Tầng điều phối quyết định commit, và thao tác ghi cần commit trước khi trả thành công. [Repository tự commit](https://github.com/hwolp/Fast_API_TaskHub/pull/1#discussion_r4535393524), [Commit sau yield](https://github.com/hwolp/Fast_API_TaskHub/pull/1#discussion_r4535393528)
- **Thiết kế ràng buộc theo nghiệp vụ.** Bật FK cho SQLite, cân nhắc `RESTRICT` khi xóa user có dữ liệu cần giữ, kiểm tra index trên cột FK phục vụ truy vấn, khớp DB cascade với `passive_deletes` của ORM, thêm CHECK cho enum không native. Cấu hình DB lấy từ môi trường. Reviewer đề nghị dùng DB default cho thời điểm tạo bản ghi. [FK SQLite](https://github.com/hwolp/Fast_API_TaskHub/pull/1#discussion_r4535393520), [RESTRICT](https://github.com/hwolp/Fast_API_TaskHub/pull/1#discussion_r4535393552), [Async cascade](https://github.com/hwolp/Fast_API_TaskHub/pull/1#discussion_r4535393560), [Thời gian](https://github.com/hwolp/Fast_API_TaskHub/pull/1#discussion_r4535393534), [Enum và constants](https://github.com/hwolp/Fast_API_TaskHub/pull/1#discussion_r4535393562)

### PR #2 — MySQL, migration và auth

- **Tách PR theo mục đích.** Reviewer đề nghị tách phần Alembic/MySQL khỏi phần auth. Mô tả phải khớp thư viện thật trong code, ở đây là `pwdlib` với Argon2. Theo dõi góp ý từ PR trước để tránh lặp lỗi. [Review #2](https://github.com/hwolp/Fast_API_TaskHub/pull/2#pullrequestreview-5855722689)
- **Giữ ranh giới giữa các tầng.** Service ném lỗi nghiệp vụ, API ánh xạ sang HTTP. Dependency lấy user qua `AuthRepository`. Đặt JWKS trong auth router, dùng `TokenType` cho loại token và nạp key ở startup để tránh I/O đồng bộ trên đường xử lý từng request. Migration cần khớp FK và enum của model. PK đã có index nên bỏ index riêng trùng cột. [Key lúc startup](https://github.com/hwolp/Fast_API_TaskHub/pull/2#discussion_r4535478191), [Lỗi nghiệp vụ](https://github.com/hwolp/Fast_API_TaskHub/pull/2#discussion_r4535478208), [AuthRepository](https://github.com/hwolp/Fast_API_TaskHub/pull/2#discussion_r4535478244), [Index PK](https://github.com/hwolp/Fast_API_TaskHub/pull/2#discussion_r4535478251)

### PR #3 — RBAC và luồng API

- **Giữ diff đúng phạm vi.** PR phụ thuộc PR #2 thì đặt base lên branch của PR #2 để reviewer chỉ thấy phần mới. Tính năng công bố trong PR cần có điểm gọi qua router và test HTTP. [Review #3](https://github.com/hwolp/Fast_API_TaskHub/pull/3#pullrequestreview-5855815882), [Router và test](https://github.com/hwolp/Fast_API_TaskHub/pull/3#discussion_r4535550906)
- **Dùng chung quy tắc truy cập.** Gom bước tải resource và workspace role thay vì sao chép qua các service. Chặn gán `OWNER` qua API thành viên, bảo vệ admin khỏi tự xóa hoặc tự hạ quyền, xử lý lỗi ràng buộc DB khi xóa user và trả `409` nếu hai thao tác thêm member trùng nhau. Danh sách trả `{items, total}` trong body. [Tải resource và role](https://github.com/hwolp/Fast_API_TaskHub/pull/3#discussion_r4535550914), [Role OWNER](https://github.com/hwolp/Fast_API_TaskHub/pull/3#discussion_r4535550932), [Xóa user](https://github.com/hwolp/Fast_API_TaskHub/pull/3#discussion_r4535550953), [Race thêm member](https://github.com/hwolp/Fast_API_TaskHub/pull/3#discussion_r4535550959), [Response danh sách](https://github.com/hwolp/Fast_API_TaskHub/pull/3#discussion_r4535550966)

### PR #4 — Workspace và hợp đồng API

- **Mỗi điều kiện có nơi xử lý rõ ràng.** Schema đã từ chối `OWNER` với `422`, nên nhánh trả `400` trong service không thể tới được qua route đó. Reviewer đề nghị giữ một chỗ và tái sử dụng message. Khai báo mã lỗi thật của từng endpoint trong Swagger và dùng chung `PaginationDep`. [Validation role](https://github.com/hwolp/Fast_API_TaskHub/pull/4#discussion_r4610984390), [OpenAPI](https://github.com/hwolp/Fast_API_TaskHub/pull/4#discussion_r4610984399), [PaginationDep](https://github.com/hwolp/Fast_API_TaskHub/pull/4#discussion_r4610984404)
- **Kiểm thử cả hậu quả của thao tác.** VIEWER tự rời workspace phải nhận `204`, rồi GET workspace trả `404`. Tách phần tạo RSA key, migrate DB và override `get_db` thành hạ tầng test dùng chung. [Tự rời workspace](https://github.com/hwolp/Fast_API_TaskHub/pull/4#discussion_r4610984410), [Fixture dùng chung](https://github.com/hwolp/Fast_API_TaskHub/pull/4#discussion_r4610984417)

### PR #5 — Project, task và vòng đời dữ liệu

- **Bảo toàn quy tắc nghiệp vụ qua các thao tác liên quan.** Assignee phải là OWNER hoặc EDITOR đang hoạt động. Hạ EDITOR xuống VIEWER hoặc xóa thành viên cần unassign task trong cùng giao dịch. Thứ tự xử lý resource là `404` nếu không thấy, `403` nếu thiếu quyền ghi, `400` nếu project archived. Xác định rõ create, update, delete, unarchive và chính sách xóa project có dữ liệu con. [Review #5](https://github.com/hwolp/Fast_API_TaskHub/pull/5#pullrequestreview-5914850467), [Hạ role và unassign](https://github.com/hwolp/Fast_API_TaskHub/pull/5#discussion_r4581819592), [Xóa cascade](https://github.com/hwolp/Fast_API_TaskHub/pull/5#discussion_r4581819633)
- **Giảm truy vấn thừa trước khi thêm cache.** Lấy thông tin assignee bằng một query join và trả mã lỗi riêng cho inactive, sai role, ngoài workspace. Khi đã tải task cùng project, lấy luôn `project_status`. Giữ truy vấn đặc thù ở repo phù hợp và truyền nguyên object phân trang xuyên các tầng. [Query assignee](https://github.com/hwolp/Fast_API_TaskHub/pull/5#discussion_r4581819608), [Project status](https://github.com/hwolp/Fast_API_TaskHub/pull/5#discussion_r4581819599), [Phạm vi BaseRepository](https://github.com/hwolp/Fast_API_TaskHub/pull/5#discussion_r4581819596), [Tham số phân trang](https://github.com/hwolp/Fast_API_TaskHub/pull/5#discussion_r4581819623)

### PR #6 — Label, comment và chất lượng kiểm thử

- **Để DB giữ tính duy nhất.** Tên label unique theo `(project_id, name)`, cần cả model và migration. Dọn dữ liệu cũ trước khi thêm constraint, rollback lỗi trùng và trả `409`. Attach lặp cần có hành vi idempotent đã quy định. Detach khi chưa gắn trả `404`, còn GET task phải đọc lại được danh sách label đã lưu. [Review #6](https://github.com/hwolp/Fast_API_TaskHub/pull/6#pullrequestreview-5953021729), [Constraint](https://github.com/hwolp/Fast_API_TaskHub/pull/6#discussion_r4610982031), [Attach đồng thời](https://github.com/hwolp/Fast_API_TaskHub/pull/6#discussion_r4610982038), [Đọc lại label](https://github.com/hwolp/Fast_API_TaskHub/pull/6#discussion_r4610982057)
- **Đặt tên cho dữ liệu đi qua nhiều tầng.** Dùng `ScopedEntity` với các trường có tên thay tuple đọc theo vị trí. Tái sử dụng helper scope, gom dependency và OpenAPI response dùng chung, khớp kiểu trả về với schema. Validate ID dương, nội dung toàn khoảng trắng, giới hạn độ dài và màu hex. Test trạng thái DB sau attach/detach/cascade và kiểm tra quyền sau khi vai trò thay đổi. Reviewer cũng yêu cầu xác nhận theo đặc tả liệu VIEWER được bình luận, EDITOR bị hạ quyền còn được sửa bình luận cũ, attach trùng trả gì và danh sách sắp theo chiều nào. [NamedTuple](https://github.com/hwolp/Fast_API_TaskHub/pull/6#discussion_r4610982101), [Dependency và response](https://github.com/hwolp/Fast_API_TaskHub/pull/6#discussion_r4610982126), [Kiểu trả về](https://github.com/hwolp/Fast_API_TaskHub/pull/6#discussion_r4610982144), [Các ca test còn thiếu](https://github.com/hwolp/Fast_API_TaskHub/pull/6#discussion_r4610982181)

### PR #7 — Redis cache

PR triển khai cache danh sách task, TTL mặc định 60 giây và fallback về DB. Key gồm phiên bản dữ liệu, người dùng, vai trò, bộ lọc và trang. Phiên bản được đổi trong cùng transaction với cập nhật ảnh hưởng đến danh sách. Đây là nội dung triển khai và mô tả PR. [PR #7](https://github.com/hwolp/Fast_API_TaskHub/pull/7), [Task service](../app/services/task.py), [Migration 0004](../alembic/versions/0004_add_task_list_revision.py)

## 2. Bộ kiến thức phải nắm

Mỗi mục có một việc để thực hành và một tiêu chí để tự biết mình đã hiểu.

| Mã | Kiến thức | Áp dụng vào TaskHub | Tự kiểm |
| --- | --- | --- | --- |
| API-01 | **Hợp đồng HTTP và OpenAPI** | Khai báo request schema, response schema, mã lỗi và detail code cho từng route. `204` có body rỗng. | Viết bảng expected response cho một endpoint rồi đối chiếu Swagger và test. |
| API-02 | **Validation ở biên** | ID dương, tên có nội dung, enum hợp lệ. Với PATCH, phân biệt thiếu trường, gửi `null` và gửi giá trị mới. | PATCH bỏ `assignee_id` giữ nguyên, PATCH `null` bỏ gán, PATCH `title=null` trả `422`. |
| API-03 | **Quyền theo từng object** | Kiểm tra workspace qua quan hệ Project → Workspace. Danh sách lọc theo quyền tại truy vấn, count cũng dùng scope đó. | Ma trận gồm admin, owner, editor, viewer và non-member. Quyền của một task phải đúng cả ở list lẫn detail. |
| API-04 | **Hành vi lặp lại** | Xác định contract khi request retry. Attach label lại giữ đúng một liên kết. Detach chưa gắn trả `404` theo hợp đồng TaskHub. | Kiểm tra số liên kết thật trong DB và dữ liệu đọc lại qua GET. |
| CODE-01 | **Trách nhiệm từng tầng** | Router xử lý HTTP, service điều phối nghiệp vụ và transaction, repository truy vấn, database áp constraint. | Theo dõi một thao tác tạo task qua cả bốn tầng và chỉ ra nơi xử lý từng lỗi. |
| CODE-02 | **DRY theo quy tắc nghiệp vụ** | Tái sử dụng kiểm tra archived, nạp workspace scope và thông số pagination. Giữ riêng helper của từng domain nếu hành vi khác nhau. | Khi đổi max limit hoặc luật archived, đếm số nơi thật sự phải sửa. |
| CODE-03 | **Kiểu dữ liệu và tên có nghĩa** | Dùng `ScopedEntity.project_status` và enum thay tuple index hoặc string rải rác. | Thêm một trường vào object scope mà caller hiện tại vẫn đọc đúng trường cũ. |
| CODE-04 | **PR nhỏ và có thể review** | Một PR có mục đích rõ, ghi cách test, mô tả dữ liệu/migration nếu ảnh hưởng. Stacked PR dùng base của PR phụ thuộc. | Xem Files changed và nói được tại sao từng nhóm thay đổi thuộc PR này. |
| AUTH-01 | **Vòng đời xác thực** | Hash mật khẩu bằng Argon2 qua thư viện đã có. Nạp key ký JWT một lần, phân biệt access và refresh, lưu hash refresh token và cập nhật trạng thái token trong một giao dịch. | Test riêng token sai loại, user ngừng hoạt động, rotation và thu hồi phiên. |
| DB-01 | **Transaction, flush, commit, rollback** | `flush` gửi SQL trong giao dịch, `refresh` tải lại giá trị, `commit` hoàn tất giao dịch. Khôi phục session bằng rollback khi ghi lỗi. | Khi thêm một dòng thành công rồi thao tác kế tiếp lỗi, xác nhận toàn bộ nghiệp vụ không để lại trạng thái dở dang. |
| DB-02 | **Constraint và ghi đồng thời** | `UNIQUE` hoặc composite PK là nguồn đảm bảo tính duy nhất. Chỉ ánh xạ lỗi vi phạm đúng constraint dự kiến sang `409` hoặc no-op. | Kiểm tra gửi trùng tuần tự và song song trên DB mục tiêu. Dữ liệu cuối cùng phải duy nhất. |
| DB-03 | **FK và xóa có chủ đích** | `CASCADE` cho dữ liệu con thuộc vòng đời cha, `RESTRICT` cho lịch sử cần giữ, `SET NULL` cho liên kết tùy chọn. | Tạo dữ liệu con, xóa resource cha bằng API, rồi truy vấn DB để xác nhận từng tác động. |
| DB-04 | **Migration bảo toàn dữ liệu** | Kiểm thử upgrade từ revision trước trên DB có dữ liệu. Khi gộp label trùng, quyết định cách giữ các liên kết `task_labels`. | Có cùng bộ assertion cho schema, dữ liệu cũ và liên kết sau migration. |
| DB-05 | **Async SQLAlchemy và N+1** | Dùng một session trên mỗi luồng công việc. Eager-load labels cần serialize, dùng join cho dữ liệu quan hệ đơn cần ngay và `selectinload` cho collection phù hợp. | Đếm truy vấn khi lấy 1 task và 20 task. Kiểm tra số query lấy labels không tăng theo từng task. |
| DB-06 | **Ngày giờ và múi giờ** | Xác định hợp đồng UTC cho `due_date`, chuyển đổi đầu vào trước khi lưu và trả offset rõ ràng. | `09:00+07:00` và `02:00Z` phải biểu diễn cùng một thời điểm sau khi đọc từ DB. |
| PERF-01 | **Đo trước khi tối ưu** | Đo p50/p95 (phân vị độ trễ), số query/request và thời gian DB trên tập dữ liệu đại diện. Đo cả cache hit, miss và Redis lỗi. | Ghi lại baseline, một thay đổi và số liệu sau thay đổi trong cùng điều kiện. |
| PERF-02 | **Index theo truy vấn thực tế** | Với truy vấn thường lọc `project_id` rồi sort `id`, đọc index sẵn có và dùng `EXPLAIN` để kiểm tra plan. Đo chi phí ghi và kích thước khi thêm index. | Trình bày được truy vấn dùng index nào, đọc bao nhiêu row và có phải sort thêm không. |
| PERF-03 | **Search, filter và pagination** | Chuẩn hóa query params, dùng sort ổn định và thêm `id` để phân định khi giá trị sort trùng. Dùng offset khi cần số trang, cân nhắc cursor khi thường duyệt trang sâu. `total` phải phản ánh đúng filter và quyền. | Thử tìm theo từ khóa kết hợp status, filter ra rỗng, trang cuối và các item có cùng giá trị sort. |
| PERF-04 | **Cache-aside và cache key** | Cache kết quả đã áp quyền theo actor và tham số ảnh hưởng đến response. TTL giới hạn tuổi bản ghi cache, phiên bản dữ liệu giúp request mới bỏ qua bản cũ sau commit. | Hai người cùng query có thể ra hai kết quả. Thay nhãn hoặc quyền rồi đọc lại ngay cả khi key cũ vẫn tồn tại. |
| PERF-05 | **Chi phí và lỗi Redis** | Cache hit vẫn cần DB để xác thực và đọc phiên bản. Đo hit rate, thời gian client, số key và tỷ lệ fallback. Phiên bản toàn cục làm invalidation đơn giản nhưng có thể làm giảm hit rate giữa các workspace. | So sánh workload chủ yếu đọc với workload ghi liên tục. Đo timeout khi Redis ngắt kết nối. |
| TEST-01 | **Test hành vi qua API và trạng thái** | Dùng DB tạm, fixture chung, request thật qua ASGI. Kiểm tra status, body, dữ liệu sau mutation và quyền sau khi scope thay đổi. | Một test attach phải quan sát được label trên GET task và biến mất sau detach. |
| TEST-02 | **Test theo công nghệ triển khai** | SQLite giúp chạy nhanh. Thêm integration test MySQL và Redis khi kiểm tra byte limit, collation, locking, TTL và kết nối. | Chỉ ra case nào đã chạy thật trên dịch vụ mục tiêu và case nào dùng mock. |

Tài liệu tham khảo cho các mục bổ sung. [FastAPI dependency lifecycle](https://fastapi.tiangolo.com/advanced/advanced-dependencies/), [SQLAlchemy Session](https://docs.sqlalchemy.org/en/20/orm/session_basics.html), [SQLAlchemy async](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html), [SQLite foreign keys](https://www.sqlite.org/foreignkeys.html), [Alembic batch migrations](https://alembic.sqlalchemy.org/en/latest/batch.html), [MySQL EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html), [MySQL composite indexes](https://dev.mysql.com/doc/refman/8.4/en/multiple-column-indexes.html), [Redis cache-aside](https://redis.io/docs/latest/develop/use-cases/cache-aside/), [GitHub đổi base branch](https://docs.github.com/en/pull-requests/how-tos/create-pull-requests/changing-the-base-branch-of-a-pull-request)

## 3. Lộ trình thực hành trên TaskHub

1. **Tuần 1 · API contract và fixture.** Lập ma trận quyền cho Project và Task. Thêm test cho tên toàn khoảng trắng, PATCH khác nhau giữa thiếu trường và `null`, và người dùng tự rời workspace. Soát một route cùng Swagger. Hoàn thành khi các ca chuyển trạng thái đều có assertion sau thao tác.
2. **Tuần 2 · DB và dữ liệu cũ.** Lần theo luồng hạ role → unassign → commit. Tạo DB tạm ở revision `0002` có label đã gắn task, rồi kiểm tra liên kết sau khi upgrade. Thực hành xác định đúng lỗi unique, FK và lỗi giao dịch. Hoàn thành khi mô tả được dữ liệu nào phải giữ và test chứng minh điều đó.
3. **Tuần 3 · Search và hiệu năng.** Thiết kế bộ lọc task có typed query params. Dùng dữ liệu giả đủ lớn để so sánh query theo project và status, có và không có index phù hợp. Dùng `EXPLAIN` và ghi p95, số query và các query plan. Hoàn thành khi chọn được index dựa trên workload đã đo.
4. **Tuần 4 · Redis và vận hành.** Chạy cùng một workload với cache tắt, cache nóng và Redis lỗi. Kiểm thử cache sau khi sửa task, đổi nhãn và mất quyền. Thử workload ghi ở một workspace và đọc ở workspace khác để đo tác động của phiên bản toàn cục. Hoàn thành khi giải thích được số query tiết kiệm, tỷ lệ hit và độ trễ khi fallback.

### Bài tự review từ code hiện tại

- **Hợp đồng tạo Project.** Trên SQLite tạm, admin tạo Project trong workspace không tồn tại nhận `500`. Viết regression test mong đợi `404`, rồi kiểm tra tồn tại workspace trước khi áp vai trò hiệu lực. [Project service](../app/services/project.py), [Workspace role](../app/repositories/base.py), [Chính sách effective role](../app/core/permissions.py)
- **Validation và UTC.** SQLite tạm chấp nhận title toàn khoảng trắng. Gửi `2026-11-19T09:00:00+07:00` rồi đọc lại nhận `2026-11-19T09:00:00`. Đây là hai ca để viết test trước khi chuẩn hóa title và UTC. [Task schema](../app/schemas/task.py), [Task model](../app/models/task.py)
- **Migration trên dữ liệu có sẵn.** Khi chạy thử SQLite từ `0002` lên `0003` với một label duy nhất đã gắn task, label vẫn còn nhưng liên kết giảm từ 1 xuống 0. Viết regression test giữ liên kết của label không trùng và xác định cách chuyển liên kết khi gộp các label trùng. [Migration 0003](../alembic/versions/0003_add_unique_constraint_to_labels.py), [Alembic và FK khi batch migration](https://alembic.sqlalchemy.org/en/latest/batch.html#dealing-with-referencing-foreign-keys)
- **Attach và mã lỗi.** Repo attach hiện bắt toàn bộ `IntegrityError`. Viết test phân biệt liên kết đã tồn tại với các lỗi ràng buộc khác. Với attach lặp đã thành công trước đó, cân nhắc chỉ đổi phiên bản cache khi liên kết thật sự thay đổi. [Label repository](../app/repositories/label.py), [Label service](../app/services/label.py)
- **Tái sử dụng pagination và fixture.** Task, Label và Comment đã truyền object phân trang. Project và Workspace vẫn truyền riêng page/limit. Các bộ test còn lặp phần tạo key và chuẩn bị DB. Đây là hai refactor nhỏ có tiêu chí hoàn thành rõ ràng. [Project endpoint](../app/api/v1/endpoints/project.py), [Workspace endpoint](../app/api/v1/endpoints/workspace.py), [Task tests](../tests/test_rbac.py), [Workspace tests](../tests/test_workspace.py)

## 4. Checklist trước khi mở PR

- [ ] Mô tả thay đổi, giới hạn phạm vi và ghi lệnh kiểm thử.
- [ ] API chạy đến đúng repository và database. Request, response và OpenAPI khớp.
- [ ] Quyền được áp ở cả list lẫn detail. Test member đổi role hoặc rời workspace.
- [ ] Thao tác nhiều bước commit một lần. Test cho lỗi giữa chừng và retry nếu có.
- [ ] Model và migration khớp. Upgrade được trên dữ liệu cũ. Cascade có test hậu quả.
- [ ] Validation nhất quán giữa query, path và body. Mã lỗi nghiệp vụ có tên rõ ràng.
- [ ] Thay đổi hiệu năng có baseline và số liệu sau khi sửa. Thay đổi cache có test hit, miss, Redis lỗi và invalidation.
- [ ] Bỏ phần ngoài phạm vi. Nếu PR phụ thuộc PR khác, kiểm tra base và Files changed.

### Lệnh kiểm thử tại workspace

```powershell
python -m pip install -r requirements-dev.txt pytest
python -m pytest -q
python -m pytest -q tests/test_rbac.py -k task_list_cache
```

Bộ test hiện có dùng request qua ASGI và DB SQLite tạm. Test cache trong repo giả lập Redis. Các bài đo MySQL và Redis thật dùng dịch vụ và dữ liệu test riêng. [Hướng dẫn dự án](../README.md), [Fixture cache](../tests/test_rbac.py)
