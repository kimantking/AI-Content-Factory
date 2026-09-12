"""Explicit, campaign-scoped allowances; never alter global settings."""
PLANS = {"PREVIEW": (1, 3.5), "THREE_SCENES": (3, 10.0)}


def allowance(campaign):
    if campaign is None or campaign.video_mode != "VEO":
        return (0, 0.0)
    return PLANS.get(campaign.video_plan, (0, 0.0))
