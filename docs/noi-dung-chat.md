# Nội dung chat Market Brief

Ghi lại cuộc làm việc ngày 20/10/2026. File này tóm tắt quyết định, việc đã làm và câu trả lời trong chat. Token Slack và mật khẩu tài khoản không được ghi lại.

Ba project nằm cạnh nhau trong thư mục `2026`:

| Project | Vai trò |
|---|---|
| `market-brief` | Python. Lấy giá, ghi MySQL, bot Slack, lệnh terminal |
| `market-brief-api` | .NET 10. Đăng nhập, dashboard, đọc MySQL cho trang web |
| `market-brief-web` | Vite + React. Giao diện đăng nhập, bảng giá, tích hợp |

## Sản phẩm

- Ngôn ngữ `vn` hoặc `en`. Mặc định tiếng Việt.
- Mỗi bản tóm tắt luôn có đủ ba nguồn `dnse`, `vci`, `kbs`. Không chọn nguồn theo từng lần gọi.
- Watchlist theo dõi, không phải khuyến nghị mua: VNINDEX, VN30, VCB, TCB, FPT, HPG, MWG, VNM, VIC, VJC, SSI, GAS.
- Disclaimer tiếng Việt: «Số liệu công khai, không phải khuyến nghị mua bán.»
- Disclaimer tiếng Anh: «Public market figures, not a recommendation to buy or sell.»
- Giá cổ phiếu DNSE đổi từ nghìn đồng sang đồng trước khi lưu. VCI và KBS đã là đồng. Chỉ số giữ đơn vị điểm.
- Nhóm số: tiếng Việt `56.700` và `+1,25%`. Tiếng Anh `56,700` và `+1.25%`. Trang web hiện in chuỗi số thô từ API.
- Biểu đồ nến là việc sau, chỉ OHLC ngày từ DNSE. VCI và KBS không phải nguồn nến. Chưa tạo bảng `candles` và `ingestions`.
- Trình duyệt không gọi DNSE, VCI, KBS. Frontend chỉ gọi API .NET.

## Python và Slack

- Kiến trúc hexagonal: domain không có IO. Cổng là `MarketData`, `Store`, `Publisher`. Nối dây ở `src/market_brief/app/wiring.py`.
- Lệnh: `brief`, `slack`, `help`. `/brief` trống hoặc `/help` hiện hướng dẫn.
- Bot Slack dùng Socket Mode, một process, chỉ trả lời trong `SLACK_CHANNEL`. Tên bot `@Market Brief`.
- Manifest nằm ở `config/slack-manifest.yaml`. Lệnh slash: `/brief`, `/help`.
- `config/runtime.yaml`: store `mysql`, publish `terminal`.
- `config/watchlist.yaml`: 12 mã ở trên.
- Không thêm gói `vnstock`. Adapter gọi HTTP chuẩn, SSL mặc định.
- Chỉ chạy một process `uv run market-brief slack`. Đổi code Python thì tắt bot rồi chạy lại.
- Backend .NET không nối Slack. Toàn bộ lệnh Slack nằm trong project Python.

## MySQL

- Docker, image `mysql:8.4`, container `market-brief-mysql`.
- Host `127.0.0.1`, cổng `3306`, database `market_brief`.
- User và mật khẩu local nằm trong `.env.example`. Mật khẩu root chỉ dùng trong container.
- Test Python vẫn dùng SQLite để không cần server. File sqlite cũ không được chuyển sang MySQL.
- Schema do migration EF của `market-brief-api` tạo. Python không còn `CREATE TABLE` bảng giá cũ.
- Python ghi `instruments` và `quotes` khi ba nguồn `dnse`, `vci`, `kbs` đã có trong bảng `sources`.

## Bảng dữ liệu

Sự kiện thị trường dùng chung. Dữ liệu của từng user là watchlist và ngôn ngữ.

Bảng nghiệp vụ, cột `snake_case`:

- `instruments`: ticker, sàn, tên, `equity` hoặc `index`, `vnd` hoặc `point`. Unique `(ticker, exchange)`.
- `sources`: `dnse` id 1 có nến, `vci` id 2 không, `kbs` id 3 không.
- `watchlists`, `watchlist_items`. Unique `(user_id, name)`, `(watchlist_id, instrument_id)`, `(watchlist_id, position)`.
- `quotes`: `instrument_id`, `source_id`, `observed_at` UTC, `price` lớn hơn 0, `change_percent` có thể âm, `volume` null hoặc không âm, `fetched_at` UTC. Unique `(instrument_id, source_id, observed_at)`.
- Tiền dùng `DECIMAL`. Thời điểm UTC dùng `DATETIME(6)`.
- Bảng giá trên dashboard là một câu query, thứ tự theo vị trí watchlist.

