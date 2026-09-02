from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from app.config import get_settings
from app.db.base import session_scope
from app.db.models import BackupManifest

# Asset classes for storage backup (Phase 5 §29)
CRITICAL_ASSET_TYPES = {"render", "thumbnail", "subtitle", "carousel"}
REGENERATABLE_ASSET_TYPES = {"image", "audio", "chart", "music"}


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _dsn_parts(dsn: str) -> dict:
    p = urlparse(dsn)
    return {"host": p.hostname or "localhost", "port": str(p.port or 5432),
            "user": p.username or "acf", "password": p.password or "acf",
            "db": (p.path or "/acf").lstrip("/")}


def _pg_tool(tool: str) -> list[str]:
    """Resolve pg_dump / pg_restore / psql: explicit setting -> PATH -> the
    postgres container via `docker exec`."""
    s = get_settings()
    explicit = {"pg_dump": s.pg_dump_cmd, "pg_restore": s.pg_restore_cmd}.get(tool)
    if explicit:
        return [explicit]
    onpath = shutil.which(tool)
    if onpath:
        return [onpath]
    if shutil.which("docker"):
        return ["docker", "exec", "-i", s.postgres_container, tool]
    raise RuntimeError(f"{tool} not found (set {tool.upper()}_CMD or run inside a container with libpq)")


def _env_for(parts: dict) -> dict:
    e = dict(os.environ)
    e.update({"PGPASSWORD": parts["password"]})
    return e


def _dump_target_host(parts: dict, tool_cmd: list[str]) -> str:
    # inside the container, the db is on localhost:5432
    return "localhost" if tool_cmd[:1] == ["docker"] else parts["host"]
def _dump_target_port(parts: dict, tool_cmd: list[str]) -> str:
    return "5432" if tool_cmd[:1] == ["docker"] else parts["port"]


def _migration_revision() -> str:
    try:
        from sqlalchemy import text

        from app.db.base import engine

        with engine.connect() as c:
            return c.execute(text("SELECT version_num FROM alembic_version")).scalar() or ""
    except Exception:  # noqa: BLE001
        return ""


