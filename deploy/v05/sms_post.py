from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field, field_validator


class SmsPostConfigurationError(RuntimeError):
    pass


class SmsPostRequestError(RuntimeError):
    pass


_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_MOBILE_PATTERN = re.compile(r"^09\d{9}$")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def normalize_mobile(value: str) -> str:
    normalized = str(value or "").translate(_DIGITS).strip()
    normalized = re.sub(r"[\s\-()]", "", normalized)
    if normalized.startswith("+98"):
        normalized = "0" + normalized[3:]
    elif normalized.startswith("98") and len(normalized) == 12:
        normalized = "0" + normalized[2:]
    if not _MOBILE_PATTERN.fullmatch(normalized):
        raise ValueError("شماره موبایل باید با قالب 09XXXXXXXXX وارد شود")
    return normalized


@dataclass(frozen=True)
class SmsPostSettings:
    enabled: bool
    dry_run: bool
    base_url: str
    username: str
    webservice_password: str
    sender: str
    internal_api_key: str
    timeout_seconds: float

    @classmethod
    def from_env(cls) -> "SmsPostSettings":
        try:
            timeout = float(os.environ.get("SMSPOST_TIMEOUT_SECONDS", "15"))
        except ValueError as exc:
            raise SmsPostConfigurationError("SMSPOST_TIMEOUT_SECONDS must be numeric") from exc
        if timeout <= 0 or timeout > 60:
            raise SmsPostConfigurationError("SMSPOST_TIMEOUT_SECONDS must be between 0 and 60")
        settings = cls(
            enabled=_env_bool("SMSPOST_ENABLED", False),
            dry_run=_env_bool("SMSPOST_DRY_RUN", True),
            base_url=os.environ.get("SMSPOST_API_BASE_URL", "").strip().rstrip("/"),
            username=os.environ.get("SMSPOST_USERNAME", "").strip(),
            webservice_password=os.environ.get("SMSPOST_WEBSERVICE_PASSWORD", "").strip(),
            sender=os.environ.get("SMSPOST_FROM", "").strip(),
            internal_api_key=os.environ.get("SMSPOST_INTERNAL_API_KEY", "").strip(),
            timeout_seconds=timeout,
        )
        settings.validate()
        return settings

    @property
    def configured(self) -> bool:
        return all(
            (
                self.base_url,
                self.username,
                self.webservice_password,
                self.sender,
                self.internal_api_key,
            )
        )

    @property
    def transport_secure(self) -> bool:
        return urlparse(self.base_url).scheme.lower() == "https"

    def validate(self) -> None:
        if not self.enabled:
            return
        if not self.internal_api_key:
            raise SmsPostConfigurationError("SMSPOST_INTERNAL_API_KEY is required")
        if self.dry_run:
            return
        missing = [
            name
            for name, value in (
                ("SMSPOST_API_BASE_URL", self.base_url),
                ("SMSPOST_USERNAME", self.username),
                ("SMSPOST_WEBSERVICE_PASSWORD", self.webservice_password),
                ("SMSPOST_FROM", self.sender),
            )
            if not value
        ]
        if missing:
            raise SmsPostConfigurationError(f"Missing SMSPost settings: {', '.join(missing)}")
        if not self.transport_secure:
            raise SmsPostConfigurationError("SMSPOST_API_BASE_URL must use HTTPS")


