# SMSPost integration

The SMSPost adapter is disabled and in dry-run mode by default. Dry-run requests validate
and normalize recipients but never contact the provider.

## Environment variables

```bash
SMSPOST_ENABLED=true
SMSPOST_DRY_RUN=true
SMSPOST_API_BASE_URL=https://PROVIDER-HTTPS-HOST/class/sms/restful
SMSPOST_USERNAME=borujerdasnaf
SMSPOST_WEBSERVICE_PASSWORD=SET_OUTSIDE_GIT
SMSPOST_FROM=PROVIDER_CONFIRMED_SENDER
SMSPOST_INTERNAL_API_KEY=GENERATE_A_LONG_RANDOM_SECRET
SMSPOST_TIMEOUT_SECONDS=15
```

Never commit real values to Git. `SMSPOST_WEBSERVICE_PASSWORD` is the web-service password,
not the interactive panel password.

Live sending is rejected unless the API base URL uses HTTPS. At the time of integration,
the panel documented `http://mysmsapi.ir/...` endpoints and the HTTPS host returned a
certificate hostname mismatch. Keep `SMSPOST_DRY_RUN=true` until the provider supplies a
valid HTTPS endpoint and confirms the sender format.

## Internal API

All routes require the `X-SMS-Integration-Key` header. They are intended for server-side
calls and must not be called directly from browser JavaScript.

- `GET /api/integrations/sms/health`
- `POST /api/integrations/sms/send`
- `GET /api/integrations/sms/status/{unique_id}`
- `POST /api/integrations/sms/status`

Example dry-run request:

```bash
curl -X POST http://127.0.0.1:8000/api/integrations/sms/send \
  -H 'Content-Type: application/json' \
  -H "X-SMS-Integration-Key: $SMSPOST_INTERNAL_API_KEY" \
  -d '{"recipients":["09121234567"],"message":"پیام آزمایشی"}'
```

Persist `provider_message_id` with the related municipal case before enabling delivery
status polling. A database migration for that relation should be made against the current
production schema, not guessed from this repository snapshot.
