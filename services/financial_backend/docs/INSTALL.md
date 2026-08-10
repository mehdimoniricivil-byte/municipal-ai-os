# نصب آزمایشی

```bash
cp .env.example .env
# SECRET_KEY و رمز مدیر را تغییر دهید
docker compose up --build -d
docker compose logs -f api
```

آدرس‌ها:

- Login: `/dashboard/login.html`
- Swagger: `/docs`
- Health: `/api/v1/health`

این نسخه هنوز از `Base.metadata.create_all` استفاده می‌کند. پیش از نصب Production باید baseline Alembic ایجاد و Migration اجرا شود.
