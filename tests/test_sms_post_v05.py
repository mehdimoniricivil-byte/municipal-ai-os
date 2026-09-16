import importlib.util
import os
from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient


MODULE_PATH = Path(__file__).parents[1] / "deploy" / "v05" / "sms_post.py"
SPEC = importlib.util.spec_from_file_location("sms_post_v05", MODULE_PATH)
sms_post = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = sms_post
SPEC.loader.exec_module(sms_post)


def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("SMSPOST_ENABLED", os.environ.get("SMSPOST_ENABLED", "true"))
    monkeypatch.setenv("SMSPOST_DRY_RUN", os.environ.get("SMSPOST_DRY_RUN", "true"))
    monkeypatch.setenv(
        "SMSPOST_INTERNAL_API_KEY", os.environ.get("SMSPOST_INTERNAL_API_KEY", "test-key")
    )
    app = FastAPI()
    app.include_router(sms_post.router, prefix="/api/v1/sms")
    return TestClient(app)


def test_normalize_mobile():
    assert sms_post.normalize_mobile("+98 912-123-4567") == "09121234567"


def test_health_requires_key(monkeypatch):
    response = client(monkeypatch).get("/api/v1/sms/health")
    assert response.status_code == 401


def test_health_dry_run(monkeypatch):
    response = client(monkeypatch).get(
        "/api/v1/sms/health", headers={"X-SMS-Integration-Key": "test-key"}
    )
    assert response.status_code == 200
    assert response.json()["dry_run"] is True


def test_send_dry_run(monkeypatch):
    response = client(monkeypatch).post(
        "/api/v1/sms/send",
        headers={"X-SMS-Integration-Key": "test-key"},
        json={"recipients": ["۰۹۱۲۱۲۳۴۵۶۷"], "message": "آزمایش"},
    )
    assert response.status_code == 200
    assert response.json()["provider_message_id"].startswith("dry-run-")


def test_live_mode_requires_https(monkeypatch):
    monkeypatch.setenv("SMSPOST_ENABLED", "true")
    monkeypatch.setenv("SMSPOST_DRY_RUN", "false")
    monkeypatch.setenv("SMSPOST_INTERNAL_API_KEY", "test-key")
    monkeypatch.setenv("SMSPOST_USERNAME", "u")
    monkeypatch.setenv("SMSPOST_WEBSERVICE_PASSWORD", "p")
    monkeypatch.setenv("SMSPOST_FROM", "sender")
    monkeypatch.setenv("SMSPOST_API_BASE_URL", "http://example.test")
    response = client(monkeypatch).get(
        "/api/v1/sms/health", headers={"X-SMS-Integration-Key": "test-key"}
    )
    assert response.status_code == 503
