"""Resource limits for user-uploaded tabular imports."""

MAX_IMPORT_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_IMPORT_ROWS = 10_000
UPLOAD_READ_CHUNK_BYTES = 64 * 1024
# An .xlsx is a zip: a small upload can expand to gigabytes (a "zip bomb"). Cap what it may expand to.
MAX_XLSX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024  # 100 MB
MAX_XLSX_ENTRIES = 2_000
