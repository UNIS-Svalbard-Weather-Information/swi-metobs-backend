"""
Cache utility module with Redis/memory fallback and test mode support.
"""

import os
import json
import base64
import hashlib
from typing import Any, Dict, Optional, Union
from functools import wraps
from datetime import datetime, timedelta
from pydantic import BaseModel
import redis
from fastapi import Request, Response
from loguru import logger


# Cache backend instance (module-level cache)
_cache_backend_instance = None


class MemoryCache:
    """Simple in-memory cache implementation."""

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}

    def get(self, key: str) -> Optional[str]:
        """Get cached value."""
        cached = self._cache.get(key)
        if cached:
            logger.debug(
                f"MemoryCache.get({key}): found cached item, expires_at={cached.get('expires_at')}, now={datetime.now()}"
            )
            if cached.get("expires_at") > datetime.now():
                logger.debug(f"MemoryCache.get({key}): returning cached value")
                return cached.get("value")
            else:
                logger.debug(f"MemoryCache.get({key}): cached item expired")
        else:
            logger.debug(f"MemoryCache.get({key}): no cached item found")
        return None

    def setex(self, key: str, ttl: int, value: str):
        """Set cached value with expiration."""
        expires_at = datetime.now() + timedelta(seconds=ttl)
        self._cache[key] = {"value": value, "expires_at": expires_at}
        logger.debug(f"MemoryCache.setex({key}): stored value, expires_at={expires_at}")

    def delete(self, key: str) -> None:
        """Delete cached value."""
        self._cache.pop(key, None)


def get_cache_backend() -> Optional[Union[redis.Redis, MemoryCache]]:
    """
    Initialize cache backend based on environment variables.

    Returns:
        redis.Redis if Redis is configured, MemoryCache for fallback, None if disabled.
    """
    global _cache_backend_instance

    # Return cached instance if available and cache is not disabled
    current_cache_disabled = (
        os.getenv("SWI_METSERVICES_CACHE_DISABLED", "false").lower() == "true"
    )

    if _cache_backend_instance is not None and not current_cache_disabled:
        return _cache_backend_instance

    # Check if cache is disabled (test mode)
    if os.getenv("SWI_METSERVICES_CACHE_DISABLED", "false").lower() == "true":
        logger.info("Cache disabled (test mode)")
        _cache_backend_instance = None
        return None

    # Try to configure Redis
    redis_host = os.getenv("SWI_METSERVICES_REDIS_HOST")
    redis_port = os.getenv("SWI_METSERVICES_REDIS_PORT")
    redis_pwd = os.getenv("SWI_METSERVICES_REDIS_PWD")

    if redis_host and redis_port:
        try:
            port = int(redis_port)
            redis_client = redis.Redis(
                host=redis_host,
                port=port,
                password=redis_pwd,
                decode_responses=True,
                socket_timeout=5,
            )
            # Test connection
            if redis_client.ping():
                logger.info(f"Using Redis cache at {redis_host}:{redis_port}")
                _cache_backend_instance = redis_client
                return _cache_backend_instance
            else:
                logger.warning("Redis connection failed, falling back to memory cache")
        except Exception as e:
            logger.warning(
                f"Redis initialization failed: {e}, falling back to memory cache"
            )

    # Fallback to memory cache
    logger.info("Using in-memory cache fallback")
    _cache_backend_instance = MemoryCache()
    return _cache_backend_instance


def generate_cache_key(request: Request) -> str:
    """
    Generate a unique cache key based on request URL and query parameters.

    Args:
        request: FastAPI Request object

    Returns:
        str: Cache key
    """
    # Create a unique key based on URL and query parameters
    url_str = str(request.url)
    cache_key = hashlib.md5(url_str.encode()).hexdigest()
    return f"cache:{cache_key}"


def generate_cache_key_from_args(func, args, kwargs) -> str:
    """
    Generate a unique cache key based on function name and arguments.

    Args:
        func: The function being cached
        args: Positional arguments
        kwargs: Keyword arguments

    Returns:
        str: Cache key
    """
    # Create a unique key based on function name and arguments.
    # Positional order is preserved (it's semantically meaningful); kwargs are
    # sorted by key for determinism.
    args_part = [str(arg) for arg in args]

    kwargs_part = []

    # Add keyword arguments (sorted for consistency). FastAPI-injected Request/
    # Response objects have no stable repr (it embeds the object's memory
    # address), so they're excluded regardless of the parameter's name.
    for key, value in sorted(kwargs.items()):
        if isinstance(value, (Request, Response)):
            continue
        kwargs_part.append(f"{key}={value}")

    return f"cache:{func.__name__}:{':'.join(args_part)}:{':'.join(kwargs_part)}"


