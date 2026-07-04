import json
from datetime import date

from municipal_ai_os.field_activity_attribution import FieldActivityAttributionEngine


def collection(**overrides):
    row = {
        "collection_id": "payment-1",
        "collection_date": "2026-07-04",
        "municipality": "Central Municipality",
        "region": "North",
        "zone": "N1",
        "collection_amount": 1000,
        "collected_amount": 1000,
        "debt_amount": 0,
        "debtor_id": "debtor-1",
        "bill_id": "bill-1",
        "property_id": "property-1",
        "national_id": "national-1",
        "mobile": "09120000000",
        "business_name": "Alpha Shop",
        "address": "Main Street 1",
        "source": "iran_system",
    }
    row.update(overrides)
    return row


def activity(**overrides):
    row = {
        "activity_id": "activity-1",
        "activity_date": "2026-07-03",
        "collector_id": "collector-1",
        "collector_name": "Collector One",
        "municipality": "Central Municipality",
        "region": "North",
        "zone": "N1",
        "debtor_id": "debtor-1",
        "bill_id": "bill-1",
        "property_id": "property-1",
        "national_id": "national-1",
        "mobile": "09120000000",
        "business_name": "Alpha Shop",
        "address": "Main Street 1",
        "action_type": "field_visit",
        "action_result": "promise_to_pay",
        "promised_payment_date": "2026-07-04",
        "claimed_amount": 1000,
        "gps_lat": 35.7,
        "gps_lng": 51.4,
        "photo_refs": ["photo-1.jpg"],
        "notes": "Visited taxpayer.",
    }
    row.update(overrides)
    return row


def build(tmp_path, current, activities, rules=None):
    config = tmp_path / "field_activity_rules.json"
    if rules is not None:
        config.write_text(json.dumps(rules))
    return FieldActivityAttributionEngine(tmp_path, config).build(
        run_id="run-1",
        current_records=current,
        previous_records=[],
        activities=activities,
        as_of=date(2026, 7, 4),
    )


def test_iran_system_data_alone_cannot_assign_collector_credit(tmp_path):
    result = build(tmp_path, [collection()], [])

    assert result["collector_credit_report"]["collectors"] == []
    assert result["unattributed_collections"][0]["collection_id"] == "payment-1"
    assert result["manager_field_performance_dashboard"]["unattributed_collection_count"] == 1


def test_exact_bill_id_match_gives_high_confidence_and_verified_credit(tmp_path):
    result = build(tmp_path, [collection()], [activity()])
    match = result["field_activity_attribution_report"]["matches"][0]
    collector = result["collector_credit_report"]["collectors"][0]

    assert match["confidence"] == "HIGH"
    assert match["verified_credit"] is True
    assert "bill_id" in match["strong_identifiers"]
    assert collector["verified_collections"] == 1
    assert collector["verified_collection_amount"] == 1000


def test_exact_property_id_confidence_depends_on_rules(tmp_path):
    current = [
        collection(
            bill_id=None,
            debtor_id=None,
            national_id=None,
            mobile=None,
            address="Official Address",
            business_name="Official Business",
        )
    ]
    activities = [
        activity(
            bill_id=None,
            debtor_id=None,
            national_id=None,
            mobile=None,
            claimed_amount=700,
            address="Field Address",
            business_name="Field Business",
        )
    ]

    medium = build(tmp_path, current, activities)
    assert medium["field_activity_attribution_report"]["matches"][0]["confidence"] == "MEDIUM"

    high_rules = {
        "matching_weights": {"exact_property_id": 70},
        "confidence_thresholds": {"high": 70, "medium": 45, "low": 20},
    }
    high = build(tmp_path, current, activities, high_rules)
    assert high["field_activity_attribution_report"]["matches"][0]["confidence"] == "HIGH"


def test_weak_address_only_match_does_not_create_verified_credit(tmp_path):
    current = [
        collection(bill_id=None, debtor_id=None, property_id=None, national_id=None, mobile=None)
    ]
    activities = [
        activity(
            bill_id=None,
            debtor_id=None,
            property_id=None,
            national_id=None,
            mobile=None,
            business_name="Different Name",
        )
    ]
    rules = {
        "matching_weights": {"normalized_address_similarity": 80},
        "confidence_thresholds": {"high": 70, "medium": 45, "low": 20},
    }

    result = build(tmp_path, current, activities, rules)
    match = result["field_activity_attribution_report"]["matches"][0]

    assert match["confidence"] == "HIGH"
    assert match["verified_credit"] is False
    assert match["strong_identifiers"] == []
    assert result["collector_credit_report"]["collectors"][0]["verified_collections"] == 0


def test_unmatched_collections_remain_unattributed(tmp_path):
    result = build(
        tmp_path,
        [collection(bill_id="bill-official", debtor_id="debtor-official", property_id="property-official", national_id="national-official", mobile="09121111111", address="A")],
        [
            activity(
                bill_id="bill-field",
                debtor_id="debtor-field",
                address="B",
                business_name="Other Business",
                activity_date="2026-06-01",
                claimed_amount=50,
            )
        ],
    )

    assert result["field_activity_attribution_report"]["matches"] == []
    assert result["unattributed_collections"][0]["collection_id"] == "payment-1"


def test_missing_gps_and_photo_lowers_quality_score(tmp_path):
    result = build(tmp_path, [collection()], [activity(gps_lat=None, gps_lng=None, photo_refs=[])])
    quality = result["field_activity_quality_report"]["activities"][0]
    collector = result["collector_credit_report"]["collectors"][0]

    assert quality["quality_score"] == 60
    assert quality["issues"] == ["missing_gps_evidence", "missing_photo_evidence"]
    assert collector["missing_gps_evidence"] == 1
    assert collector["missing_photo_evidence"] == 1


def test_collector_report_separates_verified_and_unverified_work(tmp_path):
    result = build(
        tmp_path,
        [collection(collection_id="payment-1", bill_id="bill-1")],
        [
            activity(activity_id="activity-1", bill_id="bill-1", claimed_amount=1000),
            activity(
                activity_id="activity-2",
                bill_id="bill-2",
                claimed_amount=500,
                action_type="notice",
                action_result="failed",
            ),
        ],
    )
    collector = result["collector_credit_report"]["collectors"][0]

    assert collector["verified_collections"] == 1
    assert collector["verified_collection_amount"] == 1000
    assert collector["unverified_claimed_work"] == 1
    assert collector["unverified_claimed_amount"] == 500
    assert collector["notices_delivered"] == 1
    assert collector["failed_visits"] == 1
