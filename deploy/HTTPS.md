# HTTPS cho web Data Warehouse: https://data.pgi.com.vn

Đường đi của request:

```
Người dùng ──https:443──> Caddy (container "caddy") ──http──> django:8000 (gunicorn)
              http:80 ───> Caddy chuyển sang https://data.pgi.com.vn
```

- Cấu hình proxy: `deploy/caddy/Caddyfile`. Service `caddy` chỉ có trong `docker-compose.prod.yml`.
- Chứng chỉ: dùng wildcard `*.pgi.com.vn` do IT cấp, đặt trong `deploy/caddy/certs/`. Thư mục này **không commit**, đã có trong `.gitignore`.
- Trang `/admin/` của Django chỉ mở từ mạng nội bộ. Truy cập từ internet sẽ nhận 404.
- Đăng nhập sai 5 lần (cùng tài khoản và IP) hoặc 20 lần (cùng IP) trong 15 phút sẽ bị khóa tạm 15 phút. Nhật ký ghi trong bảng `LogActivity`.

## 1. Việc của IT

| # | Việc | Ghi chú |
|---|---|---|
| 1 | Cấp chứng chỉ **`*.pgi.com.vn`** gồm 2 file: `fullchain.crt` (chứng chỉ và chuỗi trung gian) và `privkey.key` (không đặt mật khẩu) | `*.pgi.vn` **không** dùng được cho `data.pgi.com.vn` |
| 2 | DNS **nội bộ**: bản ghi A `data.pgi.com.vn` trỏ về `192.168.68.123` | Máy trong công ty đi thẳng vào server, không vòng ra internet |
| 3 | DNS **công cộng**: bản ghi A `data.pgi.com.vn` trỏ về IP public tĩnh của công ty | |
| 4 | Router/firewall: chuyển tiếp **443** và **80** từ IP public vào `192.168.68.123` | **Không** mở 8000, 8089 (Airflow), 14333 (SQL Server), 22 (SSH) |
| 5 | Firewall trên server (ufw): chỉ cho 80 và 443 từ ngoài vào | 8000 và 8089 chỉ cho mạng LAN, hoặc đóng hẳn |
| 6 | Gửi ngày hết hạn của chứng chỉ | Khi gia hạn: thay 2 file rồi `restart caddy` (xem mục 4) |

Nên làm theo thứ tự: mục 1, 2 → triển khai và thử trong LAN → mục 3, 4, 5.

## 2. Triển khai trên server

```bash
cd ~/data-warehouse
git pull origin main

# 2.1 Chép chứng chỉ IT cấp vào đúng tên file
cp /duong-dan/fullchain.crt deploy/caddy/certs/fullchain.crt
cp /duong-dan/privkey.key   deploy/caddy/certs/privkey.key
chmod 644 deploy/caddy/certs/fullchain.crt
chmod 600 deploy/caddy/certs/privkey.key
```

2.2 Sửa `.env`. Thêm hoặc sửa các dòng sau, giữ nguyên các dòng khác:

```
DEBUG=False
SECRET_KEY=<chuỗi ngẫu nhiên dài; tạo bằng: python3 -c "import secrets; print(secrets.token_urlsafe(50))">
HTTPS_ENABLED=True
ALLOWED_HOSTS=data.pgi.com.vn,192.168.68.123,localhost
CSRF_TRUSTED_ORIGINS=https://data.pgi.com.vn
SITE_DOMAIN=data.pgi.com.vn
# Tự đăng xuất sau 12 giờ (mặc định 14 ngày)
SESSION_COOKIE_AGE=43200
```

> Lưu ý: khi `HTTPS_ENABLED=True`, cookie đăng nhập chỉ gửi qua HTTPS, nên **không đăng nhập được qua `http://192.168.68.123:8000` nữa**. Mọi người chuyển sang dùng `https://data.pgi.com.vn` (cần DNS nội bộ ở mục 1.2).
> Đổi `SECRET_KEY` sẽ đăng xuất toàn bộ người dùng đang đăng nhập (một lần).

```bash
# 2.3 Build lại django và bật caddy
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build django caddy

# 2.4 Kiểm tra
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs caddy | grep -i -E "error|serving"
curl -sI https://data.pgi.com.vn/login/ | head -5     # phải ra HTTP/2 200 (chạy trên server hoặc máy trong LAN)
curl -sI http://data.pgi.com.vn/ | head -3            # phải ra 301 sang https://
```

2.5 Khi chạy ổn, đóng cổng 8000 ra ngoài: đặt `DJANGO_BIND_ADDR=127.0.0.1` trong `.env` rồi chạy lại lệnh 2.3. Sau 1–2 tuần ổn định, tăng `SECURE_HSTS_SECONDS=31536000` (1 năm).

## 3. Chạy thử khi chưa có chứng chỉ

Đặt `CADDY_TLS_ARGS=internal` trong `.env` rồi chạy lại lệnh 2.3. Caddy sẽ tự tạo chứng chỉ tạm. Trình duyệt sẽ cảnh báo "không an toàn", chỉ dùng để thử. Khi đã có chứng chỉ thật thì xóa dòng này.

## 4. Gia hạn chứng chỉ (mỗi năm)

```bash
cp fullchain-moi.crt deploy/caddy/certs/fullchain.crt
cp privkey-moi.key   deploy/caddy/certs/privkey.key
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart caddy
```

## 5. Gỡ lỗi nhanh

| Hiện tượng | Nguyên nhân thường gặp |
|---|---|
| `caddy` khởi động lỗi `no such file ... /certs/...` | Chưa chép chứng chỉ, hoặc sai tên file (phải là `fullchain.crt`, `privkey.key`) |
| Trình duyệt báo chứng chỉ sai tên | Đang vào bằng IP (`https://192.168.68.123`). Phải vào bằng tên miền |
| Trang báo `Bad Request (400)` | Thiếu `data.pgi.com.vn` trong `ALLOWED_HOSTS` |
| Đăng nhập báo lỗi CSRF (403) | Thiếu hoặc sai `CSRF_TRUSTED_ORIGINS=https://data.pgi.com.vn` |
| Đăng nhập xong lại quay về trang login | Đang vào bằng `http://...:8000` trong khi `HTTPS_ENABLED=True`. Dùng `https://data.pgi.com.vn` |
| Trong công ty không vào được, 4G vào được | Thiếu DNS nội bộ (mục 1.2), hoặc router không hỗ trợ NAT loopback |
