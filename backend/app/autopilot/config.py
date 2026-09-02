from __future__ import annotations

from app.config import get_settings

AUTOPILOT_MODES = ["OFF", "SHADOW", "SUGGEST_ONLY", "SEMI_AUTO", "FULL_AUTO"]

# Values the AI/LLM may NEVER change. Enforced here in code — a prompt that asks
# to change one of these is rejected, not obeyed.
HARD_RULE_KEYS = {
    "autopilot_daily_hard_budget_usd",
    "autopilot_monthly_hard_budget_usd",
    "autopilot_daily_post_limit",
    "autopilot_blocked_topics",
    "autopilot_blocked_keywords",
    "autopilot_min_compliance_score",
    "autopilot_emergency_stop",
}


class HardRuleViolation(Exception):
    pass


def enforce_hard_rules(proposed_changes: dict, *, actor: str = "ai") -> None:
    """Raise if a non-human actor tries to change a hard rule."""
    if actor == "user":
        return
    hit = HARD_RULE_KEYS & set(proposed_changes)
    if hit:
        raise HardRuleViolation(
            f"actor '{actor}' may not modify hard rules: {sorted(hit)}"
        )


def snapshot_config() -> dict:
    s = get_settings()
    keys = [
        "autopilot_mode", "autopilot_objective", "autopilot_target_country", "autopilot_language",
        "autopilot_daily_content_min", "autopilot_daily_content_max",
        "autopilot_daily_budget_usd", "autopilot_monthly_budget_usd",
        "autopilot_trend_reserve_ratio", "autopilot_min_opportunity_score",
        "autopilot_min_fact_score", "autopilot_max_risk_level", "autopilot_exploration_ratio",
        "autopilot_stage1_keep", "autopilot_stage2_keep", "opportunity_formula_version",
        "autopilot_config_version", "autopilot_publish_all_platforms",
        "autopilot_platform_opportunity_threshold",
        "autopilot_daily_hard_budget_usd", "autopilot_monthly_hard_budget_usd",
        "autopilot_daily_post_limit", "autopilot_blocked_topics", "autopilot_blocked_keywords",
        "autopilot_min_compliance_score", "autopilot_emergency_stop",
    ]
    return {k: getattr(s, k) for k in keys}


def apply_config(session, changes: dict, *, actor: str = "user") -> str:
    """Persist a new AutopilotConfigVersion and mutate the live settings.
    Hard rules are only mutable by actor='user'."""
    from datetime import datetime, timezone

    from app.db.models import AutopilotConfigVersion

    enforce_hard_rules(changes, actor=actor)
    s = get_settings()
    for k, v in changes.items():
        if hasattr(s, k):
            setattr(s, k, v)
    new_version = f"v{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    s.autopilot_config_version = new_version
    for row in session.query(AutopilotConfigVersion).filter_by(is_active=True):
        row.is_active = False
    session.add(AutopilotConfigVersion(version=new_version, config=snapshot_config(),
                                       changed_by=actor, is_active=True))
    session.flush()
    return new_version


_RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def risk_rank(level: str) -> int:
    return _RISK_ORDER.get(level.upper(), 1)


def topic_blocked(topic: str) -> str | None:
    """Return the matched block term, or None."""
    s = get_settings()
    low = topic.lower()
    for t in (s.autopilot_blocked_topics or []):
        if t and t.lower() in low:
            return f"topic:{t}"
    for kw in (s.autopilot_blocked_keywords or []):
        if kw and kw.lower() in low:
            return f"keyword:{kw}"
    return None
