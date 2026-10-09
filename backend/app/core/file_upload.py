import os
import re
import unicodedata
from urllib.parse import quote

from fastapi import HTTPException, UploadFile

from app.core.import_limits import UPLOAD_READ_CHUNK_BYTES


async def read_upload_limited(file: UploadFile, max_bytes: int) -> bytes:
    """Read an upload in bounded chunks, rejecting it as soon as it exceeds max_bytes."""
    chunks: list[bytes] = []
    total = 0

    while True:
        # Read at most one byte over the remaining allowance so an oversized
        # upload is detected without buffering an unbounded request body.
        chunk_size = min(UPLOAD_READ_CHUNK_BYTES, max_bytes - total + 1)
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail="File too large (max 10 MB)")
        chunks.append(chunk)

    return b"".join(chunks)


_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def safe_filename(name: str | None, default: str = "file", max_length: int = 150) -> str:
    """A client-supplied filename made safe to store and show.

    Drops any directory part and control characters and caps the length while
    keeping the extension. Never returns an empty string.
    """
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    base = _CONTROL_CHARS.sub("", base).strip().strip(".")
    if not base:
        return default
    if len(base) > max_length:
        stem, ext = os.path.splitext(base)
        base = stem[: max(1, max_length - len(ext))] + ext
    return base


def content_disposition(filename: str, disposition: str = "inline") -> str:
    """Content-Disposition header value that is valid for any filename.

    HTTP header values must be Latin-1, so a raw non-Latin filename (Japanese,
    Cyrillic, Polish, ...) used to crash the response. This sends an ASCII
    fallback plus the exact name as an RFC 5987/6266 ``filename*`` parameter,
    and escapes anything that could break out of the quoted string.
    """
    stem, ext = os.path.splitext(filename)
    ascii_stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode()
    ascii_ext = unicodedata.normalize("NFKD", ext).encode("ascii", "ignore").decode()
    fallback = re.sub(r'[^A-Za-z0-9._ -]', "_", (ascii_stem.strip() or "file") + ascii_ext)
    return f"{disposition}; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"