def _provider_message_id(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("uniqueID", "uniqueId", "unique_id", "messageId", "message_id", "id"):
            if payload.get(key) not in (None, ""):
                return str(payload[key])
        for value in payload.values():
            found = _provider_message_id(value)
            if found:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _provider_message_id(value)
            if found:
                return found
    return None


class SmsPostClient:
    ENDPOINTS = {
        "send": "sendSms_OneToMany.php",
        "status": "getStatus.php",
        "status_array": "getStatusArray.php",
    }

    def __init__(self, settings: SmsPostSettings) -> None:
        self.settings = settings

    def _credentials(self) -> dict[str, str]:
        return {"uname": self.settings.username, "pass": self.settings.webservice_password}

    async def _post(self, endpoint: str, payload: dict[str, Any]) -> Any:
        self.settings.validate()
        if not self.settings.enabled:
            raise SmsPostConfigurationError("SMSPost integration is disabled")
        if self.settings.dry_run:
            return {"dry_run": True}
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.timeout_seconds,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    urljoin(self.settings.base_url + "/", endpoint),
                    json=payload,
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SmsPostRequestError("sms_provider_request_failed") from exc
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise SmsPostRequestError("sms_provider_invalid_json") from exc

    async def send(self, recipients: list[str], message: str) -> dict[str, Any]:
        normalized = [normalize_mobile(value) for value in recipients]
        message = str(message or "").strip()
        if not message:
            raise ValueError("متن پیام الزامی است")
        if self.settings.dry_run:
            digest = hashlib.sha256(("|".join(normalized) + "\n" + message).encode()).hexdigest()[:16]
            return {
                "dry_run": True,
                "provider_message_id": f"dry-run-{digest}",
                "recipient_count": len(normalized),
            }
        result = await self._post(
            self.ENDPOINTS["send"],
            {**self._credentials(), "from": self.settings.sender, "msg": message, "to": normalized},
        )
        return {
            "dry_run": False,
            "provider_message_id": _provider_message_id(result),
            "recipient_count": len(normalized),
            "provider_response": result,
        }

    async def status(self, unique_ids: list[str]) -> Any:
        cleaned = [str(value).strip() for value in unique_ids if str(value).strip()]
        if not cleaned:
            raise ValueError("حداقل یک شناسه پیام الزامی است")
        endpoint = "status" if len(cleaned) == 1 else "status_array"
        key = "uniqueID" if len(cleaned) == 1 else "uniqueIDs"
        return await self._post(self.ENDPOINTS[endpoint], {**self._credentials(), key: cleaned[0] if len(cleaned) == 1 else cleaned})


class SmsSendRequest(BaseModel):
    recipients: list[str] = Field(min_length=1, max_length=500)
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("recipients")
    @classmethod
    def validate_recipients(cls, values: list[str]) -> list[str]:
        return [normalize_mobile(value) for value in values]


class SmsStatusRequest(BaseModel):
    unique_ids: list[str] = Field(min_length=1, max_length=500)


router = APIRouter()


def _authorized(x_sms_integration_key: str | None) -> SmsPostSettings:
    try:
        settings = SmsPostSettings.from_env()
    except SmsPostConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not settings.internal_api_key:
        raise HTTPException(status_code=503, detail="SMS integration key is not configured")
    if not x_sms_integration_key or not secrets.compare_digest(
        x_sms_integration_key, settings.internal_api_key
    ):
        raise HTTPException(status_code=401, detail="invalid integration key")
    return settings


@router.get("/health")
async def health(x_sms_integration_key: str | None = Header(default=None)) -> dict[str, Any]:
    settings = _authorized(x_sms_integration_key)
    return {
        "enabled": settings.enabled,
        "dry_run": settings.dry_run,
        "configured": settings.configured,
        "transport_secure": settings.transport_secure,
        "sender_configured": bool(settings.sender),
    }


@router.post("/send")
async def send_sms(
    request: SmsSendRequest,
    x_sms_integration_key: str | None = Header(default=None),
) -> dict[str, Any]:
    settings = _authorized(x_sms_integration_key)
    if not settings.enabled:
        raise HTTPException(status_code=503, detail="SMSPost integration is disabled")
    try:
        return await SmsPostClient(settings).send(request.recipients, request.message)
    except (ValueError, SmsPostConfigurationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SmsPostRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/status")
async def sms_status(
    request: SmsStatusRequest,
    x_sms_integration_key: str | None = Header(default=None),
) -> Any:
    settings = _authorized(x_sms_integration_key)
    if not settings.enabled:
        raise HTTPException(status_code=503, detail="SMSPost integration is disabled")
    try:
        return await SmsPostClient(settings).status(request.unique_ids)
    except (ValueError, SmsPostConfigurationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SmsPostRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
