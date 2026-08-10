from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UploadHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    region_id: int
    persian_year: int
    persian_month: int
    original_filename: str
    status: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    total_amount_irr: int
    uploaded_by: int
    uploaded_at: datetime
    imported_at: datetime | None
