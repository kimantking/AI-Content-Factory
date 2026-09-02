from __future__ import annotations

import hashlib


def media_hash(asset_hashes: list[str]) -> str:
    joined = "|".join(sorted(h for h in asset_hashes if h))
    return hashlib.sha256(joined.encode()).hexdigest()[:16]


def make_idempotency_key(*, platform: str, account_id: str, content_id: str,
                         scheduled_at: str, media_hash_: str) -> str:
    raw = f"{platform}|{account_id}|{content_id}|{scheduled_at}|{media_hash_}"
    return hashlib.sha256(raw.encode()).hexdigest()[:40]
