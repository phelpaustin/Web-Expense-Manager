SUPPORTED_RECEIPT_TYPES = {
    "application/pdf": b"%PDF",
    "image/jpeg": b"\xff\xd8\xff",
    "image/png": b"\x89PNG\r\n\x1a\n",
}


def detect_receipt_content_type(data: bytes) -> str:
    """Return a trusted MIME type from file bytes or reject the file."""
    for content_type, signature in SUPPORTED_RECEIPT_TYPES.items():
        if data.startswith(signature):
            return content_type
    raise ValueError("Unsupported or invalid receipt file; use a PDF, JPEG, or PNG")