def cache_response(ttl: int = 60):
    """
    Decorator to cache API responses.

    Args:
        ttl: Time-to-live in seconds for cached responses

    Returns:
        Decorator function
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get cache backend
            cache_backend = get_cache_backend()

            # If cache is disabled, execute function normally
            if cache_backend is None:
                logger.debug("Cache disabled, executing function normally")
                return await func(*args, **kwargs)

            # FastAPI-injected Response side-channel (e.g. `response: Response`
            # params used to set headers), if the endpoint declares one.
            response_obj = kwargs.get("response")
            if not isinstance(response_obj, Response):
                response_obj = None

            # Generate cache key from function arguments
            cache_key = generate_cache_key_from_args(func, args, kwargs)
            logger.debug(f"Cache key: {cache_key}")

            # Try to get cached response
            try:
                cached_data = cache_backend.get(cache_key)
            except Exception as e:
                logger.warning(f"Cache read failed for {cache_key}: {e}")
                cached_data = None

            if cached_data:
                logger.debug(f"Cache hit for {cache_key}")
                try:
                    cached_response = json.loads(cached_data)
                    if isinstance(cached_response, dict) and cached_response.get(
                        "__cached_binary_response__"
                    ):
                        return Response(
                            content=base64.b64decode(cached_response["body"]),
                            media_type=cached_response.get("media_type"),
                            status_code=cached_response.get("status_code", 200),
                            headers=cached_response.get("headers") or None,
                        )
                    if isinstance(cached_response, dict) and cached_response.get(
                        "__cached_with_headers__"
                    ):
                        if response_obj is not None:
                            for k, v in cached_response.get("headers", {}).items():
                                response_obj.headers[k] = v
                        return cached_response["data"]
                    return cached_response
                except (
                    json.JSONDecodeError,
                    UnicodeDecodeError,
                    KeyError,
                    TypeError,
                    ValueError,
                ):
                    logger.warning(f"Invalid cached data for {cache_key}")
                    cache_backend.delete(cache_key)

            # Execute the function if no cache hit
            logger.debug(f"Cache miss for {cache_key}, executing function")
            result = await func(*args, **kwargs)

            # logger.debug(f"Type of result: {type(result)} and content: {result}")

            # Cache successful results
            try:
                if isinstance(result, Response):
                    # Handle FastAPI Response objects (e.g. binary bodies like
                    # NetCDF) by base64-encoding the body so it round-trips
                    # through JSON/UTF-8 safely, and preserving media type,
                    # status code and headers so a cache hit can reconstruct
                    # an equivalent Response.
                    response_data = json.dumps(
                        {
                            "__cached_binary_response__": True,
                            "body": base64.b64encode(result.body or b"").decode(
                                "ascii"
                            ),
                            "media_type": result.media_type,
                            "status_code": result.status_code,
                            "headers": {
                                k: v
                                for k, v in result.headers.items()
                                if k.lower() not in ("content-length", "content-type")
                            },
                        }
                    )
                elif isinstance(result, BaseModel):
                    response_data = result.model_dump_json()
                    logger.debug(
                        f"Serializing Pydantic model for caching: \n\n\n{response_data}\n\n\n"
                    )
                elif hasattr(result, "dict"):
                    # Handle Pydantic models - use model_dump() with mode='json' for proper serialization
                    try:
                        # Try to use model_dump() first (Pydantic v2)
                        if hasattr(result, "model_dump"):
                            result_dict = result.model_dump(mode="json")
                        else:
                            result_dict = result.dict()
                        response_data = json.dumps(result_dict)
                    except (TypeError, ValueError) as e:
                        logger.warning(
                            f"Failed to serialize Pydantic model directly: {e}, falling back to string"
                        )
                        response_data = json.dumps(str(result))
                else:
                    # Handle other types - try to serialize, fall back to string if needed
                    try:
                        response_data = json.dumps(result)
                    except (TypeError, ValueError):
                        # Fall back to string representation if JSON serialization fails
                        response_data = json.dumps(str(result))

                # If the endpoint mutates a side-channel `response` object
                # (e.g. to set headers) rather than returning a Response
                # itself, snapshot those headers so a future cache hit can
                # replay them - a cache hit otherwise skips the function body
                # entirely and those mutations would never happen.
                if response_obj is not None and not isinstance(result, Response):
                    response_data = json.dumps(
                        {
                            "__cached_with_headers__": True,
                            "data": json.loads(response_data),
                            "headers": dict(response_obj.headers),
                        }
                    )

                # Store in cache
                cache_backend.setex(cache_key, ttl, response_data)
                logger.debug(f"Cached response for {cache_key} (TTL: {ttl}s)")
            except Exception as e:
                logger.error(f"Failed to cache response for {cache_key}: {e}")

            return result

        return wrapper

    return decorator
