from __future__ import annotations

import os
import uuid

import pytest

from app.db.base import session_scope
from app.db.models import BackupManifest, Campaign
from app.ops.backup import _migration_revision, restore_to, run_backup, verify_backup

pytestmark = pytest.mark.integration

_HEAD = _migration_revision()   # whatever the DB is migrated to (currently 0009_intelligence)


def test_full_backup_verify_restore_roundtrip():
    marker = f"backup-roundtrip-{uuid.uuid4().hex[:8]}"
    cid = str(uuid.uuid4())
    with session_scope() as s:
        s.add(Campaign(id=cid, topic=marker, platforms=["youtube_shorts"], status="SUCCESS"))

    b = run_backup("full")
    assert b["size_bytes"] > 1000 and len(b["checksum_sha256"]) == 64
    assert os.path.isfile(b["path"])

    with session_scope() as s:
        m = s.get(BackupManifest, b["backup_id"])
        assert m.status == "CREATED"
        assert m.migration_revision == _HEAD
        assert m.app_version

    v = verify_backup(b["backup_id"])
    assert v["ok"] is True
    with session_scope() as s:
        assert s.get(BackupManifest, b["backup_id"]).status == "VERIFIED"

    # BACKUP IS NOT PASS UNTIL RESTORE
    r = restore_to(b["backup_id"], "acf_restore_test")
    assert r["ok"] is True
    assert r["counts"]["migration_revision"] == _HEAD
    # the marker campaign made it into the restored database
    from sqlalchemy import create_engine, text

    from app.config import get_settings
    from urllib.parse import urlparse

    p = urlparse(get_settings().sync_database_url)
    tgt = f"postgresql+psycopg://{p.username}:{p.password}@{p.hostname}:{p.port}/acf_restore_test"
    eng = create_engine(tgt)
    with eng.connect() as c:
        found = c.execute(text("SELECT count(*) FROM campaigns WHERE topic = :t"),
                          {"t": marker}).scalar()
    eng.dispose()
    assert found == 1

    with session_scope() as s:
        assert s.get(BackupManifest, b["backup_id"]).restore_tested_at is not None


def test_restore_refuses_source_database():
    b = run_backup("full")
    from app.config import get_settings
    from urllib.parse import urlparse

    src_db = urlparse(get_settings().sync_database_url).path.lstrip("/")
    r = restore_to(b["backup_id"], src_db)
    assert r["ok"] is False and "source" in r["reason"].lower()


def test_verify_detects_tampered_backup():
    b = run_backup("full")
    with open(b["path"], "r+b") as f:
        f.seek(64)
        f.write(b"\x00\x00\x00\x00")
    v = verify_backup(b["backup_id"])
    assert v["ok"] is False
    with session_scope() as s:
        assert s.get(BackupManifest, b["backup_id"]).status == "FAILED"


def test_storage_backup_manifest():
    b = run_backup("storage")
    assert os.path.isfile(b["path"]) and len(b["checksum_sha256"]) == 64
    with session_scope() as s:
        m = s.get(BackupManifest, b["backup_id"])
        assert m.kind == "storage" and m.method == "tar.gz"


def test_retention_prunes_old_manifests(_ops_defaults):
    _ops_defaults.backup_retention_days = 7
    from datetime import datetime, timedelta, timezone

    old_path = os.path.join(_ops_defaults.backup_dir, "OLD.dump")
    os.makedirs(_ops_defaults.backup_dir, exist_ok=True)
    with open(old_path, "wb") as f:
        f.write(b"x" * 100)
    with session_scope() as s:
        s.add(BackupManifest(kind="full", storage_location=old_path,
                             created_at=datetime.now(timezone.utc) - timedelta(days=30)))
    run_backup("full")   # triggers retention
    with session_scope() as s:
        assert s.query(BackupManifest).filter_by(storage_location=old_path).count() == 0
    assert not os.path.exists(old_path)
