# مهاجرت از v0.4.0 به v0.5.0

## پیش‌نیاز

1. توقف سرویس API.
2. تهیه نسخه پشتیبان از PostgreSQL و پوشه Storage.
3. نگهداری یک نسخه از فایل `.env` فعلی.

## پایگاه داده موجود v0.4.0

این نسخه ساختار جداول مالی v0.4.0 را تغییر نمی‌دهد و یک Alembic baseline اضافه
می‌کند. چون جداول از قبل با `create_all` ساخته شده‌اند، نباید migration baseline
را روی آن‌ها اجرا کرد. فقط آن را ثبت کنید:

```bash
alembic stamp 0001_v050
```

سپس در `.env`:

```env
AUTO_CREATE_SCHEMA=false
```

## نصب تازه

```bash
alembic upgrade head
```

## کنترل بعد از مهاجرت

```bash
python -m compileall -q app
pytest -q
curl -f http://localhost:8000/api/v1/live
curl -f http://localhost:8000/api/v1/health
```

در پاسخ Health باید `database` و `storage` برابر `ok` باشند.
