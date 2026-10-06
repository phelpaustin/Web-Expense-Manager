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
