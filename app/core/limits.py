from slowapi import Limiter
from slowapi.util import get_remote_address

# Global limiter — per-endpoint limits applied via @limiter.limit decorators.
# default_limits is intentionally empty so non-decorated endpoints stay
# unthrottled (health, settings, list endpoints, exports, etc.).
limiter = Limiter(key_func=get_remote_address, default_limits=[])
