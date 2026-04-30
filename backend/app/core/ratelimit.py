"""Rate-limiter singleton.

Lives in its own module so any router can decorate its handlers with
``@limiter.limit('X/minute')`` without circle-importing main.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

# Default 300 req/min per IP for the broad surface; sensitive endpoints
# tighten this with their own decorators.
limiter = Limiter(key_func=get_remote_address, default_limits=["300/minute"])
