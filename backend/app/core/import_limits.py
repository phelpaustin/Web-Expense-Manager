"""Resource limits for user-uploaded tabular imports."""

MAX_IMPORT_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_IMPORT_ROWS = 10_000
UPLOAD_READ_CHUNK_BYTES = 64 * 1024
