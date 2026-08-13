from slowapi import Limiter
from slowapi.util import get_remote_address

# Rate limiting keyed by client IP. Applied per-endpoint via @limiter.limit(...).
limiter = Limiter(key_func=get_remote_address)
