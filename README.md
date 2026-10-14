# Web tổng hợp Facebook Page (Vercel + đăng nhập Supabase)

Đọc 3 bảng `fb_posts`, `fb_post_metrics`, `fb_page_daily` từ Supabase và hiển thị dashboard.
Khoá Supabase chỉ nằm ở server (biến môi trường Vercel). Đăng nhập bằng bảng `web_users` + cookie phiên.

## 1. Tạo bảng user
Supabase > SQL Editor > chạy `supabase_web_users.sql`.

## 2. Tạo tài khoản (trên máy bạn, cần .env có SUPABASE_URL, SUPABASE_SERVICE_KEY)
```bash
pip install bcrypt requests python-dotenv
python create_user.py ten_dang_nhap        # tạo user hoặc đổi mật khẩu
python create_user.py ten_dang_nhap --off  # khoá tài khoản
```

## 3. Deploy Vercel
```bash
npm i -g vercel
vercel            # lần đầu, trả lời các câu hỏi
vercel env add SUPABASE_URL
vercel env add SUPABASE_SERVICE_KEY
vercel env add SESSION_SECRET     # chuỗi ngẫu nhiên dài: python -c "import secrets;print(secrets.token_urlsafe(48))"
vercel --prod
```
(Hoặc đẩy lên GitHub rồi Import Project trên vercel.com, đặt 3 biến ở Settings > Environment Variables.)

## Chạy thử local
```bash
pip install -r requirements.txt uvicorn
uvicorn web:app --port 8090      # cần .env có SUPABASE_URL, SUPABASE_SERVICE_KEY, SESSION_SECRET
```

## Ghi chú
- Sai mật khẩu 5 lần thì khoá user 15 phút. Phiên đăng nhập 7 ngày (`SESSION_DAYS`); khoá user bằng `--off` chỉ chặn đăng nhập mới, phiên đang mở hết hạn theo ngày. Muốn đá ngay thì đổi `SESSION_SECRET`.
- Số liệu cache 60 giây mỗi instance (`WEB_CACHE_SECONDS`).
- "Tổng người xem" là cộng theo từng bài nên có thể trùng người giữa các bài.
- `fb_to_supabase.py` (cron mỗi ngày) vẫn chạy trên VPS, không thuộc project này.
