from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import create_engine, insert

from shahrdari_ai import upload_app
from shahrdari_ai.auth import (
    UserCreate,
    UserLogin,
    UserRole,
    authenticate_user,
    create_user_record,
    hash_password,
    require_financial_access,
    scoped_region_filter,
    verify_password,
)
from shahrdari_ai.etl.engine import create_tables
from shahrdari_ai.etl.models import daily_snapshots


def test_password_hash_verification_round_trip():
    password_hash = hash_password("secure-password")

    assert password_hash != "secure-password"
    assert verify_password("secure-password", password_hash)
    assert not verify_password("wrong-password", password_hash)


def test_create_login_and_current_user_contract(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    create_tables(engine)
    monkeypatch.setattr("shahrdari_ai.auth.make_engine", lambda: engine)

    created = upload_app.create_user(
        UserCreate(
            name="مدیر کل",
            username="admin",
            password="strong-password",
            role=UserRole.ADMIN,
            is_active=True,
        )
    )
    token = upload_app.login_user(UserLogin(username="admin", password="strong-password"))
    current = upload_app.read_current_user(created)

    assert created.username == "admin"
    assert created.role == UserRole.ADMIN
    assert token.token_type == "bearer"
    assert token.access_token
    assert token.user.id == created.id
    assert current.username == "admin"


def test_inactive_or_wrong_password_login_is_rejected():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    create_tables(engine)
    create_user_record(
        UserCreate(
            name="کاربر غیرفعال",
            username="inactive",
            password="strong-password",
            role=UserRole.FIELD_AGENT,
            is_active=False,
        ),
        engine,
    )

    for password in ("strong-password", "wrong-password"):
        try:
            authenticate_user(UserLogin(username="inactive", password=password), engine)
        except HTTPException as exc:
            assert exc.status_code == 401
        else:
            raise AssertionError("inactive or invalid login should fail")


def test_role_scope_and_financial_access_are_ready():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    create_tables(engine)
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            insert(daily_snapshots),
            [
                {"import_run_id": 1, "snapshot_date": "1405-04-17", "region": "منطقه یک", "identification_code": "1", "created_at": now},
                {"import_run_id": 1, "snapshot_date": "1405-04-17", "region": "منطقه دو", "identification_code": "2", "created_at": now},
            ],
        )

    region_manager = create_user_record(
        UserCreate(name="مدیر منطقه", username="region1", password="strong-password", role=UserRole.REGION_MANAGER, region="منطقه یک"),
        engine,
    )
    accountant = create_user_record(
        UserCreate(name="حسابدار", username="acc", password="strong-password", role=UserRole.ACCOUNTANT),
        engine,
    )

    with engine.connect() as conn:
        rows = conn.execute(
            daily_snapshots.select().where(scoped_region_filter(region_manager, daily_snapshots.c.region))
        ).mappings().all()

    assert [row["identification_code"] for row in rows] == ["1"]
    assert require_financial_access(accountant) == accountant
    try:
        require_financial_access(region_manager)
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("non-accounting roles should not have financial access")
