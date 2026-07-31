# Shahrdari AI Backend — v0.5.0 RC Foundation

هسته سامانه مدیریت وصول، هزینه، دستمزد، صورت‌وضعیت و پرداخت کارگزاری شهرداری.
این نسخه روی سورس v0.4.0 توسعه یافته و زیرساخت انتشار آزمایشی را اضافه می‌کند.

## قابلیت‌های اصلی

- احراز هویت JWT، نقش‌ها و Permission Engine
- بارگذاری و اعتبارسنجی فایل وصول کارشناسان
- داشبورد مبتنی بر داده پایگاه داده
- قرارداد، صورت‌وضعیت، گردش کار شش‌مرحله‌ای و چندپرداختی
- Audit Log و نسخه‌بندی صورت‌وضعیت
- موتور محاسبات مالی متمرکز و قابل تست
- Health Check تفصیلی برای پایگاه داده، Storage، دیسک و حافظه
- Alembic baseline و اسکریپت پشتیبان‌گیری

## اجرای توسعه

```bash
cp .env.example .env
docker compose up --build
```

- ورود: `http://localhost:8000/dashboard/login.html`
- Swagger: `http://localhost:8000/docs`
- Liveness: `GET /api/v1/live`
- Health: `GET /api/v1/health`

در محیط توسعه `AUTO_CREATE_SCHEMA=true` است. در staging/production آن را `false`
قرار دهید و migration را اجرا کنید:

```bash
alembic upgrade head
```

برای دیتابیس موجود v0.4.0 ابتدا Backup بگیرید و سپس baseline را stamp کنید:

```bash
alembic stamp 0001_v050
```

جزئیات در `docs/MIGRATION_V0.5.0.md` آمده است.

## تست

```bash
pytest -q
python -m compileall -q app
```

## استقرار ایزوله staging روی سرور موجود

اسکریپت staging یک دیتابیس و نقش جدا در کانتینر PostgreSQL موجود می‌سازد،
سرویس را فقط روی `127.0.0.1:8002` بالا می‌آورد و به نسخه فعال پورت ۸۰۰۱
دست نمی‌زند. رمزهای تصادفی فقط روی خود سرور ذخیره می‌شوند.

```bash
./scripts/deploy_staging.sh
./scripts/publish_staging_proxy.sh
```

مسیر عمومی آزمایش:
`/backend-v1-staging/dashboard/login.html`

## هشدار بهره‌برداری

تا پایان تست پذیرش در محیط staging، فایل واقعی سازمانی وارد نشود. رمز اولیه و
`SECRET_KEY` پیش از هر استقرار تغییر کند.
