import os

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    # Memory storage only counts requests in this process.
    storage_uri=os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
    headers_enabled=True,
    # Count recent requests instead of resetting at fixed times.
    strategy="moving-window",
)
