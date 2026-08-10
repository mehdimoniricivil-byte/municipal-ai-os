from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.models import Region, User
from app.db.session import SessionLocal


REGIONS = [
    ("R1", "منطقه ۱", 1),
    ("R2", "منطقه ۲", 2),
    ("A2", "ناحیه ۲", 3),
    ("A3", "ناحیه ۳", 4),
    ("R3", "منطقه ۳", 5),
]


def seed_reference_data() -> None:
    with SessionLocal() as db:
        for code, title, order in REGIONS:
            if db.scalar(select(Region).where(Region.code == code)) is None:
                db.add(Region(code=code, title=title, sort_order=order))
        db.flush()
        if db.scalar(select(User).where(User.username == settings.initial_admin_username)) is None:
            db.add(User(
                username=settings.initial_admin_username,
                full_name=settings.initial_admin_full_name,
                password_hash=hash_password(settings.initial_admin_password),
                role="brokerage_head",
                is_active=True,
                must_change_password=True,
            ))
        db.commit()
