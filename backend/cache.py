from diskcache import Cache
import hashlib

# Simple singleton cache (stored in ./cache directory)
cache = Cache('./cache')

def make_key(prompt: str) -> str:
    """Create a reproducible cache key from the prompt."""
    h = hashlib.sha256()
    h.update(prompt.encode('utf-8'))
    return h.hexdigest()

def get_cached_response(prompt: str) -> str | None:
    key = make_key(prompt)
    return cache.get(key)

def set_cached_response(prompt: str, response: str) -> None:
    key = make_key(prompt)
    # Store for 24 hours (86400 s)
    cache.set(key, response, expire=86400)
