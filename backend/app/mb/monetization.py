"""Monetization (§26-§35, §64-§69) — deterministic analysis + safety guards.

MonetizationAgent evaluates which revenue model fits a channel from its data.
Sponsor-content guard, commercial-intent / sponsored-density guards, and
affiliate-disclosure enforcement. No fake reviews / scarcity / discounts (§65).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Campaign, RevenueEntry
from app.db.models_mb import Channel

REVENUE_MODELS = ("PLATFORM_AD_REVENUE", "AFFILIATE", "SPONSOR", "PRODUCT",
                  "SERVICE_LEAD", "MEMBERSHIP", "OTHER")

_FAKE_SCARCITY = ("마감 임박", "품절 임박", "딱 오늘만", "선착순 마감", "곧 사라집니다", "한정 수량")
_FAKE_SOCIAL = ("모두가 샀", "다들 쓰는", "후기 폭발", "완판", "역대급 후기")
_HIDDEN_AD = ("협찬 아님", "내돈내산")  # only a problem when a sponsor deal exists


def profit_center(db: Session, *, channel_id: str, days: int = 30) -> dict:
    cut = datetime.now(timezone.utc) - timedelta(days=days)
    from app.db.models import CostLog

    rev_actual = float(db.query(func.coalesce(func.sum(RevenueEntry.amount), 0.0))
                       .filter(RevenueEntry.channel_id == channel_id,
                               RevenueEntry.occurred_at >= cut,
                               RevenueEntry.is_estimate.is_(False)).scalar() or 0.0)
    rev_est = float(db.query(func.coalesce(func.sum(RevenueEntry.amount), 0.0))
                    .filter(RevenueEntry.channel_id == channel_id,
                            RevenueEntry.occurred_at >= cut,
                            RevenueEntry.is_estimate.is_(True)).scalar() or 0.0)
    cost = float(db.query(func.coalesce(func.sum(CostLog.amount_usd), 0.0))
                 .filter(CostLog.channel_id == channel_id, CostLog.created_at >= cut).scalar() or 0.0)
    n_content = int(db.query(func.count(Campaign.id))
                    .filter(Campaign.channel_id == channel_id, Campaign.created_at >= cut).scalar() or 0)
    net = rev_actual - cost
    return {
        "period_days": days,
        "revenue_actual_usd": round(rev_actual, 2),
        "revenue_estimated_usd": round(rev_est, 2),      # kept separate — never summed with actual
        "production_cost_usd": round(cost, 2),
        "net_profit_usd": round(net, 2),
        "profit_margin": round(net / rev_actual, 3) if rev_actual > 0 else None,
        "content_count": n_content,
        "cost_per_content_usd": round(cost / n_content, 3) if n_content else None,
        "revenue_per_content_usd": round(rev_actual / n_content, 3) if n_content else None,
        "profit_per_content_usd": round(net / n_content, 3) if n_content else None,
    }


def monetization_agent(db: Session, channel: Channel) -> dict:
    pc = profit_center(db, channel_id=channel.id)
    n = pc["content_count"]
    fits: dict[str, dict] = {}

    ad_ok = n >= 10 and pc["revenue_actual_usd"] > 0
    fits["PLATFORM_AD_REVENUE"] = {"fit": 0.7 if ad_ok else 0.4,
                                   "why": "steady output + platform monetisation eligible" if ad_ok
                                   else "needs more consistent output / monetisation approval"}
    edu = channel.channel_type in ("YOUTUBE_LONG", "NAVER_BLOG", "LINKEDIN")
    fits["AFFILIATE"] = {"fit": 0.65 if edu else 0.45,
                         "why": "how-to / review formats convert well" if edu else "possible, lower intent"}
    fits["SPONSOR"] = {"fit": 0.6 if n >= 20 else 0.3,
                       "why": "audience size / niche attractive to sponsors" if n >= 20
                       else "build track record first"}
    fits["PRODUCT"] = {"fit": 0.4 if (channel.primary_objective == "PROFIT") else 0.25,
                       "why": "own offer only where audience trust is established"}
    fits["SERVICE_LEAD"] = {"fit": 0.5 if channel.channel_type == "LINKEDIN" else 0.2, "why": "B2B lean"}
    fits["MEMBERSHIP"] = {"fit": 0.35 if n >= 40 else 0.15, "why": "needs a loyal base"}

    primary = max(fits.items(), key=lambda kv: kv[1]["fit"])[0]
    return {
        "channel_id": channel.id,
        "profit_center": pc,
        "model_fit": {k: round(v["fit"], 2) for k, v in fits.items()},
        "reasons": {k: v["why"] for k, v in fits.items()},
        "recommended_primary_model": primary,
        "notes": ["estimate and actual revenue are tracked separately and never summed",
                  "no fake reviews / scarcity / discounts / hidden ads (policy)"],
    }


def sponsor_content_guard(*, sponsor_deal: dict, script_text: str, verified_fact_texts: list[str],
                          brand_risk_policy: dict, platform: str | None = None) -> dict:
    """BLOCK if a sponsor requirement collides with facts / compliance / platform /
    brand policy (§34). Compliance is never overridden by a paid deal (§49)."""
    findings: list[str] = []
    low = (script_text or "").lower()

    for claim in sponsor_deal.get("forbidden_claims", []):
        if claim and claim.lower() in low:
            findings.append(f"sponsor forbidden_claim present in script: '{claim}'")
    # a required mention that contradicts a verified fact
    fact_blob = " ".join(verified_fact_texts).lower()
    for m in sponsor_deal.get("required_mentions", []):
        neg = any(x in m for x in ("최고", "1위", "유일", "부작용 없", "100%"))
        if neg and m.lower() not in fact_blob:
            findings.append(f"required_mention makes an unverifiable superlative claim: '{m}'")
    # brand-level blocked sponsor categories
    for cat in brand_risk_policy.get("blocked_sponsor_categories", []):
        if cat and cat.lower() in (sponsor_deal.get("sponsor", "") + " " +
                                   str(sponsor_deal.get("deliverables", ""))).lower():
            findings.append(f"sponsor category blocked by brand policy: '{cat}'")
    # hidden-ad phrasing while a sponsor deal is active
    if any(p in (script_text or "") for p in _HIDDEN_AD):
        findings.append("script implies 'not sponsored' while a sponsor deal exists")

    verdict = "BLOCK" if findings else "OK"
    return {"verdict": verdict, "findings": findings}


def commercial_guards(*, recent_contents: list[dict], script_text: str) -> dict:
    """CommercialDensity + SponsoredDensity + fake-tactic scan (§65-§68)."""
    n = max(1, len(recent_contents))
    sponsored = sum(1 for c in recent_contents if c.get("is_sponsored"))
    commercial = sum(1 for c in recent_contents
                     if c.get("is_sponsored") or c.get("has_affiliate") or c.get("has_offer"))
    sponsored_density = round(sponsored / n, 3)
    commercial_density = round(commercial / n, 3)

    fake = []
    for p in _FAKE_SCARCITY:
        if p in (script_text or ""):
            fake.append(f"fake_scarcity:{p}")
    for p in _FAKE_SOCIAL:
        if p in (script_text or ""):
            fake.append(f"fake_social_proof:{p}")

    warnings = []
    if sponsored_density > 0.4:
        warnings.append(f"sponsored density {sponsored_density:.0%} of last {n} — audience-trust risk")
    if commercial_density > 0.6:
        warnings.append(f"commercial density {commercial_density:.0%} — too salesy for this channel")
    return {
        "sponsored_density": sponsored_density,
        "commercial_density": commercial_density,
        "fake_tactics": fake,
        "verdict": "BLOCK" if fake else ("WARN" if warnings else "OK"),
        "warnings": warnings,
    }


def enforce_affiliate_disclosure(script_text: str, *, has_affiliate_link: bool,
                                 default_disclosure: str, platform_disclosure_rules: dict | None = None
                                 ) -> dict:
    """Affiliate content must keep the required disclosure — it is never auto-removed
    (§32, §117). Returns the (possibly amended) script + status."""
    if not has_affiliate_link:
        return {"status": "N/A", "script": script_text}
    text = script_text or ""
    markers = ("제휴", "affiliate", "커미션", "수수료", "파트너스", "쿠팡 파트너스", "유료 광고 포함")
    present = any(m in text for m in markers) or (default_disclosure and default_disclosure[:8] in text)
    if present:
        return {"status": "PRESENT", "script": text}
    disclosure = default_disclosure or "이 콘텐츠에는 제휴 링크가 포함되어 있으며, 구매 시 수수료를 받을 수 있습니다."
    amended = (disclosure.strip() + "\n\n" + text).strip()
    return {"status": "ADDED", "script": amended, "disclosure": disclosure}
