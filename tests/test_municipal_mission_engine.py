from datetime import date

from municipal_ai_os.municipal_mission_engine import MunicipalMissionEngine


def build(records):
    return MunicipalMissionEngine().build(run_id="run-1", records=records, as_of=date(2026, 7, 4))


def mission(record):
    result = build([record])
    return result["municipal_mission_list"][0]


def base_record(**overrides):
    record = {
        "debtor": "شرکت نمونه",
        "debt_amount": 6000000,
        "region": "منطقه ۱",
        "zone": "ناحیه ۲",
        "address": "بازار مرکزی",
        "mobile": "09120000000",
        "previous_notice_count": 0,
        "previous_call_count": 0,
        "previous_field_visit_count": 0,
        "payment_status": "open",
        "legal_status": "open",
        "business_category": "صنفی",
    }
    record.update(overrides)
    return record


def test_high_debt_without_previous_notice_becomes_first_notice():
    generated = mission(base_record(previous_notice_count=0))

    assert generated["mission_action"] == "NOTICE_FIRST"
    assert generated["responsible_role"] == "FIELD_COLLECTOR"
    assert "اخطار اول" in generated["required_document_or_notice"]


def test_high_debt_with_prior_notices_escalates_to_72h_or_seal_warning():
    notice_72h = mission(base_record(previous_notice_count=3))
    seal_warning = mission(base_record(previous_notice_count=4))

    assert notice_72h["mission_action"] == "NOTICE_72H"
    assert seal_warning["mission_action"] == "SEAL_WARNING"
    assert seal_warning["priority"] == "CRITICAL"


def test_legal_status_triggers_legal_review_or_commission_77_referral():
    legal_review = mission(base_record(legal_status="legal"))
    commission = mission(base_record(legal_status="commission_77"))

    assert legal_review["mission_action"] == "LEGAL_REVIEW"
    assert legal_review["responsible_role"] == "LEGAL_OPERATOR"
    assert commission["mission_action"] == "COMMISSION_77_REFERRAL"
    assert commission["priority"] == "CRITICAL"


def test_missing_mobile_prevents_staff_call_and_moves_to_field_or_manager():
    field_visit = mission(
        base_record(debt_amount=500000, mobile=None, previous_promise_to_pay=True)
    )
    manager_review = mission(base_record(debt_amount=500000, mobile=None, address=None))

    assert field_visit["mission_action"] == "FIELD_VISIT"
    assert field_visit["responsible_role"] == "FIELD_COLLECTOR"
    assert manager_review["mission_action"] == "MANAGER_REVIEW"
    assert manager_review["responsible_role"] == "REGIONAL_MANAGER"


def test_missing_address_prevents_field_visit_and_moves_to_call_or_manager():
    staff_call = mission(base_record(address=None, broken_promise_to_pay=True))
    manager_review = mission(base_record(address=None, mobile=None, broken_promise_to_pay=True))

    assert staff_call["mission_action"] == "STAFF_CALL"
    assert staff_call["responsible_role"] == "CALL_OPERATOR"
    assert manager_review["mission_action"] == "MANAGER_REVIEW"


def test_persian_instruction_and_manager_report_are_generated():
    result = build([base_record(previous_notice_count=0), base_record(mobile=None, address=None)])
    generated = result["municipal_mission_list"][0]
    report = result["human_readable_manager_report"]

    assert "این گزارش صرفاً پیشنهاد عملیاتی است" in report
    assert "پرونده شرکت نمونه" in generated["persian_instruction"]
    assert "مسئول اقدام" in generated["persian_instruction"]
    assert "مدرک لازم" in generated["persian_instruction"]
    assert "## ۲۰ پرونده فوری" in report


def test_every_mission_has_required_governance_fields():
    result = build(
        [
            base_record(previous_notice_count=0),
            base_record(legal_status="legal"),
            base_record(debt_amount=100, address=None),
        ]
    )

    for generated in result["municipal_mission_list"]:
        assert generated["responsible_role"]
        assert generated["reason"]
        assert generated["deadline"]
        assert generated["next_escalation_step"]
        assert generated["recommendation_only"] is True
