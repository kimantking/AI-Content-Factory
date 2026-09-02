from __future__ import annotations

import re
import uuid

from app.config import get_settings

# magic-byte signatures -> canonical mime
_MAGIC: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"RIFF", "image/webp"),           # + WEBP at offset 8 (checked below)
    (b"\x00\x00\x00\x18ftyp", "video/mp4"),
    (b"\x00\x00\x00\x20ftyp", "video/mp4"),
    (b"\x1aE\xdf\xa3", "video/webm"),
    (b"OggS", "audio/ogg"),
    (b"ID3", "audio/mpeg"),
    (b"%PDF-", "application/pdf"),
]
_ALLOWED = {"image/jpeg", "image/png", "image/gif", "image/webp",
            "video/mp4", "video/webm", "audio/ogg", "audio/mpeg", "audio/wav",
            "text/plain", "application/pdf"}

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class UploadRejected(ValueError):
    pass


def sniff_mime(data: bytes) -> str | None:
    head = data[:64]
    for sig, mime in _MAGIC:
        if head.startswith(sig):
            if mime == "image/webp" and data[8:12] != b"WEBP":
                continue
            return mime
    if head.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return "audio/wav"
    # utf-8 text?
    try:
        data[:512].decode("utf-8")
        return "text/plain"
    except UnicodeDecodeError:
        return None


def safe_filename(name: str, *, keep_ext: bool = True) -> str:
    """Never trust the client filename for a storage path."""
    ext = ""
    if keep_ext and "." in name:
        raw_ext = name.rsplit(".", 1)[1].lower()
        if re.fullmatch(r"[a-z0-9]{1,8}", raw_ext):
            ext = "." + raw_ext
    return f"{uuid.uuid4().hex}{ext}"


def has_path_traversal(name: str) -> bool:
    return (".." in name) or name.startswith(("/", "\\")) or ":" in name or "\x00" in name


def validate_upload(data: bytes, *, declared_mime: str | None = None,
                    max_size: int | None = None, allowed: set[str] | None = None) -> dict:
    s = get_settings()
    max_size = max_size or s.max_upload_bytes
    allowed = allowed or _ALLOWED
    if not data:
        raise UploadRejected("empty upload")
    if len(data) > max_size:
        raise UploadRejected(f"upload too large: {len(data)} > {max_size}")
    sniffed = sniff_mime(data)
    if sniffed is None or sniffed not in allowed:
        raise UploadRejected(f"disallowed content (sniffed={sniffed}, declared={declared_mime})")
    if declared_mime and declared_mime.split(";")[0].strip() != sniffed:
        # declared type must not contradict the bytes
        if not (declared_mime.startswith("image/") and sniffed.startswith("image/")):
            raise UploadRejected(f"declared mime {declared_mime} != sniffed {sniffed}")
    return {"mime": sniffed, "size": len(data), "stored_name": safe_filename("upload." + sniffed.split("/")[-1])}
