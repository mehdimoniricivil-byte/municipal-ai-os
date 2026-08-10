# API

Base path: `/api/v1`

## Authentication

- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`
- `GET /auth/me`
- `POST /auth/change-password`

## Dashboard

- `GET /dashboard/summary?year=1405&month=4`

## Collections

- `GET /collections?year=1405&month=4`

## Expenses

- `POST /expenses` — نیازمند `expense.create`
- `GET /expenses?year=1405&month=4` — نیازمند `expense.view`

## Audit

`GET /audit`

مجوز: `audit.view`

پارامترهای اختیاری:

- `module`
- `action`
- `user_id`
- `limit` از ۱ تا ۵۰۰، پیش‌فرض ۱۰۰
- `offset`

نمونه:

```http
GET /api/v1/audit?module=expenses&action=create&limit=50
Authorization: Bearer <access-token>
```

## Collection Upload — v0.3.0

### Validate and preview

`POST /upload/validate`

مجوز: `collection.upload`

فرمت درخواست: `multipart/form-data`

- `region_id`
- `year`
- `month`
- `file` (`xlsx` یا `xls`، حداکثر ۲۰ مگابایت)

فایل فقط در صورت نبود خطا آماده ثبت نهایی می‌شود. کارشناس تنها می‌تواند برای واحد متصل به حساب خودش فایل بفرستد.

### Final import

`POST /upload/{upload_id}/import`

رکوردها در یک تراکنش ثبت می‌شوند و سپس جمع ماهانه داشبورد به‌روزرسانی می‌شود.

### History

`GET /upload/history`

مجوز: `collection.upload_status`

کارشناس فقط سوابق واحد خودش را می‌بیند.

### Upload detail

`GET /upload/{upload_id}`

## Statement Management — v0.4.0

- `POST /api/v1/statements/contracts` ایجاد قرارداد
- `GET /api/v1/statements/contracts` فهرست قراردادها
- `POST /api/v1/statements` ایجاد صورت‌وضعیت از داده‌های وصول و دستمزد
- `GET /api/v1/statements` فهرست و فیلتر صورت‌وضعیت‌ها
- `GET /api/v1/statements/{id}` جزئیات، گردش کار و پرداخت‌ها
- `POST /api/v1/statements/{id}/workflow` تأیید یا رد مرحله جاری
- `POST /api/v1/statements/{id}/payments` ثبت پرداخت

همه Endpointها نیازمند Bearer JWT و مجوز متناسب هستند.
