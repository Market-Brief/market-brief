# market-brief

Bản tóm tắt chứng khoán Việt Nam. Lõi tạo một `Board`. Nguồn giá, nơi lưu và kênh phát là adapter, khai báo trong `src/market_brief/app/wiring.py` và bật bằng tên trong `config/runtime.yaml`.

Đợt này bật nguồn giá DNSE, MySQL và terminal. Gói `vnstock` trên PyPI đang bị quarantine nên mỗi nguồn gọi thẳng API công khai của nhà cung cấp.

Mỗi bản tóm tắt hiện cùng lúc dnse, vci và kbs. DNSE lấy nến ngày. VCI và KBS lấy giá khớp trong phiên; VNINDEX và VN30 lấy nến ngày đang chạy vì bảng giá của hai nguồn đó không kèm chỉ số.

## Chạy

```bash
docker compose up -d
uv sync --extra dev
uv run market-brief brief
uv run market-brief brief --symbol VCB
uv run market-brief brief --lang en --symbol VCB
uv run market-brief help
```

`--lang` nhận `vn` hoặc `en`. Không khai báo `sources` thì bảng gồm mọi nguồn trong `MARKET_DATA`: dnse, vci và kbs. Muốn tắt một nguồn, liệt kê phần còn lại:

```yaml
sources:
  - vci
  - kbs
```

Danh sách mã nằm trong `config/watchlist.yaml`. Giá cổ phiếu từ DNSE được đổi từ nghìn đồng sang đồng trong `adapters/market_data/mapping.py`. Chỉ số giữ đơn vị điểm.

MySQL chạy trong Docker. `docker compose up -d` đọc biến `MYSQL_*` từ `.env`. Mẫu nằm trong `.env.example`. Schema do migration của `market-brief-api` tạo. App ghi vào `instruments` và `quotes` khi các nguồn `dnse`, `vci`, `kbs` đã có trong bảng `sources`.

## Bot Slack

Bot dùng Socket Mode, nên máy chạy lệnh không cần URL công khai. Lệnh `brief` vẫn in ra terminal. Lệnh `slack` nghe tin nhắn và trả lại cùng một bản tóm tắt.

1. Tạo app tại [api.slack.com/apps](https://api.slack.com/apps) bằng manifest `config/slack-manifest.yaml`.
2. Trong **Basic Information → App-Level Tokens**, tạo token scope `connections:write`. Đó là `SLACK_APP_TOKEN` (`xapp-`).
3. **Install App** vào workspace. Bot token là `SLACK_BOT_TOKEN` (`xoxb-`).
4. Copy `.env.example` thành `.env` và điền hai token cùng `SLACK_CHANNEL`. File `.env` không được commit.
5. Trong đúng một kênh, gõ `/invite @Market Brief`. ID kênh nằm cuối phần chi tiết kênh.

```bash
uv sync --extra dev
uv run market-brief slack
```

Bot chỉ trả lời trong kênh ghi ở `SLACK_CHANNEL`. Gõ `/brief` để xem hướng dẫn. `/brief VCB` lấy một mã. Nhắc `@Market Brief brief` để lấy cả watchlist.

Thêm `vn` hoặc `en` để chọn ngôn ngữ. Ví dụ: `@Market Brief brief VCB en`. Bảng luôn gồm dnse, vci và kbs.

Muốn `market-brief brief` đăng thêm vào cùng kênh đó, thêm `slack` vào `publish`:

```yaml
publish:
  - terminal
  - slack
```

## Thêm một kênh phát

1. Tạo `src/market_brief/adapters/publish/<tên>.py` với `name` và `publish(board)`.
2. Thêm class vào dict `PUBLISHERS` trong `app/wiring.py`.
3. Thêm tên vào `publish` trong `config/runtime.yaml`.

Tên không có trong dict thì lệnh dừng và in các tên hợp lệ. Đây là số liệu công khai, không phải khuyến nghị mua bán.
