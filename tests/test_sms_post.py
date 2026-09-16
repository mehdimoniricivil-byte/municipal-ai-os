import asyncio

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shahrdari_ai.sms_post import (
    SmsPostClient,
    SmsPostConfigurationError,
    SmsPostSettings,
    normalize_mobile,
    router,
)


def _settings(**overrides):
    values = {
        "enabled": True,
        "dry_run": False,
        "base_url": "https://sms.example.test/class/sms/restful",
        "username": "municipality",
        "webservice_password": "webservice-secret",
        "sender": "+9810002002",
        "internal_api_key": "internal-secret",
        "timeout_seconds": 10.0,
    }
    values.update(overrides)
    return SmsPostSettings(**values)


def test_live_configuration_requires_https(monkeypatch):
    monkeypatch.setenv("SMSPOST_ENABLED", "true")
    monkeypatch.setenv("SMSPOST_DRY_RUN", "false")
    monkeypatch.setenv("SMSPOST_API_BASE_URL", "http://mysmsapi.ir/class/sms/restful")
    monkeypatch.setenv("SMSPOST_USERNAME", "municipality")
    monkeypatch.setenv("SMSPOST_WEBSERVICE_PASSWORD", "secret")
    monkeypatch.setenv("SMSPOST_FROM", "+9810002002")
    monkeypatch.setenv("SMSPOST_INTERNAL_API_KEY", "internal")

    with pytest.raises(SmsPostConfigurationError, match="must use HTTPS"):
        SmsPostSettings.from_env()


def test_mobile_normalization_accepts_persian_and_country_code():
    assert normalize_mobile("۰۹۱۲ ۱۲۳ ۴۵۶۷") == "09121234567"
    assert normalize_mobile("+989121234567") == "09121234567"


def test_dry_run_never_contacts_provider():
    async def fail_if_called(_request):
        raise AssertionError("provider must not be contacted in dry-run mode")

    client = SmsPostClient(
        _settings(dry_run=True),
        transport=httpx.MockTransport(fail_if_called),
    )
    result = asyncio.run(client.send_one_to_many(["09121234567"], "اخطار آزمایشی"))

    assert result["dry_run"] is True
    assert result["recipient_count"] == 1
    assert result["provider_message_id"].startswith("dry-run-")


def test_send_uses_documented_json_fields_without_exposing_secret():
    captured = {}

    async def handler(request):
        captured["url"] = str(request.url)
        captured["payload"] = __import__("json").loads(request.content)
        return httpx.Response(200, json={"uniqueID": "msg-123"})

    client = SmsPostClient(_settings(), transport=httpx.MockTransport(handler))
    result = asyncio.run(
        client.send_one_to_many(["09121234567", "+989351234567"], "یادآوری پرداخت")
    )

    assert captured["url"].endswith("/sendSms_OneToMany.php")
    assert captured["payload"] == {
        "uname": "municipality",
        "pass": "webservice-secret",
        "from": "+9810002002",
        "msg": "یادآوری پرداخت",
        "to": ["09121234567", "09351234567"],
    }
    assert result == {
        "dry_run": False,
        "provider_message_id": "msg-123",
        "recipient_count": 2,
        "provider_response": {"uniqueID": "msg-123"},
    }
    assert "webservice-secret" not in str(result)


def test_delivery_status_uses_unique_id():
    captured = {}

    async def handler(request):
        captured["payload"] = __import__("json").loads(request.content)
        return httpx.Response(200, json={"status": "delivered"})

    client = SmsPostClient(_settings(), transport=httpx.MockTransport(handler))
    result = asyncio.run(client.get_status("msg-123"))

    assert captured["payload"] == {
        "uname": "municipality",
        "pass": "webservice-secret",
        "uniqueID": "msg-123",
    }
    assert result == {"status": "delivered"}


def test_internal_send_route_is_protected_and_dry_run_safe(monkeypatch):
    monkeypatch.setenv("SMSPOST_ENABLED", "true")
    monkeypatch.setenv("SMSPOST_DRY_RUN", "true")
    monkeypatch.setenv("SMSPOST_INTERNAL_API_KEY", "internal-secret")
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    body = {"recipients": ["۰۹۱۲۱۲۳۴۵۶۷"], "message": "اخطار آزمایشی"}

    unauthorized = client.post("/api/integrations/sms/send", json=body)
    authorized = client.post(
        "/api/integrations/sms/send",
        json=body,
        headers={"X-SMS-Integration-Key": "internal-secret"},
    )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json()["dry_run"] is True
    assert authorized.json()["recipient_count"] == 1
