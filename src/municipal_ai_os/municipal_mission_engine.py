"""Rules-based municipal mission generation for collection operations."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

MISSION_ACTIONS = {
    "STAFF_CALL",
    "FIELD_VISIT",
    "NOTICE_FIRST",
    "NOTICE_24H",
    "NOTICE_48H",
    "NOTICE_72H",
    "SEAL_WARNING",
    "COMMISSION_77_REFERRAL",
    "LEGAL_REVIEW",
    "EXECUTION_REGISTRATION",
    "MANAGER_REVIEW",
    "LOW_PRIORITY_MONITORING",
}

RESPONSIBLE_ROLE_BY_ACTION = {
    "STAFF_CALL": "CALL_OPERATOR",
    "FIELD_VISIT": "FIELD_COLLECTOR",
    "NOTICE_FIRST": "FIELD_COLLECTOR",
    "NOTICE_24H": "FIELD_COLLECTOR",
    "NOTICE_48H": "FIELD_COLLECTOR",
    "NOTICE_72H": "FIELD_COLLECTOR",
    "SEAL_WARNING": "REGIONAL_MANAGER",
    "COMMISSION_77_REFERRAL": "LEGAL_OPERATOR",
    "LEGAL_REVIEW": "LEGAL_OPERATOR",
    "EXECUTION_REGISTRATION": "LEGAL_OPERATOR",
    "MANAGER_REVIEW": "REGIONAL_MANAGER",
    "LOW_PRIORITY_MONITORING": "ADMIN",
}

NOTICE_ACTIONS = {"NOTICE_FIRST", "NOTICE_24H", "NOTICE_48H", "NOTICE_72H", "SEAL_WARNING"}
LEGAL_ACTIONS = {"COMMISSION_77_REFERRAL", "LEGAL_REVIEW", "EXECUTION_REGISTRATION"}

DEFAULT_MISSION_RULES: dict[str, Any] = {
    "debt_amount_thresholds": {"critical": 50_000_000, "high": 5_000_000, "medium": 1_000_000},
    "debt_age_thresholds_days": {"critical": 365, "high": 180, "medium": 60},
    "notice_escalation": {
        "first_notice_when_previous_notice_count": 0,
        "notice_24h_after_count": 1,
        "notice_48h_after_count": 2,
        "notice_72h_after_count": 3,
        "seal_warning_after_count": 4,
    },
    "call_escalation": {"max_previous_call_count_for_staff_call": 2},
    "field_visit_escalation": {"max_previous_field_visit_count_before_manager_review": 3},
    "priority_deadlines_hours": {"CRITICAL": 24, "HIGH": 48, "MEDIUM": 72, "LOW": 168},
    "legal_status_actions": {
        "commission_77": "COMMISSION_77_REFERRAL",
        "commission 77": "COMMISSION_77_REFERRAL",
        "legal": "LEGAL_REVIEW",
        "legal_review": "LEGAL_REVIEW",
        "execution": "EXECUTION_REGISTRATION",
    },
    "payment_status_closed": ["paid", "cleared", "closed", "resolved"],
    "business_property_type_rules": {
        "high_risk_types": ["commercial", "business", "retail", "صنفی", "تجاری"]
    },
    "duplicate_risk_action": "MANAGER_REVIEW",
    "broken_promise_action": "FIELD_VISIT",
    "previous_promise_action": "STAFF_CALL",
    "default_action": "LOW_PRIORITY_MONITORING",
    "recommendation_only": True,
}


@dataclass(frozen=True)
class MunicipalMission:
    mission_id: str
    debtor_name: str
    debt_amount: float
    region: str
    zone: str
    address: str | None
    mobile: str | None
    mission_action: str
    priority: str
    reason: str
    required_document_or_notice: str
    deadline: str
    responsible_role: str
    evidence_required: list[str]
    next_escalation_step: str
    persian_instruction: str
    collector_assignment: str | None = None
    recommendation_only: bool = True


class MunicipalMissionEngine:
    """Converts official debt records into municipality rule-based missions."""

    def __init__(
        self,
        workspace: str | Path = "var/municipal_missions",
        config_path: str | Path = "config/municipal_mission_rules.json",
    ) -> None:
        self.workspace = Path(workspace)
        self.config_path = Path(config_path)

    def build(
        self,
        *,
        run_id: str,
        records: list[dict[str, Any]],
        as_of: date | None = None,
    ) -> dict[str, Any]:
        day = as_of or date.today()
        rules = self._load_rules()
        missions = [
            self._mission_for_record(run_id, index, record, rules, day)
            for index, record in enumerate(records, start=1)
        ]
        payloads = [asdict(mission) for mission in missions]
        return {
            "date": day.isoformat(),
            "run_id": run_id,
            "recommendation_only": True,
            "municipal_mission_list": payloads,
            "daily_staff_call_missions": [
                m for m in payloads if m["mission_action"] == "STAFF_CALL"
            ],
            "daily_field_visit_missions": [
                m for m in payloads if m["mission_action"] == "FIELD_VISIT"
            ],
            "daily_notice_missions": [m for m in payloads if m["mission_action"] in NOTICE_ACTIONS],
            "daily_legal_missions": [m for m in payloads if m["mission_action"] in LEGAL_ACTIONS],
            "daily_manager_review_missions": [
                m for m in payloads if m["mission_action"] == "MANAGER_REVIEW"
            ],
            "municipal_mission_summary": self._summary(payloads),
            "human_readable_manager_report": self._human_report(payloads, day),
        }

    def _mission_for_record(
        self,
        run_id: str,
        index: int,
        record: dict[str, Any],
        rules: dict[str, Any],
        day: date,
    ) -> MunicipalMission:
        action, reason = self._select_action(record, rules, day)
        priority = self._priority(record, rules, day, action)
        deadline = self._deadline(day, priority, rules)
        role = RESPONSIBLE_ROLE_BY_ACTION[action]
        required_document = self._required_document(action)
        evidence = self._evidence_required(action)
        escalation = self._next_escalation(action)
        debtor_name = str(record.get("debtor") or record.get("debtor_name") or "نامشخص")
        amount = self._money(record.get("debt_amount", 0))
        region = str(record.get("region") or "نامشخص")
        zone = str(record.get("zone") or region or "نامشخص")
        address = self._optional(record.get("address"))
        mobile = self._optional(record.get("mobile"))
        collector = self._optional(record.get("collector") or record.get("assigned_collector"))
        instruction = self._persian_instruction(
            debtor_name,
            amount,
            action,
            priority,
            reason,
            role,
            required_document,
            evidence,
            escalation,
            deadline,
        )
        return MunicipalMission(
            mission_id=f"mission-{run_id}-{index:05d}",
            debtor_name=debtor_name,
            debt_amount=amount,
            region=region,
            zone=zone,
            address=address,
            mobile=mobile,
            mission_action=action,
            priority=priority,
            reason=reason,
            required_document_or_notice=required_document,
            deadline=deadline,
            responsible_role=role,
            evidence_required=evidence,
            next_escalation_step=escalation,
            persian_instruction=instruction,
            collector_assignment=collector,
        )

    def _select_action(
        self, record: dict[str, Any], rules: dict[str, Any], day: date
    ) -> tuple[str, str]:
        status = self._clean(record.get("payment_status") or record.get("status"))
        if status in {self._clean(item) for item in rules.get("payment_status_closed", [])}:
            return (
                "LOW_PRIORITY_MONITORING",
                "پرونده پرداخت‌شده یا بسته‌شده است و فقط پایش کم‌اولویت لازم دارد.",
            )
        legal_status = self._clean(record.get("legal_status"))
        legal_actions = {
            self._clean(k): v for k, v in rules.get("legal_status_actions", {}).items()
        }
        if legal_status in legal_actions:
            action = legal_actions[legal_status]
            return action, "وضعیت حقوقی پرونده نیازمند اقدام حقوقی طبق مقررات شهرداری است."
        missing_mobile = not self._optional(record.get("mobile"))
        missing_address = not self._optional(record.get("address"))
        if missing_mobile and missing_address:
            return (
                "MANAGER_REVIEW",
                "شماره تماس و نشانی معتبر وجود ندارد؛ قبل از اقدام میدانی یا تماس، بازبینی مدیریتی لازم است.",
            )
        if self._truthy(record.get("duplicate_risk")):
            return str(
                rules.get("duplicate_risk_action", "MANAGER_REVIEW")
            ), "ریسک تکراری بودن پرونده وجود دارد و باید قبل از اقدام بررسی شود."
        if self._truthy(record.get("broken_promise_to_pay")):
            if missing_address:
                return (
                    "STAFF_CALL",
                    "وعده پرداخت شکسته شده اما نشانی معتبر موجود نیست؛ ابتدا تماس پیگیری انجام شود.",
                )
            return str(
                rules.get("broken_promise_action", "FIELD_VISIT")
            ), "وعده پرداخت قبلی شکسته شده و پیگیری میدانی لازم است."
        notice_count = self._int(record.get("previous_notice_count", 0))
        debt_amount = self._money(record.get("debt_amount", 0))
        high_threshold = float(rules.get("debt_amount_thresholds", {}).get("high", 5_000_000))
        if debt_amount >= high_threshold:
            if missing_address:
                return (
                    "STAFF_CALL",
                    "بدهی بالا است اما نشانی معتبر برای مراجعه وجود ندارد؛ ابتدا تماس و تکمیل اطلاعات انجام شود.",
                )
            action = self._notice_action(notice_count, rules)
            return action, "بدهی بالا است و پرونده باید طبق زنجیره اخطارهای شهرداری پیگیری شود."
        if self._truthy(record.get("previous_promise_to_pay")):
            if missing_mobile:
                return (
                    "FIELD_VISIT",
                    "وعده پرداخت قبلی وجود دارد اما شماره تماس در دسترس نیست؛ پیگیری میدانی لازم است.",
                )
            return str(
                rules.get("previous_promise_action", "STAFF_CALL")
            ), "پرونده دارای وعده پرداخت قبلی است و باید تماس پیگیری انجام شود."
        if missing_mobile:
            if missing_address:
                return "MANAGER_REVIEW", "اطلاعات تماس و نشانی برای اقدام عملیاتی کافی نیست."
            return (
                "FIELD_VISIT",
                "شماره تماس وجود ندارد؛ اقدام تلفنی مجاز نیست و مراجعه میدانی پیشنهاد می‌شود.",
            )
        if missing_address:
            return (
                "STAFF_CALL",
                "نشانی معتبر وجود ندارد؛ اقدام میدانی مجاز نیست و ابتدا تماس برای تکمیل نشانی لازم است.",
            )
        if self._int(record.get("previous_call_count", 0)) <= int(
            rules.get("call_escalation", {}).get("max_previous_call_count_for_staff_call", 2)
        ):
            return "STAFF_CALL", "پرونده کم‌ریسک‌تر است و تماس کارکنان برای شروع پیگیری کافی است."
        return str(
            rules.get("default_action", "LOW_PRIORITY_MONITORING")
        ), "پرونده در سطح پایش کم‌اولویت قرار دارد."

    def _notice_action(self, notice_count: int, rules: dict[str, Any]) -> str:
        escalation = rules.get("notice_escalation", {})
        if notice_count >= int(escalation.get("seal_warning_after_count", 4)):
            return "SEAL_WARNING"
        if notice_count >= int(escalation.get("notice_72h_after_count", 3)):
            return "NOTICE_72H"
        if notice_count >= int(escalation.get("notice_48h_after_count", 2)):
            return "NOTICE_48H"
        if notice_count >= int(escalation.get("notice_24h_after_count", 1)):
            return "NOTICE_24H"
        return "NOTICE_FIRST"

    def _priority(
        self, record: dict[str, Any], rules: dict[str, Any], day: date, action: str
    ) -> str:
        if action in {"COMMISSION_77_REFERRAL", "EXECUTION_REGISTRATION", "SEAL_WARNING"}:
            return "CRITICAL"
        amount = self._money(record.get("debt_amount", 0))
        age = self._debt_age_days(record, day)
        amount_thresholds = rules.get("debt_amount_thresholds", {})
        age_thresholds = rules.get("debt_age_thresholds_days", {})
        if amount >= float(amount_thresholds.get("critical", 50_000_000)) or age >= int(
            age_thresholds.get("critical", 365)
        ):
            return "CRITICAL"
        if amount >= float(amount_thresholds.get("high", 5_000_000)) or age >= int(
            age_thresholds.get("high", 180)
        ):
            return "HIGH"
        if amount >= float(amount_thresholds.get("medium", 1_000_000)) or age >= int(
            age_thresholds.get("medium", 60)
        ):
            return "MEDIUM"
        return "LOW"

    def _deadline(self, day: date, priority: str, rules: dict[str, Any]) -> str:
        hours = int(rules.get("priority_deadlines_hours", {}).get(priority, 168))
        return (datetime.combine(day, datetime.min.time()) + timedelta(hours=hours)).isoformat()

    @staticmethod
    def _required_document(action: str) -> str:
        return {
            "STAFF_CALL": "ثبت نتیجه تماس و فایل صوتی یا یادداشت تماس",
            "FIELD_VISIT": "گزارش بازدید، عکس محل و موقعیت مکانی",
            "NOTICE_FIRST": "اخطار اول ابلاغ‌شده",
            "NOTICE_24H": "اخطار ۲۴ ساعته ابلاغ‌شده",
            "NOTICE_48H": "اخطار ۴۸ ساعته ابلاغ‌شده",
            "NOTICE_72H": "اخطار ۷۲ ساعته ابلاغ‌شده",
            "SEAL_WARNING": "هشدار پلمب و مستندات ابلاغ",
            "COMMISSION_77_REFERRAL": "پرونده کامل ارجاع به کمیسیون ۷۷",
            "LEGAL_REVIEW": "گزارش بررسی حقوقی و مستندات بدهی",
            "EXECUTION_REGISTRATION": "ثبت اجرائیه و مستندات قانونی",
            "MANAGER_REVIEW": "یادداشت بررسی مدیر منطقه",
            "LOW_PRIORITY_MONITORING": "ثبت پایش کم‌اولویت",
        }[action]

    @staticmethod
    def _evidence_required(action: str) -> list[str]:
        if action == "STAFF_CALL":
            return ["نتیجه تماس", "زمان تماس", "نام اپراتور نقش‌محور"]
        if action in {"FIELD_VISIT", *NOTICE_ACTIONS}:
            return ["عکس", "موقعیت مکانی", "زمان اقدام", "گزارش نتیجه"]
        if action in LEGAL_ACTIONS:
            return ["مستندات بدهی", "سوابق اخطار", "نظر کارشناس حقوقی"]
        return ["یادداشت بررسی", "تصمیم پیشنهادی"]

    @staticmethod
    def _next_escalation(action: str) -> str:
        return {
            "STAFF_CALL": "در صورت عدم پاسخ یا عدم پرداخت، ارجاع به بازدید میدانی.",
            "FIELD_VISIT": "در صورت عدم همکاری، صدور اخطار رسمی بعدی.",
            "NOTICE_FIRST": "در صورت عدم پرداخت، اخطار ۲۴ ساعته.",
            "NOTICE_24H": "در صورت عدم پرداخت، اخطار ۴۸ ساعته.",
            "NOTICE_48H": "در صورت عدم پرداخت، اخطار ۷۲ ساعته.",
            "NOTICE_72H": "در صورت عدم پرداخت، هشدار پلمب یا بررسی مدیر منطقه.",
            "SEAL_WARNING": "در صورت عدم اقدام مؤدی، بررسی حقوقی و کمیسیون ۷۷.",
            "COMMISSION_77_REFERRAL": "پیگیری رأی و اجرای تصمیم کمیسیون.",
            "LEGAL_REVIEW": "در صورت تأیید، ارجاع به کمیسیون ۷۷ یا ثبت اجرائیه.",
            "EXECUTION_REGISTRATION": "پیگیری عملیات اجرایی طبق قانون.",
            "MANAGER_REVIEW": "پس از تکمیل اطلاعات، تعیین مأموریت تماس، اخطار یا بازدید.",
            "LOW_PRIORITY_MONITORING": "پایش دوره‌ای تا تغییر وضعیت بدهی.",
        }[action]

    def _persian_instruction(
        self,
        debtor_name: str,
        amount: float,
        action: str,
        priority: str,
        reason: str,
        role: str,
        document: str,
        evidence: list[str],
        escalation: str,
        deadline: str,
    ) -> str:
        return (
            f"پرونده {debtor_name} با بدهی {amount:,.0f} به دلیل {reason} "
            f"باید مأموریت {action} با اولویت {priority} دریافت کند. "
            f"مسئول اقدام: {self._role_fa(role)}. مدرک لازم: {document}. "
            f"شواهد لازم: {'، '.join(evidence)}. "
            f"مهلت انجام: {deadline}. گام بعدی: {escalation}"
        )

    def _summary(self, missions: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "recommendation_only": True,
            "total_missions": len(missions),
            "critical_missions": sum(
                1 for mission in missions if mission["priority"] == "CRITICAL"
            ),
            "high_priority_missions": sum(
                1 for mission in missions if mission["priority"] == "HIGH"
            ),
            "missions_by_action_type": self._count_by(missions, "mission_action"),
            "missions_by_responsible_role": self._count_by(missions, "responsible_role"),
            "missing_data_cases": sum(
                1 for mission in missions if not mission.get("mobile") or not mission.get("address")
            ),
        }

    def _human_report(self, missions: list[dict[str, Any]], day: date) -> str:
        summary = self._summary(missions)
        urgent = sorted(
            missions,
            key=lambda mission: (self._priority_rank(mission["priority"]), mission["debt_amount"]),
            reverse=True,
        )[:20]
        missing = [
            mission
            for mission in missions
            if not mission.get("mobile") or not mission.get("address")
        ]
        lines = [
            f"# گزارش روزانه مأموریت‌های وصول شهرداری - {day.isoformat()}",
            "",
            "این گزارش صرفاً پیشنهاد عملیاتی است و هیچ پیام، اخطار واقعی، اقدام حقوقی یا تغییر در داده‌های ایران‌سیستم انجام نمی‌دهد.",
            "",
            f"- تعداد کل مأموریت‌ها: {summary['total_missions']}",
            f"- مأموریت‌های بحرانی: {summary['critical_missions']}",
            f"- مأموریت‌های با اولویت بالا: {summary['high_priority_missions']}",
            f"- پرونده‌های دارای نقص اطلاعات: {summary['missing_data_cases']}",
            "",
            "## مأموریت‌ها بر اساس نوع اقدام",
        ]
        lines.extend(
            f"- {action}: {count}"
            for action, count in sorted(summary["missions_by_action_type"].items())
        )
        lines.append("")
        lines.append("## مأموریت‌ها بر اساس نقش مسئول")
        lines.extend(
            f"- {role}: {count}"
            for role, count in sorted(summary["missions_by_responsible_role"].items())
        )
        lines.append("")
        lines.append("## ۲۰ پرونده فوری")
        for mission in urgent:
            lines.append(
                f"- {mission['debtor_name']} | بدهی: {mission['debt_amount']:,.0f} | اقدام: {mission['mission_action']} | اولویت: {mission['priority']} | نقش مسئول: {mission['responsible_role']}"
            )
        lines.append("")
        lines.append("## پرونده‌های نقص اطلاعات")
        for mission in missing[:20]:
            missing_parts = []
            if not mission.get("mobile"):
                missing_parts.append("شماره تماس")
            if not mission.get("address"):
                missing_parts.append("نشانی")
            lines.append(f"- {mission['debtor_name']}: نقص {' و '.join(missing_parts)}")
        lines.append("")
        lines.append("## اقدامات پیشنهادی مدیر")
        lines.extend(
            [
                "- مأموریت‌های بحرانی را در ابتدای روز بین نقش‌های مسئول توزیع کنید.",
                "- پرونده‌های فاقد شماره تماس یا نشانی را قبل از اقدام میدانی یا تماس تکمیل اطلاعات کنید.",
                "- برای اخطارها و بازدیدها عکس، موقعیت مکانی و گزارش نتیجه را الزامی کنید.",
                "- هیچ اقدام واقعی، پیام، پلمب، ارجاع حقوقی یا تغییر در ایران‌سیستم بدون تأیید انسانی انجام نشود.",
            ]
        )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _role_fa(role: str) -> str:
        return {
            "CALL_OPERATOR": "اپراتور تماس",
            "FIELD_COLLECTOR": "نیروی میدانی وصول",
            "LEGAL_OPERATOR": "کارشناس حقوقی",
            "REGIONAL_MANAGER": "مدیر منطقه",
            "FINANCE_OPERATOR": "کارشناس مالی",
            "ADMIN": "امور اداری",
        }[role]

    def _debt_age_days(self, record: dict[str, Any], day: date) -> int:
        value = record.get("due_date") or record.get("debt_date") or record.get("created_at")
        if not value:
            return 0
        try:
            return max(0, (day - datetime.fromisoformat(str(value)).date()).days)
        except ValueError:
            return 0

    def _load_rules(self) -> dict[str, Any]:
        rules = json.loads(json.dumps(DEFAULT_MISSION_RULES))
        if self.config_path.exists():
            configured = json.loads(self.config_path.read_text())
            for key, value in configured.items():
                if isinstance(value, dict) and isinstance(rules.get(key), dict):
                    rules[key] = {**rules[key], **value}
                else:
                    rules[key] = value
        return rules

    @staticmethod
    def _count_by(rows: list[dict[str, Any]], field_name: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in rows:
            key = str(row.get(field_name) or "نامشخص")
            counts[key] = counts.get(key, 0) + 1
        return counts

    @staticmethod
    def _priority_rank(priority: str) -> int:
        return {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}.get(priority, 0)

    @staticmethod
    def _truthy(value: Any) -> bool:
        return str(value).strip().lower() in {"1", "true", "yes", "y", "broken", "بله"}

    @staticmethod
    def _clean(value: Any) -> str:
        return str(value).strip().lower() if value not in (None, "") else ""

    @staticmethod
    def _optional(value: Any) -> str | None:
        return str(value).strip() if value not in (None, "") else None

    @staticmethod
    def _int(value: Any) -> int:
        if value in (None, ""):
            return 0
        return int(float(str(value).replace(",", "")))

    @staticmethod
    def _money(value: Any) -> float:
        if value in (None, ""):
            return 0.0
        return round(float(str(value).replace("$", "").replace(",", "")), 2)
