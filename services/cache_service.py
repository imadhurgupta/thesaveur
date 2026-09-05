import os
import redis

# Redis Configuration & Initialization (Optional High-Speed Cache)
redis_client = None
redis_url = os.environ.get('REDIS_URL', '').strip()

if redis_url:
    try:
        redis_client = redis.Redis.from_url(redis_url, socket_timeout=3)
        redis_client.ping()
        print(f"[REDIS] Connected successfully to {redis_url}")
    except Exception as e:
        print(f"[REDIS WARNING] Failed to connect to {redis_url}: {e}. Caching is disabled.")
        redis_client = None


def invalidate_cache(*keys):
    """Invalidate one or more keys from the Redis cache."""
    if redis_client:
        try:
            for key in keys:
                redis_client.delete(key)
                print(f"[REDIS] Cache invalidated for key: {key}")
        except Exception as e:
            print(f"[REDIS] Cache invalidation error: {e}")
