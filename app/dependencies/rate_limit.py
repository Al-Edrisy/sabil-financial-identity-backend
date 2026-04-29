import time
import logging
from fastapi import HTTPException, Request, status
from typing import Dict, Tuple, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Redis Backend Setup ───────────────────────────────────────────────────────
_redis_client = None
if settings.REDIS_URL:
    try:
        import redis
        _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        logger.info("Rate limiter: connected to Redis")
    except ImportError:
        logger.warning("Redis package not installed. Falling back to in-memory rate limiting.")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}. Falling back to in-memory.")

# ── In-memory Fallback ────────────────────────────────────────────────────────
# {ip: (timestamp, count)}
_in_memory_storage: Dict[str, Tuple[float, int]] = {}

def rate_limiter(requests_per_minute: int = 60):
    async def dependency(request: Request):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        key = f"rate_limit:{client_ip}"

        # ── Scenario A: Redis ─────────────────────────────────────────────────
        if _redis_client:
            try:
                # Use a pipeline for atomic increment + expire
                pipe = _redis_client.pipeline()
                pipe.incr(key)
                pipe.expire(key, 60, nx=True)
                count, _ = pipe.execute()
                
                if count > requests_per_minute:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Too many requests. Please try again later.",
                    )
                return
            except Exception as e:
                if isinstance(e, HTTPException): raise e
                logger.error(f"Redis rate limit error: {e}")
                # Fallback to in-memory on Redis failure

        # ── Scenario B: In-memory ──────────────────────────────────────────────
        global _in_memory_storage
        if client_ip not in _in_memory_storage:
            _in_memory_storage[client_ip] = (now, 1)
            return
        
        last_request_time, count = _in_memory_storage[client_ip]
        if now - last_request_time > 60:
            _in_memory_storage[client_ip] = (now, 1)
            return
        
        if count >= requests_per_minute:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
            )
        
        _in_memory_storage[client_ip] = (last_request_time, count + 1)
    
    return dependency
