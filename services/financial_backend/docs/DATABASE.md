# پایگاه داده

## جدول‌های فعلی

- `regions`: واحدهای عملیاتی فعلی
- `operational_calendar`: تقویم عملیاتی
- `monthly_collections`: وصول تجمیعی ماهانه
- `monthly_targets`: اهداف ماهانه
- `wage_rule_sets`, `wage_brackets`, `wage_calculations`: قواعد و محاسبات دستمزد
- `expenses`: هزینه مستقیم و مشترک
- `users`, `refresh_tokens`, `login_audits`: احراز هویت
- `audit_logs`: ردپای تغییرات عملیاتی

## audit_logs

| ستون | توضیح |
|---|---|
| id | شناسه داخلی |
| user_id | کاربر انجام‌دهنده |
| module | نام ماژول |
| action | نوع عملیات |
| record_type | نوع رکورد |
| record_id | شناسه رکورد |
| old_value | مقدار قبلی به صورت JSON متنی |
| new_value | مقدار جدید به صورت JSON متنی |
| ip_address | IP درخواست |
| user_agent | مرورگر/عامل کاربر |
| created_at | زمان ثبت |

Audit Log فقط افزایشی است و Endpoint حذف یا ویرایش ندارد.

## برنامه Migration بعدی

1. افزودن Alembic و ثبت baseline از ساختار موجود.
2. تغییر نام کنترل‌شده `regions` به `operational_units`.
3. افزودن `collection_uploads` و `collection_records`.
4. افزودن جدول‌های قرارداد، صورت‌وضعیت، گردش کار، پرداخت و پیوست.

## collection_uploads — v0.3.0

متادیتای هر فایل، هش SHA-256، دوره، واحد، نتیجه اعتبارسنجی، کاربر بارگذار و وضعیت `validated`، `rejected` یا `imported` را نگهداری می‌کند.

## collection_records — v0.3.0

رکوردهای وصول ثبت‌شده از فایل Excel. ترکیب `region_id` و `source_row_hash` یکتا است تا یک ردیف دوباره وارد نشود.

## جداول صورت‌وضعیت — v0.4.0

- `contracts`: اطلاعات قرارداد هر واحد عملیاتی
- `statements`: مبالغ وصول، نرخ دستمزد، ناخالص، کسورات، خالص و وضعیت
- `statement_workflow`: مراحل گردش کار و اقدام‌کننده هر مرحله
- `statement_payments`: پرداخت‌های متعدد هر صورت‌وضعیت
- `statement_versions`: Snapshot غیرقابل حذف هر نسخه برای حسابرسی