def run_backup(kind: str = "full") -> dict:
    s = get_settings()
    Path(s.backup_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if kind == "storage":
        return _run_storage_backup(ts)

    parts = _dsn_parts(s.sync_database_url)
    cmd = _pg_tool("pg_dump")
    out_path = os.path.join(s.backup_dir, f"{ts}_full.dump")
    full = cmd + ["-Fc", "-h", _dump_target_host(parts, cmd), "-p", _dump_target_port(parts, cmd),
                  "-U", parts["user"], "-d", parts["db"], "--no-owner", "--no-privileges"]
    with open(out_path, "wb") as f:
        proc = subprocess.run(full, stdout=f, stderr=subprocess.PIPE,
                              env=_env_for(parts), timeout=600)
    if proc.returncode != 0:
        _fail_manifest(kind, out_path, proc.stderr.decode(errors="replace")[-500:])
        raise RuntimeError(f"pg_dump failed: {proc.stderr.decode(errors='replace')[-300:]}")

    encryption = "none"
    if s.backup_encryption_key:
        enc_path = out_path + ".enc"
        _encrypt_file(out_path, enc_path, s.backup_encryption_key)
        os.remove(out_path)
        out_path = enc_path
        encryption = "fernet"

    size = os.path.getsize(out_path)
    checksum = _sha256(out_path)
    with session_scope() as sess:
        m = BackupManifest(kind="full", app_version=s.app_version,
                           db_version="postgres", migration_revision=_migration_revision(),
                           method="pg_dump", size_bytes=size, checksum_sha256=checksum,
                           storage_location=str(Path(out_path).resolve()),
                           encryption=encryption, status="CREATED")
        sess.add(m)
        sess.flush()
        mid = m.id
    _apply_retention()
    return {"backup_id": mid, "path": out_path, "size_bytes": size,
            "checksum_sha256": checksum, "encryption": encryption}


def _run_storage_backup(ts: str) -> dict:
    s = get_settings()
    from app.db.models import Asset

    tar_path = os.path.join(s.backup_dir, f"{ts}_storage.tar.gz")
    included = 0
    with session_scope() as sess, tarfile.open(tar_path, "w:gz") as tar:
        for a in sess.query(Asset).all():
            if a.asset_type in (CRITICAL_ASSET_TYPES | REGENERATABLE_ASSET_TYPES) \
                    and a.storage_path and os.path.isfile(a.storage_path):
                tar.add(a.storage_path, arcname=f"assets/{a.id}{Path(a.storage_path).suffix}")
                included += 1
    size = os.path.getsize(tar_path)
    checksum = _sha256(tar_path)
    with session_scope() as sess:
        m = BackupManifest(kind="storage", app_version=s.app_version, method="tar.gz",
                           size_bytes=size, checksum_sha256=checksum,
                           storage_location=str(Path(tar_path).resolve()), status="CREATED",
                           meta={"assets": included})
        sess.add(m)
        sess.flush()
        mid = m.id
    return {"backup_id": mid, "path": tar_path, "assets": included, "checksum_sha256": checksum}


def verify_backup(backup_id: str) -> dict:
    s = get_settings()
    with session_scope() as sess:
        m = sess.get(BackupManifest, backup_id)
        if m is None:
            return {"ok": False, "reason": "manifest not found"}
        loc = m.storage_location
        kind = m.kind
        recorded = m.checksum_sha256
    if not os.path.isfile(loc):
        _set_status(backup_id, "FAILED")
        return {"ok": False, "reason": "backup file missing"}
    if _sha256(loc) != recorded:
        _set_status(backup_id, "FAILED")
        return {"ok": False, "reason": "checksum mismatch"}
    if kind == "full" and not loc.endswith(".enc"):
        try:
            _run_restore_list(loc)
        except Exception as e:  # noqa: BLE001
            _set_status(backup_id, "FAILED")
            return {"ok": False, "reason": f"pg_restore --list failed: {e}"}
    _set_status(backup_id, "VERIFIED", verified=True)
    return {"ok": True, "checksum_sha256": recorded}


def _run_restore_list(path: str) -> None:
    cmd = _pg_tool("pg_restore")
    if cmd[:1] == ["docker"]:
        with open(path, "rb") as f:
            proc = subprocess.run(cmd + ["--list"], stdin=f, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, timeout=120)
    else:
        proc = subprocess.run(cmd + ["--list", path], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode(errors="replace")[-200:])


def restore_to(backup_id: str, target_db: str) -> dict:
    """Restore a full backup into a SEPARATE target database (never production
    silently). Returns basic verification counts."""
    s = get_settings()
    with session_scope() as sess:
        m = sess.get(BackupManifest, backup_id)
        if m is None or m.kind != "full":
            return {"ok": False, "reason": "no full backup"}
        loc = m.storage_location
    if loc.endswith(".enc"):
        return {"ok": False, "reason": "encrypted backup — decrypt before restore"}
    parts = _dsn_parts(s.sync_database_url)
    if target_db == parts["db"]:
        return {"ok": False, "reason": "refusing to restore over the source database"}

    psql = _pg_tool("psql")
    host = _dump_target_host(parts, psql)
    port = _dump_target_port(parts, psql)
    base = psql + ["-h", host, "-p", port, "-U", parts["user"], "-d", "postgres", "-v", "ON_ERROR_STOP=0", "-c"]
    subprocess.run(base + [f'DROP DATABASE IF EXISTS "{target_db}"'], env=_env_for(parts), timeout=120)
    subprocess.run(base + [f'CREATE DATABASE "{target_db}"'], env=_env_for(parts),
                   check=True, timeout=120)

    pgr = _pg_tool("pg_restore")
    restore = pgr + ["-h", host, "-p", port, "-U", parts["user"], "-d", target_db,
                     "--no-owner", "--no-privileges", "--clean", "--if-exists"]
    if pgr[:1] == ["docker"]:
        with open(loc, "rb") as f:
            proc = subprocess.run(restore, stdin=f, stderr=subprocess.PIPE, timeout=600,
                                  env=_env_for(parts))
    else:
        proc = subprocess.run(restore + [loc], stderr=subprocess.PIPE, timeout=600,
                              env=_env_for(parts))
    # pg_restore returns non-zero on benign warnings with --clean; check content instead

    from sqlalchemy import create_engine, text

    tgt_url = f"postgresql+psycopg://{parts['user']}:{parts['password']}@{parts['host']}:{parts['port']}/{target_db}"
    eng = create_engine(tgt_url)
    counts = {}
    with eng.connect() as c:
        counts["migration_revision"] = c.execute(text("SELECT version_num FROM alembic_version")).scalar()
        for t in ("campaigns", "assets", "publications", "analytics_snapshots",
                  "learning_memories", "autopilot_config_versions"):
            try:
                counts[t] = c.execute(text(f"SELECT count(*) FROM {t}")).scalar()
            except Exception:  # noqa: BLE001
                counts[t] = "MISSING"
    eng.dispose()
    ok = counts["migration_revision"] not in (None, "") and counts.get("campaigns") != "MISSING"
    if ok:
        _set_status(backup_id, "RESTORE_TESTED", restore_tested=True)
    return {"ok": ok, "target_db": target_db, "counts": counts,
            "stderr_tail": proc.stderr.decode(errors="replace")[-300:] if proc.stderr else ""}


def _encrypt_file(src: str, dst: str, key: str) -> None:
    from cryptography.fernet import Fernet

    f = Fernet(key if isinstance(key, bytes) else key.encode())
    with open(src, "rb") as r, open(dst, "wb") as w:
        w.write(f.encrypt(r.read()))


def _fail_manifest(kind: str, path: str, err: str) -> None:
    with session_scope() as sess:
        sess.add(BackupManifest(kind=kind, method="pg_dump", status="FAILED",
                                storage_location=path, meta={"error": err[-400:]}))


def _set_status(backup_id: str, status: str, *, verified: bool = False,
                restore_tested: bool = False) -> None:
    with session_scope() as sess:
        m = sess.get(BackupManifest, backup_id)
        if m is None:
            return
        m.status = status
        now = datetime.now(timezone.utc)
        if verified:
            m.verified_at = now
        if restore_tested:
            m.restore_tested_at = now


def _apply_retention() -> None:
    s = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(days=s.backup_retention_days)
    with session_scope() as sess:
        for m in sess.query(BackupManifest).filter(BackupManifest.created_at < cutoff):
            if m.storage_location and os.path.isfile(m.storage_location):
                try:
                    os.remove(m.storage_location)
                except OSError:
                    pass
            sess.delete(m)


def backup_status() -> dict:
    with session_scope() as sess:
        last = (sess.query(BackupManifest).filter_by(kind="full")
                .order_by(BackupManifest.created_at.desc()).first())
        last_restore = (sess.query(BackupManifest)
                        .filter(BackupManifest.restore_tested_at.isnot(None))
                        .order_by(BackupManifest.restore_tested_at.desc()).first())
        return {
            "last_full_backup": None if last is None else {
                "id": last.id, "created_at": last.created_at.isoformat(),
                "size_bytes": last.size_bytes, "status": last.status,
                "checksum_sha256": last.checksum_sha256, "encryption": last.encryption},
            "last_restore_test": None if last_restore is None else
            last_restore.restore_tested_at.isoformat(),
            "retention_days": get_settings().backup_retention_days,
        }
