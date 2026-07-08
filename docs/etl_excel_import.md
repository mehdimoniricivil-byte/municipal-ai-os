# ETL Excel Column Matching

Municipality Excel files can use either Persian or Arabic keyboard variants in column names. The ETL normalizes uploaded Excel headers before matching them to logical fields, so users should not manually edit real municipality files just to replace Arabic letters.

## Header normalization

Before matching columns, the ETL:

- converts Arabic `ي` / `ى` to Persian `ی`;
- converts Arabic `ك` to Persian `ک`;
- converts Persian and Arabic digits to ASCII digits;
- converts half-spaces and invisible marks to normal spaces;
- collapses repeated whitespace and trims leading/trailing spaces.

## Accepted aliases

The following logical fields are required. Each field accepts the listed aliases after normalization:

| Logical field | Accepted aliases |
|---|---|
| `identification_code` | `کد شناسایی`, `كد شناسايي`, `کد شناسايي`, `كد شناسایی` |
| `case_number` | `شماره پرونده` |
| `operator_name` | `نام متصدی`, `نام متصدي` |
| `job` | `شغل واحد` |
| `phone` | `شماره تماس` |
| `address` | `نشانی واحد صنفی`, `نشاني واحد صنفي`, `نشانی واحد صنفي`, `نشاني واحد صنفی` |
| `payment_date` | `تاریخ پرداخت`, `تاريخ پرداخت` |
| `bill_amount` | `مبلغ فیش`, `مبلغ فيش` |
| `outstanding_debt` | `بدهی معوقه`, `بدهي معوقه` |

If any required field is still missing, the ETL returns a Persian error message that lists the missing logical field, accepted aliases for that field, and the actual columns found in the uploaded file.
