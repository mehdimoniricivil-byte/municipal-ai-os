"""Recommendation-only field activity attribution for Municipal AI OS."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

CONFIDENCE_ORDER = {"UNMATCHED": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
IDENTIFIER_FIELDS = ["bill_id", "debtor_id", "property_id", "national_id", "mobile"]

DEFAULT_FIELD_ACTIVITY_RULES: dict[str, Any] = {
    "matching_weights": {
        "exact_bill_id": 60,
        "exact_debtor_id": 45,
        "exact_property_id": 40,
        "exact_national_id": 35,
        "exact_mobile": 25,
        "amount_similarity": 15,
        "date_window": 10,
        "normalized_address_similarity": 10,
        "business_name_similarity": 5,
    },
    "confidence_thresholds": {"high": 70, "medium": 45, "low": 20},
    "verified_credit_min_confidence": "HIGH",
    "date_window_days": 7,
    "amount_tolerance_ratio": 0.1,
    "address_similarity_threshold": 0.82,
    "business_name_similarity_threshold": 0.9,
    "require_strong_identifier_for_verified_credit": True,
    "strong_identifier_fields": ["bill_id", "debtor_id", "property_id", "national_id", "mobile"],
    "evidence_requirements": {"gps_required": True, "photo_required": True},
    "kpi_scoring": {
        "base_quality_score": 100,
        "missing_gps_penalty": 20,
        "missing_photo_penalty": 20,
        "failed_visit_penalty": 10,
        "suspicious_repeated_claim_penalty": 25,
    },
}


@dataclass(frozen=True)
class FieldActivityRecord:
    """A collector-reported field activity imported from field_activity_log.json."""

    activity_id: str
    activity_date: str
    collector_id: str
    collector_name: str
    municipality: str
    region: str
    zone: str
    debtor_id: str | None = None
    bill_id: str | None = None
    property_id: str | None = None
    national_id: str | None = None
    mobile: str | None = None
    business_name: str | None = None
    address: str | None = None
    action_type: str | None = None
    action_result: str | None = None
    promised_payment_date: str | None = None
    claimed_amount: float | None = None
    gps_lat: float | None = None
    gps_lng: float | None = None
    photo_refs: list[str] = field(default_factory=list)
    notes: str | None = None


@dataclass(frozen=True)
class CollectionRecord:
    """A normalized collection/payment candidate from the official financial source."""

    collection_id: str
    collection_date: str
    municipality: str
    region: str
    zone: str
    collection_amount: float
    debtor_id: str | None = None
    bill_id: str | None = None
    property_id: str | None = None
    national_id: str | None = None
    mobile: str | None = None
    business_name: str | None = None
    address: str | None = None
    source: str = "iran_system"


class FieldActivityAttributionEngine:
    """Matches field logs to official collections without taking automatic actions."""

    def __init__(
        self,
        workspace: str | Path,
        config_path: str | Path = "config/field_activity_rules.json",
    ) -> None:
        self.workspace = Path(workspace)
        self.config_path = Path(config_path)

    def build(
        self,
        *,
        run_id: str,
        current_records: list[dict[str, Any]],
        previous_records: list[dict[str, Any]] | None = None,
        activities: list[dict[str, Any]] | None = None,
        as_of: date | None = None,
    ) -> dict[str, Any]:
        rules = self._load_rules()
        day = as_of or date.today()
        activity_records = [self._activity(row) for row in (activities or [])]
        collections = self._collections(current_records, previous_records or [], day)
        matches = self._match_collections(collections, activity_records, rules)
        collector_report = self._collector_credit_report(
            activity_records, collections, matches, rules
        )
        quality_report = self._quality_report(activity_records, rules)
        unattributed = [
            asdict(collection)
            for collection in collections
            if collection.collection_id not in matches
        ]
        dashboard = self._manager_dashboard(matches, collector_report, quality_report, unattributed)
        return {
            "date": day.isoformat(),
            "run_id": run_id,
            "recommendation_only": True,
            "field_activity_attribution_report": {
                "recommendation_only": True,
                "matches": list(matches.values()),
                "match_count": len(matches),
            },
            "collector_credit_report": collector_report,
            "unattributed_collections": unattributed,
            "field_activity_quality_report": quality_report,
            "manager_field_performance_dashboard": dashboard,
        }

    def _match_collections(
        self,
        collections: list[CollectionRecord],
        activities: list[FieldActivityRecord],
        rules: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        matches = {}
        for collection in collections:
            candidates = [self._score_match(collection, activity, rules) for activity in activities]
            candidates = [
                candidate for candidate in candidates if candidate["confidence"] != "UNMATCHED"
            ]
            if not candidates:
                continue
            best = max(
                candidates, key=lambda candidate: (candidate["score"], candidate["activity_id"])
            )
            matches[collection.collection_id] = best
        return matches

    def _score_match(
        self,
        collection: CollectionRecord,
        activity: FieldActivityRecord,
        rules: dict[str, Any],
    ) -> dict[str, Any]:
        weights = rules["matching_weights"]
        score = 0.0
        reasons: list[str] = []
        strong_identifiers: list[str] = []
        for field_name in IDENTIFIER_FIELDS:
            collection_value = self._clean(getattr(collection, field_name))
            activity_value = self._clean(getattr(activity, field_name))
            if collection_value and activity_value and collection_value == activity_value:
                weight_name = f"exact_{field_name}"
                score += float(weights.get(weight_name, 0))
                reasons.append(weight_name)
                strong_identifiers.append(field_name)
        if self._amount_matches(collection.collection_amount, activity.claimed_amount, rules):
            score += float(weights.get("amount_similarity", 0))
            reasons.append("amount_similarity")
        if self._date_matches(collection.collection_date, activity.activity_date, rules):
            score += float(weights.get("date_window", 0))
            reasons.append("date_window")
        address_similarity = self._similarity(collection.address, activity.address)
        if address_similarity >= float(rules.get("address_similarity_threshold", 0.82)):
            score += float(weights.get("normalized_address_similarity", 0))
            reasons.append("normalized_address_similarity")
        business_similarity = self._similarity(collection.business_name, activity.business_name)
        if business_similarity >= float(rules.get("business_name_similarity_threshold", 0.9)):
            score += float(weights.get("business_name_similarity", 0))
            reasons.append("business_name_similarity")
        confidence = self._confidence(score, rules)
        verified = self._is_verified(confidence, strong_identifiers, rules)
        if not strong_identifiers and {
            "normalized_address_similarity",
            "business_name_similarity",
        } & set(reasons):
            verified = False
        return {
            "collection_id": collection.collection_id,
            "activity_id": activity.activity_id,
            "collector_id": activity.collector_id,
            "collector_name": activity.collector_name,
            "region": collection.region,
            "collection_amount": collection.collection_amount,
            "claimed_amount": activity.claimed_amount,
            "score": round(score, 2),
            "confidence": confidence,
            "verified_credit": verified,
            "assisted_credit": confidence in {"LOW", "MEDIUM"} and not verified,
            "strong_identifiers": strong_identifiers,
            "match_reasons": reasons,
            "address_similarity": round(address_similarity, 4),
            "business_name_similarity": round(business_similarity, 4),
            "recommendation_only": True,
        }

    def _collector_credit_report(
        self,
        activities: list[FieldActivityRecord],
        collections: list[CollectionRecord],
        matches: dict[str, dict[str, Any]],
        rules: dict[str, Any],
    ) -> dict[str, Any]:
        report: dict[str, dict[str, Any]] = {}
        for activity in activities:
            row = report.setdefault(activity.collector_id, self._empty_collector(activity))
            action_type = self._clean(activity.action_type)
            action_result = self._clean(activity.action_result)
            if action_type in {"visit", "field_visit"} and action_result not in {"paid", "payment"}:
                row["visits_without_payment"] += 1
            if action_type in {"notice", "deliver_notice"}:
                row["notices_delivered"] += 1
            if action_result in {"promise_to_pay", "promised_payment", "promise"}:
                row["promises_to_pay"] += 1
            if action_result in {"failed", "not_found", "closed", "no_answer"}:
                row["failed_visits"] += 1
            if activity.claimed_amount:
                row["unverified_claimed_work"] += 1
                row["unverified_claimed_amount"] = round(
                    row["unverified_claimed_amount"] + activity.claimed_amount, 2
                )
            if self._missing_gps(activity):
                row["missing_gps_evidence"] += 1
            if self._missing_photo(activity):
                row["missing_photo_evidence"] += 1
        for match in matches.values():
            row = report.setdefault(
                match["collector_id"],
                self._empty_collector_from_match(match),
            )
            if match["verified_credit"]:
                row["verified_collections"] += 1
                row["verified_collection_amount"] = round(
                    row["verified_collection_amount"] + match["collection_amount"], 2
                )
                if match.get("claimed_amount"):
                    row["unverified_claimed_work"] = max(0, row["unverified_claimed_work"] - 1)
                    row["unverified_claimed_amount"] = round(
                        max(0.0, row["unverified_claimed_amount"] - match["claimed_amount"]), 2
                    )
            elif match["assisted_credit"]:
                row["assisted_collections"] += 1
                row["assisted_collection_amount"] = round(
                    row["assisted_collection_amount"] + match["collection_amount"], 2
                )
        self._mark_suspicious_repeated_claims(activities, report, rules)
        return {
            "recommendation_only": True,
            "iran_system_source_note": "Official collections create regional revenue but do not create collector credit without field activity confidence.",
            "collectors": sorted(report.values(), key=lambda row: row["collector_id"]),
            "official_collection_count": len(collections),
        }

    def _quality_report(
        self, activities: list[FieldActivityRecord], rules: dict[str, Any]
    ) -> dict[str, Any]:
        rows = []
        scoring = rules.get("kpi_scoring", {})
        base = float(scoring.get("base_quality_score", 100))
        for activity in activities:
            score = base
            issues = []
            if self._missing_gps(activity):
                score -= float(scoring.get("missing_gps_penalty", 20))
                issues.append("missing_gps_evidence")
            if self._missing_photo(activity):
                score -= float(scoring.get("missing_photo_penalty", 20))
                issues.append("missing_photo_evidence")
            if self._clean(activity.action_result) in {
                "failed",
                "not_found",
                "closed",
                "no_answer",
            }:
                score -= float(scoring.get("failed_visit_penalty", 10))
                issues.append("failed_visit")
            rows.append(
                {
                    "activity_id": activity.activity_id,
                    "collector_id": activity.collector_id,
                    "collector_name": activity.collector_name,
                    "quality_score": max(0, round(score, 2)),
                    "issues": issues,
                    "recommendation_only": True,
                }
            )
        return {"recommendation_only": True, "activities": rows}

    def _manager_dashboard(
        self,
        matches: dict[str, dict[str, Any]],
        collector_report: dict[str, Any],
        quality_report: dict[str, Any],
        unattributed: list[dict[str, Any]],
    ) -> dict[str, Any]:
        collectors = collector_report.get("collectors", [])
        return {
            "recommendation_only": True,
            "verified_collection_amount": round(
                sum(row["verified_collection_amount"] for row in collectors), 2
            ),
            "assisted_collection_amount": round(
                sum(row["assisted_collection_amount"] for row in collectors), 2
            ),
            "unattributed_collection_amount": round(
                sum(row["collection_amount"] for row in unattributed), 2
            ),
            "verified_match_count": sum(
                1 for match in matches.values() if match["verified_credit"]
            ),
            "assisted_match_count": sum(
                1 for match in matches.values() if match["assisted_credit"]
            ),
            "unattributed_collection_count": len(unattributed),
            "quality_alert_count": sum(
                1 for row in quality_report.get("activities", []) if row.get("issues")
            ),
            "recommended_manager_actions": [
                "Review unattributed collections before assigning collector credit.",
                "Require GPS/photo evidence follow-up for low-quality field activities.",
                "Treat all outputs as recommendation-only; do not punish staff automatically.",
            ],
        }

    def _collections(
        self,
        current_records: list[dict[str, Any]],
        previous_records: list[dict[str, Any]],
        day: date,
    ) -> list[CollectionRecord]:
        previous_by_debtor = {record.get("debtor_id"): record for record in previous_records}
        current_ids = {record.get("debtor_id") for record in current_records}
        collections = []
        for record in current_records:
            before = previous_by_debtor.get(record.get("debtor_id"))
            collected = float(record.get("collected_amount") or 0)
            if before:
                collected = max(
                    0.0, float(before.get("debt_amount", 0)) - float(record.get("debt_amount", 0))
                )
            if collected > 0:
                collections.append(self._collection(record, collected, day))
        for record in previous_records:
            if (
                record.get("debtor_id") not in current_ids
                and float(record.get("debt_amount", 0)) > 0
            ):
                collections.append(
                    self._collection(record, float(record.get("debt_amount", 0)), day)
                )
        return collections

    def _collection(self, record: dict[str, Any], amount: float, day: date) -> CollectionRecord:
        collection_id = str(
            record.get("collection_id")
            or record.get("payment_id")
            or record.get("bill_id")
            or f"collection-{record.get('debtor_id', 'unknown')}-{day.isoformat()}"
        )
        return CollectionRecord(
            collection_id=collection_id,
            collection_date=str(
                record.get("collection_date") or record.get("payment_date") or day.isoformat()
            ),
            municipality=str(record.get("municipality") or "Unassigned"),
            region=str(record.get("region") or "Unassigned"),
            zone=str(record.get("zone") or record.get("region") or "Unassigned"),
            collection_amount=round(amount, 2),
            debtor_id=self._optional(record.get("debtor_id")),
            bill_id=self._optional(record.get("bill_id")),
            property_id=self._optional(record.get("property_id")),
            national_id=self._optional(record.get("national_id")),
            mobile=self._optional(record.get("mobile")),
            business_name=self._optional(record.get("business_name") or record.get("debtor_name")),
            address=self._optional(record.get("address")),
            source=str(record.get("source") or "iran_system"),
        )

    def _activity(self, row: dict[str, Any]) -> FieldActivityRecord:
        required = ["activity_id", "activity_date", "collector_id", "collector_name"]
        missing = [field for field in required if row.get(field) in (None, "")]
        if missing:
            raise ValueError(f"Field activity is missing required fields: {', '.join(missing)}")
        return FieldActivityRecord(
            activity_id=str(row["activity_id"]),
            activity_date=str(row["activity_date"]),
            collector_id=str(row["collector_id"]),
            collector_name=str(row["collector_name"]),
            municipality=str(row.get("municipality") or "Unassigned"),
            region=str(row.get("region") or "Unassigned"),
            zone=str(row.get("zone") or row.get("region") or "Unassigned"),
            debtor_id=self._optional(row.get("debtor_id")),
            bill_id=self._optional(row.get("bill_id")),
            property_id=self._optional(row.get("property_id")),
            national_id=self._optional(row.get("national_id")),
            mobile=self._optional(row.get("mobile")),
            business_name=self._optional(row.get("business_name")),
            address=self._optional(row.get("address")),
            action_type=self._optional(row.get("action_type")),
            action_result=self._optional(row.get("action_result")),
            promised_payment_date=self._optional(row.get("promised_payment_date")),
            claimed_amount=self._money_or_none(row.get("claimed_amount")),
            gps_lat=self._float_or_none(row.get("gps_lat")),
            gps_lng=self._float_or_none(row.get("gps_lng")),
            photo_refs=[str(item) for item in row.get("photo_refs", [])],
            notes=self._optional(row.get("notes")),
        )

    def _empty_collector(self, activity: FieldActivityRecord) -> dict[str, Any]:
        return {
            "collector_id": activity.collector_id,
            "collector_name": activity.collector_name,
            "verified_collections": 0,
            "verified_collection_amount": 0.0,
            "assisted_collections": 0,
            "assisted_collection_amount": 0.0,
            "unverified_claimed_work": 0,
            "unverified_claimed_amount": 0.0,
            "visits_without_payment": 0,
            "notices_delivered": 0,
            "promises_to_pay": 0,
            "failed_visits": 0,
            "suspicious_repeated_claims": 0,
            "missing_gps_evidence": 0,
            "missing_photo_evidence": 0,
            "recommendation_only": True,
        }

    def _empty_collector_from_match(self, match: dict[str, Any]) -> dict[str, Any]:
        return self._empty_collector(
            FieldActivityRecord(
                activity_id="unknown",
                activity_date=date.today().isoformat(),
                collector_id=match["collector_id"],
                collector_name=match["collector_name"],
                municipality="Unassigned",
                region=match.get("region", "Unassigned"),
                zone="Unassigned",
            )
        )

    def _mark_suspicious_repeated_claims(
        self,
        activities: list[FieldActivityRecord],
        report: dict[str, dict[str, Any]],
        rules: dict[str, Any],
    ) -> None:
        seen: dict[tuple[str, str, float | None], list[FieldActivityRecord]] = {}
        for activity in activities:
            key = (
                activity.collector_id,
                activity.bill_id or activity.debtor_id or "",
                activity.claimed_amount,
            )
            seen.setdefault(key, []).append(activity)
        for (collector_id, identifier, amount), claims in seen.items():
            if identifier and amount and len(claims) > 1:
                report[collector_id]["suspicious_repeated_claims"] += len(claims)

    def _is_verified(
        self, confidence: str, strong_identifiers: list[str], rules: dict[str, Any]
    ) -> bool:
        threshold = str(rules.get("verified_credit_min_confidence", "HIGH")).upper()
        if CONFIDENCE_ORDER[confidence] < CONFIDENCE_ORDER.get(threshold, CONFIDENCE_ORDER["HIGH"]):
            return False
        if (
            rules.get("require_strong_identifier_for_verified_credit", True)
            and not strong_identifiers
        ):
            return False
        allowed = set(rules.get("strong_identifier_fields", IDENTIFIER_FIELDS))
        return bool(set(strong_identifiers) & allowed)

    def _confidence(self, score: float, rules: dict[str, Any]) -> str:
        thresholds = rules.get("confidence_thresholds", {})
        if score >= float(thresholds.get("high", 70)):
            return "HIGH"
        if score >= float(thresholds.get("medium", 45)):
            return "MEDIUM"
        if score >= float(thresholds.get("low", 20)):
            return "LOW"
        return "UNMATCHED"

    def _amount_matches(
        self, collection_amount: float, claimed_amount: float | None, rules: dict[str, Any]
    ) -> bool:
        if not claimed_amount or collection_amount <= 0:
            return False
        tolerance = float(rules.get("amount_tolerance_ratio", 0.1))
        return (
            abs(collection_amount - claimed_amount)
            <= max(collection_amount, claimed_amount) * tolerance
        )

    def _date_matches(
        self, collection_date: str, activity_date: str, rules: dict[str, Any]
    ) -> bool:
        try:
            collection_day = datetime.fromisoformat(collection_date).date()
            activity_day = datetime.fromisoformat(activity_date).date()
        except ValueError:
            return False
        return abs((collection_day - activity_day).days) <= int(rules.get("date_window_days", 7))

    def _missing_gps(self, activity: FieldActivityRecord) -> bool:
        return activity.gps_lat is None or activity.gps_lng is None

    def _missing_photo(self, activity: FieldActivityRecord) -> bool:
        return not activity.photo_refs

    def _load_rules(self) -> dict[str, Any]:
        rules = json.loads(json.dumps(DEFAULT_FIELD_ACTIVITY_RULES))
        if self.config_path.exists():
            configured = json.loads(self.config_path.read_text())
            for key, value in configured.items():
                if isinstance(value, dict) and isinstance(rules.get(key), dict):
                    rules[key] = {**rules[key], **value}
                else:
                    rules[key] = value
        return rules

    @staticmethod
    def _similarity(left: str | None, right: str | None) -> float:
        if not left or not right:
            return 0.0
        return SequenceMatcher(
            None,
            FieldActivityAttributionEngine._normalize(left),
            FieldActivityAttributionEngine._normalize(right),
        ).ratio()

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(str(value).strip().lower().replace("ي", "ی").replace("ك", "ک").split())

    @staticmethod
    def _clean(value: Any) -> str:
        return str(value).strip().lower() if value not in (None, "") else ""

    @staticmethod
    def _optional(value: Any) -> str | None:
        return str(value).strip() if value not in (None, "") else None

    @staticmethod
    def _money_or_none(value: Any) -> float | None:
        if value in (None, ""):
            return None
        return round(float(str(value).replace("$", "").replace(",", "")), 2)

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        if value in (None, ""):
            return None
        return float(value)
