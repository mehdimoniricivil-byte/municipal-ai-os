from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    module: str
    action: str
    record_type: str | None
    record_id: str | None
    old_value: str | None
    new_value: str | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime
