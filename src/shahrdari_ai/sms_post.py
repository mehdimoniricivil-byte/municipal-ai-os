from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field, field_validator


class SmsPostConfigurationError(RuntimeError):
    """Raised when SMSPost is not safely configured."""


class SmsPostRequestError(RuntimeError):
    """Raised when SMSPost rejects or cannot complete a request."""


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
        raise ValueError(
            "شماره موبایل باید با قالب 09XXXXXXXXX وارد شود"
        )
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
    timeout_seconds: float = 15.0

    @classmethod
    def from_env(cls) -> "SmsPostSettings":
        timeout_raw = os.environ.get("SMSPOST_TIMEOUT_SECONDS", "15")
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError as exc:
            raise SmsPostConfigurationError("SMSPOST_TIMEOUT_SECONDS must be numeric") from exc
        if timeout_seconds <= 0 or timeout_seconds > 60:
            raise SmsPostConfigurationError("SMSPOST_TIMEOUT_SECONDS must be between 0 and 60")

        settings = cls(
            enabled=_env_bool("SMSPOST_ENABLED", False),
            dry_run=_env_bool("SMSPOST_DRY_RUN", True),
            base_url=os.environ.get("SMSPOST_API_BASE_URL", "").strip().rstrip("/"),
            username=os.environ.get("SMSPOST_USERNAME", "").strip(),
            webservice_password=os.environ.get("SMSPOST_WEBSERVICE_PASSWORD", "").strip(),
            sender=os.environ.get("SMSPOST_FROM", "").strip(),
            internal_api_key=os.environ.get("SMSPOST_INTERNAL_API_KEY", "").strip(),
            timeout_seconds=timeout_seconds,
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
            raise SmsPostConfigurationError("SMSPOST_INTERNAL_API_KEY is required when enabled")
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
            raise SmsPostConfigurationError("SMSPOST_API_BASE_URL must use HTTPS for live sending")


def _extract_provider_message_id(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("uniqueID", "uniqueId", "unique_id", "messageId", "message_id", "id"):
            value = payload.get(key)
            if value not in (None, ""):
                return str(value)
        for value in payload.values():
            found = _extract_provider_message_id(value)
            if found:
                return found
    if isinstance(payload, list):
        for value in payload:
            found = _extract_provider_message_id(value)
            if found:
                return found
    return None


class SmsPostClient:
    ENDPOINTS = {
        "account": "getData.php",
        "send_one_to_many": "sendSms_OneToMany.php",
        "status": "getStatus.php",
        "status_array": "getStatusArray.php",
    }

    def __init__(
        self,
        settings: SmsPostSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport

    def _credentials(self) -> dict[str, str]:
        return {
            "uname": self.settings.username,
            "pass": self.settings.webservice_password,
        }

    async def _post(self, endpoint: str, payload: dict[str, Any]) -> Any:
        self.settings.validate()
        if not self.settings.enabled:
            raise SmsPostConfigurationError("SMSPost integration is disabled")
        if self.settings.dry_run:
            return {"dry_run": True}

        url = urljoin(self.settings.base_url + "/", endpoint)
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.timeout_seconds,
                transport=self.transport,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    url,
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

    async def account_info(self) -> Any:
        return await self._post(self.ENDPOINTS["account"], self._credentials())

    async def send_one_to_many(self, recipients: Iterable[str], message: str) -> dict[str, Any]:
        normalized_recipients = [normalize_mobile(recipient) for recipient in recipients]
        if not normalized_recipients:
            raise ValueError("حداقل یک گیرنده الزامی است")
        if len(normalized_recipients) > 500:
            raise ValueError(
                "حداکثر ۵۰۰ گیرنده در هر درخواست مجاز است"
            )
        normalized_message = str(message or "").strip()
        if not normalized_message:
            raise ValueError("متن پیام الزامی است")
        if len(normalized_message) > 4000:
            raise ValueError("متن پیام بیش از حد طولانی است")

        if self.settings.dry_run:
            digest = hashlib.sha256(
                ("|".join(normalized_recipients) + "\n" + normalized_message).encode("utf-8")
            ).hexdigest()[:16]
            return {
                "dry_run": True,
                "provider_message_id": f"dry-run-{digest}",
                "recipient_count": len(normalized_recipients),
            }

        payload = {
            **self._credentials(),
            "from": self.settings.sender,
            "msg": normalized_message,
            "to": normalized_recipients,
        }
        provider_response = await self._post(self.ENDPOINTS["send_one_to_many"], payload)
        return {
            "dry_run": False,
            "provider_message_id": _extract_provider_message_id(provider_response),
            "recipient_count": len(normalized_recipients),
            "provider_response": provider_response,
        }

    async def get_status(self, unique_id: str) -> Any:
        normalized_id = str(unique_id or "").strip()
        if not normalized_id:
            raise ValueError("شناسه پیام الزامی است")
        return await self._post(
            self.ENDPOINTS["status"],
            {**self._credentials(), "uniqueID": normalized_id},
        )

    async def get_status_array(self, unique_ids: Iterable[str]) -> Any:
        normalized_ids = [str(value or "").strip() for value in unique_ids]
        normalized_ids = [value for value in normalized_ids if value]
        if not normalized_ids:
            raise ValueError("حداقل یک شناسه پیام الزامی است")
        if len(normalized_ids) > 500:
            raise ValueError(
                "حداکثر ۵۰۰ شناسه در هر درخواست مجاز است"
            )
        return await self._post(
            self.ENDPOINTS["status_array"],
            {**self._credentials(), "uniqueIDs": normalized_ids},
        )


class SmsSendRequest(BaseModel):
    recipients: list[str] = Field(min_length=1, max_length=500)
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("recipients")
    @classmethod
    def validate_recipients(cls, values: list[str]) -> list[str]:
        return [normalize_mobile(value) for value in values]


class SmsStatusArrayRequest(BaseModel):
    unique_ids: list[str] = Field(min_length=1, max_length=500)


class SmsHealthResponse(BaseModel):
    enabled: bool
    dry_run: bool
    configured: bool
    transport_secure: bool
    sender_configured: bool


router = APIRouter(prefix="/api/integrations/sms", tags=["SMS Integration"])


def _settings_or_http_error() -> SmsPostSettings:
    try:
        return SmsPostSettings.from_env()
    except SmsPostConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _authorize(settings: SmsPostSettings, provided_key: str | None) -> None:
    if not settings.internal_api_key:
        raise HTTPException(status_code=503, detail="sms_internal_api_key_not_configured")
    if not provided_key or not secrets.compare_digest(provided_key, settings.internal_api_key):
        raise HTTPException(status_code=401, detail="sms_integration_unauthorized")


@router.get("/health", response_model=SmsHealthResponse)
def sms_health(x_sms_integration_key: str | None = Header(default=None)) -> SmsHealthResponse:
    settings = _settings_or_http_error()
    _authorize(settings, x_sms_integration_key)
    return SmsHealthResponse(
        enabled=settings.enabled,
        dry_run=settings.dry_run,
        configured=settings.configured,
        transport_secure=settings.transport_secure,
        sender_configured=bool(settings.sender),
    )


@router.post("/send")
async def send_sms(
    request: SmsSendRequest,
    x_sms_integration_key: str | None = Header(default=None),
) -> dict[str, Any]:
    settings = _settings_or_http_error()
    _authorize(settings, x_sms_integration_key)
    if not settings.enabled:
        raise HTTPException(status_code=503, detail="sms_provider_disabled")
    try:
        return await SmsPostClient(settings).send_one_to_many(request.recipients, request.message)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (SmsPostConfigurationError, SmsPostRequestError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/status/{unique_id}")
async def get_sms_status(
    unique_id: str,
    x_sms_integration_key: str | None = Header(default=None),
) -> Any:
    settings = _settings_or_http_error()
    _authorize(settings, x_sms_integration_key)
    try:
        return await SmsPostClient(settings).get_status(unique_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (SmsPostConfigurationError, SmsPostRequestError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/status")
async def get_sms_status_array(
    request: SmsStatusArrayRequest,
    x_sms_integration_key: str | None = Header(default=None),
) -> Any:
    settings = _settings_or_http_error()
    _authorize(settings, x_sms_integration_key)
    try:
        return await SmsPostClient(settings).get_status_array(request.unique_ids)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (SmsPostConfigurationError, SmsPostRequestError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
