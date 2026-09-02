"""License registry + interpretation (§8, §9, §10, §66).

Code license ≠ model license ≠ content/asset license — kept as separate `kind`s.
Interpretation is rule-based, not string matching. A license we don't recognise
is `UNKNOWN` (never assumed permissive).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models_gov import LicenseRegistry

# key -> (kind, commercial, derivative, attribution_required, share_alike, expiration_possible, redistribution_limit)
_SEED = {
    "CC0":                 ("CONTENT", "YES", "YES", False, False, False, "NONE"),
    "PUBLIC_DOMAIN":       ("CONTENT", "YES", "YES", False, False, False, "NONE"),
    "CC-BY":               ("CONTENT", "YES", "YES", True,  False, False, "NONE"),
    "CC-BY-SA":            ("CONTENT", "YES", "YES", True,  True,  False, "SHARE_ALIKE"),
    "CC-BY-NC":            ("CONTENT", "NO",  "YES", True,  False, False, "NONCOMMERCIAL"),
    "CC-BY-ND":            ("CONTENT", "YES", "NO",  True,  False, False, "NO_DERIVATIVE"),
    "COMMERCIAL_STOCK":    ("ASSET",   "YES", "YES", False, False, True,  "PROVIDER_TERMS"),
    "EDITORIAL_STOCK":     ("ASSET",   "NO",  "LIMITED", False, False, True, "EDITORIAL_ONLY"),
    "USER_OWNED":          ("ASSET",   "YES", "YES", False, False, False, "NONE"),
    "USER_PERMISSION":     ("ASSET",   "YES", "YES", False, False, True,  "SCOPE_LIMITED"),
    "PROVIDER_MUSIC":      ("ASSET",   "YES", "LIMITED", True, False, True, "PLATFORM_LIMITED"),
    "MODEL_OUTPUT_COMMERCIAL": ("MODEL", "YES", "YES", False, False, False, "MODEL_TERMS"),
    "MODEL_OUTPUT_NONCOMMERCIAL": ("MODEL", "NO", "YES", False, False, False, "MODEL_TERMS"),
    "UNKNOWN":             ("CONTENT", "UNKNOWN", "UNKNOWN", False, False, True, "UNKNOWN"),
    # software licenses kept only so code/asset are not confused (§9)
    "MIT": ("SOFTWARE", "YES", "YES", True, False, False, "NONE"),
    "APACHE-2.0": ("SOFTWARE", "YES", "YES", True, False, False, "NONE"),
    "GPL-3.0": ("SOFTWARE", "YES", "YES", True, True, False, "COPYLEFT"),
}


def seed_license_registry(db: Session) -> int:
    n = 0
    for key, (kind, comm, deriv, attr, sa, exp, redis) in _SEED.items():
        if db.query(LicenseRegistry).filter_by(key=key).first():
            continue
        db.add(LicenseRegistry(
            key=key, kind=f"{kind}_LICENSE", name=key, commercial_allowed=comm,
            derivative_allowed=deriv, attribution_required=attr, share_alike=sa,
            expiration_possible=exp, redistribution_limit=redis,
            last_verified_at=datetime.now(timezone.utc),
        ))
        n += 1
    db.flush()
    return n


def interpret(db: Session, license_key: str) -> dict:
    """Return the effective rules for a license key. Unknown → conservative."""
    key = (license_key or "UNKNOWN").upper().replace(" ", "_")
    row = db.query(LicenseRegistry).filter_by(key=key).first()
    if row is None:
        if key in _SEED:
            seed_license_registry(db)
            row = db.query(LicenseRegistry).filter_by(key=key).first()
    if row is None:
        return {"key": key, "known": False, "kind": "CONTENT_LICENSE",
                "commercial_allowed": "UNKNOWN", "derivative_allowed": "UNKNOWN",
                "attribution_required": False, "share_alike": False,
                "expiration_possible": True, "redistribution_limit": "UNKNOWN"}
    return {
        "key": row.key, "known": True, "kind": row.kind,
        "commercial_allowed": row.commercial_allowed,
        "derivative_allowed": row.derivative_allowed,
        "attribution_required": row.attribution_required,
        "share_alike": row.share_alike,
        "expiration_possible": row.expiration_possible,
        "redistribution_limit": row.redistribution_limit,
        "is_software": row.kind == "SOFTWARE_LICENSE",
    }


def commercial_ok(db: Session, license_key: str) -> str:
    """YES | NO | UNKNOWN — a SOFTWARE license used for an asset is always UNKNOWN
    for that asset (§9)."""
    r = interpret(db, license_key)
    if r.get("is_software"):
        return "UNKNOWN"
    return r["commercial_allowed"]
