"""Content Library — a read model over EVERY content the factory has ever made.

Not a new store: it aggregates Campaign / PlatformContent / Asset / Script /
Publication / AnalyticsSnapshot / RevenueEntry / CostLog that already exist,
including content created before Governance / tenant scope / the Intelligence
Upgrade. Legacy rows never crash — missing fields are shown as LEGACY /
NOT_APPLICABLE / —.
"""
from app.library.service import (
    add_platform_to_campaign,
    content_detail,
    library_stats,
    list_content,
)

__all__ = ["list_content", "content_detail", "library_stats", "add_platform_to_campaign"]
