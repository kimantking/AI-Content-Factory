from __future__ import annotations

import hashlib
import os

from app.db.base import session_scope
from app.db.models import Asset

CRITICAL = {"render", "thumbnail", "subtitle", "carousel"}
REGENERATABLE = {"image", "audio", "chart", "music"}


def classify(asset_type: str, path: str) -> str:
    p = (path or "").replace("\\", "/")
    if "/_cache/" in p or "/_work/" in p:
        return "CACHE"
    if "/temp/" in p or p.endswith(".tmp"):
        return "TEMP"
    if asset_type in CRITICAL:
        return "CRITICAL"
    if asset_type in REGENERATABLE:
        return "REGENERATABLE"
    return "REGENERATABLE"


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_assets(*, limit: int = 5000, repair_status: bool = True) -> dict:
    """Check every asset file. MISSING => file gone; CORRUPTED => size 0 or
    unreadable. Records the status back on the asset row."""
    result = {"checked": 0, "ok": 0, "missing": [], "corrupted": [],
              "by_class": {"CRITICAL": 0, "REGENERATABLE": 0, "CACHE": 0, "TEMP": 0}}
    with session_scope() as s:
        for a in s.query(Asset).limit(limit):
            result["checked"] += 1
            cls = classify(a.asset_type, a.storage_path or "")
            result["by_class"][cls] = result["by_class"].get(cls, 0) + 1
            if not a.storage_path or not os.path.exists(a.storage_path):
                result["missing"].append(a.id)
                if repair_status:
                    a.status = "MISSING_ASSET"
                continue
            try:
                sz = os.path.getsize(a.storage_path)
                if sz == 0:
                    raise OSError("zero bytes")
                with open(a.storage_path, "rb") as f:
                    f.read(1)
            except OSError:
                result["corrupted"].append(a.id)
                if repair_status:
                    a.status = "CORRUPTED"
                continue
            result["ok"] += 1
            if repair_status and a.status in ("MISSING_ASSET", "CORRUPTED"):
                a.status = "SUCCESS"

    if result["missing"] or result["corrupted"]:
        from app.ops.alerts import raise_alert

        raise_alert("HIGH", "storage_integrity",
                    f"{len(result['missing'])} missing / {len(result['corrupted'])} corrupted asset(s)",
                    {"missing": result["missing"][:10], "corrupted": result["corrupted"][:10]})
    return result