Bảng `quotes` cũ bị khóa chính `(ticker, as_of)` nên VNINDEX và VN30 của vci bị kbs ghi đè khi cùng mốc thời gian. Migration `ResearchModel` đổi bảng cũ thành `quotes_legacy`, tạo bảng `quotes` mới, seed nguồn, rồi chép 34 dòng sang UTC. Không xóa `quotes_legacy`. Hai dòng chỉ số vci đã mất được lấy lại bằng `uv run market-brief brief`.

Xóa user thì xóa watchlist, mục trong watchlist và refresh token. Không xóa giá.

## Tài khoản và bảng AspNet

Đăng nhập dùng thư viện có sẵn `Microsoft.AspNetCore.Identity.EntityFrameworkCore` 9.0.21. `MarketBriefDbContext` kế thừa `IdentityDbContext<AppUser>`.

Bảy bảng `AspNetUsers`, `AspNetRoles`, `AspNetUserRoles`, `AspNetUserClaims`, `AspNetUserLogins`, `AspNetUserTokens`, `AspNetRoleClaims` là tên mặc định của thư viện, không phải tên tự đặt. `AspNetUsers` có thêm `DisplayName` và `Language` (`vn` hoặc `en`). Các bảng role đang trống vì chưa gán quyền. Nên giữ tên `AspNet`: nhiều hệ thống .NET lớn giữ nguyên. Doanh nghiệp đổi tên khi chuẩn DBA bắt buộc, hoặc đăng nhập qua Entra ID / Okta và không tự giữ mật khẩu.

`refresh_tokens` lưu SHA-256 của token, không lưu token thô. Access token JWT sống 15 phút, claim `sub`. Refresh token là cookie httpOnly `mb_refresh`, path `/auth`, SameSite Lax, Secure tắt vì local đang HTTP. Đăng xuất ghi `revoked_at`. Làm mới thì xoay token.

Endpoint:

- `POST /auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`
- `GET /dashboard` cần đăng nhập
- `GET /health` không cần đăng nhập
- `GET /board` đã bỏ

Đăng ký tạo watchlist tên «Mặc định» với mọi instrument, thứ tự theo watchlist mặc định. Mật khẩu: tối thiểu 8 ký tự, chữ hoa, chữ thường, chữ số, ký tự đặc biệt. Mật khẩu thiếu chữ thường bị Identity từ chối.

Tài khoản đang dùng: `dex-h68@mb.com`, tên hiển thị «Nhà nghiên cứu». Mật khẩu đã đổi qua Identity và không ghi trong file này. Tài khoản thử `analyst@marketbrief.local` không còn đăng nhập được. Watchlist giữ trên cùng user. Phiên cũ bị thu hồi.

Khóa ký JWT local nằm trong `appsettings.Development.json`. Đăng ký đặt email đã xác nhận vì chưa có mailer. Khi ra môi trường dùng chung: chuyển khóa sang secret store, xác nhận email, cookie chỉ qua HTTPS.

## Backend .NET

- SDK 10.0.401. Pomelo 9 với EF Core 9.0.21 vì Pomelo chưa có gói EF Core 10.
- Project: Domain, Application, Infrastructure, Api. Domain không tham chiếu ASP.NET hay EF.
- Không generic repository, không MediatR, không AutoMapper. JSON `snake_case`.
- Không tự migrate lúc khởi động. Lệnh là `dotnet ef database update`.
- API nghe `http://127.0.0.1:8080`.
- CORS cho `http://127.0.0.1:5173` và `http://localhost:5173`, có cookie.

## Frontend

- React 19, TypeScript, Vite, Tailwind 4, TanStack Query, React Router.
- Dev server `http://127.0.0.1:5173`.
- `/login`, `/register`, `/` là bảng giá, `/integrations` là tích hợp Slack.
- Access token trong `sessionStorage`. Refresh bằng cookie, `credentials: 'include'`. Hết hạn thì làm mới một lần, rồi về trang đăng nhập.
- Bảng giá theo thứ tự symbol từ API. Ô thiếu nguồn hiện gạch ngang.
- Sidebar bên trái: Market Brief, Bảng giá, Tích hợp, tên user, đăng xuất.
- Sidebar thu gọn được. Thu gọn còn dấu B và T, bấm vẫn chuyển trang. Trạng thái lưu ở `localStorage` khóa `mb_sidebar`.

Trang Tích hợp đọc `GET /integrations/slack`. Hiện ứng dụng Market Brief, bot `@Market Brief`, Socket Mode, ID kênh, token đã đặt hay chưa, và các lệnh `/brief`, `/help`, `@Market Brief brief`. Không trả giá trị token. Bot vẫn chạy bằng `uv run market-brief slack`.

## Chưa làm

- Bảng nến và ingestions.
- Ghi chú nghiên cứu, cảnh báo, role.
- Xóa `quotes_legacy`.
- Định dạng số trên web theo locale.
- Commit git. Chưa được yêu cầu.
