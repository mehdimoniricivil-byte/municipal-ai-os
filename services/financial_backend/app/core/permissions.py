from __future__ import annotations

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "brokerage_head": frozenset({"*"}),
    "executive_manager": frozenset({
        "dashboard.view", "collection.view", "statement.view", "statement.manage",
        "report.view", "audit.view", "statement.approve",
    }),
    "finance_manager": frozenset({
        "dashboard.view", "expense.view", "expense.create", "expense.edit",
        "payment.view", "payment.create", "report.view", "statement.view", "statement.approve",
    }),
    "expert": frozenset({
        "collection.upload", "collection.upload_status",
    }),
    "tri_manager": frozenset({
        "dashboard.view", "report.view", "statement.view", "statement.approve",
    }),
}


def has_permission(role: str, permission: str) -> bool:
    permissions = ROLE_PERMISSIONS.get(role, frozenset())
    return "*" in permissions or permission in permissions
