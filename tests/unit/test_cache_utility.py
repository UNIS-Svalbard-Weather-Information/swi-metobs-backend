"""
Unit tests for the cache utility module.
"""

import os
import pytest
from unittest.mock import patch, MagicMock
import app.utils.cache as cache_module
from app.utils.cache import (
    get_cache_backend,
    generate_cache_key,
    generate_cache_key_from_args,
    MemoryCache,
    cache_response,
)
from fastapi import Request, Response


@pytest.fixture(autouse=True)
def _reset_cache_backend_singleton():
    """Reset cache-related global state before/after each test in this module.

    get_cache_backend() caches successfully-resolved backends (Redis or
    Memory) in a module-level global for reuse across requests. Without this
    reset, whichever backend a given test happens to resolve would leak into
    every later test in this module regardless of that test's own env vars.

    Several tests in this file also pop SWI_METSERVICES_CACHE_DISABLED to
    exercise the enabled path without restoring it - which otherwise leaks a
    "caching enabled" state into every test that runs afterwards in the same
    pytest session (including other test files), since the session-scoped
    fixture in conftest.py only sets it once, at session start.
    """
    original_backend = cache_module._cache_backend_instance
    original_cache_disabled = os.environ.get("SWI_METSERVICES_CACHE_DISABLED")
    cache_module._cache_backend_instance = None
    yield
    cache_module._cache_backend_instance = original_backend
    if original_cache_disabled is None:
        os.environ.pop("SWI_METSERVICES_CACHE_DISABLED", None)
    else:
        os.environ["SWI_METSERVICES_CACHE_DISABLED"] = original_cache_disabled


class TestMemoryCache:
    """Test the MemoryCache implementation."""

    def test_memory_cache_set_and_get(self):
        """Test setting and getting values in memory cache."""
        cache = MemoryCache()
        test_key = "test_key"
        test_value = "test_value"

        # Set value with TTL
        cache.setex(test_key, 60, test_value)

        # Get value should return it
        result = cache.get(test_key)
        assert result == test_value

    def test_memory_cache_expiration(self):
        """Test that cached values expire."""
        cache = MemoryCache()
        test_key = "test_key"
        test_value = "test_value"

        # Set value with very short TTL (1 second)
        cache.setex(test_key, 1, test_value)

        # Should be available immediately
        result = cache.get(test_key)
        assert result == test_value

        # Wait for expiration
        import time

        time.sleep(2)

        # Should be None after expiration
        result = cache.get(test_key)
        assert result is None

    def test_memory_cache_delete(self):
        """Test deleting values from memory cache."""
        cache = MemoryCache()
        test_key = "test_key"
        test_value = "test_value"

        # Set value
        cache.setex(test_key, 60, test_value)

        # Should be available
        result = cache.get(test_key)
        assert result == test_value

        # Delete value
        cache.delete(test_key)

        # Should be None after deletion
        result = cache.get(test_key)
        assert result is None


class TestCacheBackendSelection:
    """Test cache backend selection logic."""

    def test_cache_disabled_in_test_mode(self):
        """Test that cache is disabled when SWI_METSERVICES_CACHE_DISABLED is true."""
        # Set environment variable to disable cache
        os.environ["SWI_METSERVICES_CACHE_DISABLED"] = "true"

        # Should return None (cache disabled)
        backend = get_cache_backend()
        assert backend is None

        # Clean up
        del os.environ["SWI_METSERVICES_CACHE_DISABLED"]

    def test_memory_cache_fallback(self):
        """Test that memory cache is used when Redis is not configured."""
        # Ensure Redis environment variables are not set
        os.environ.pop("SWI_METSERVICES_REDIS_HOST", None)
        os.environ.pop("SWI_METSERVICES_REDIS_PORT", None)
        os.environ.pop("SWI_METSERVICES_CACHE_DISABLED", None)

        # Should return MemoryCache instance
        backend = get_cache_backend()
        assert isinstance(backend, MemoryCache)

    @patch("app.utils.cache.redis.Redis")
    def test_redis_connection_failure_fallback(self, mock_redis):
        """Test that memory cache is used when Redis connection fails."""
        # Set Redis environment variables
        os.environ["SWI_METSERVICES_REDIS_HOST"] = "localhost"
        os.environ["SWI_METSERVICES_REDIS_PORT"] = "6379"
        os.environ.pop("SWI_METSERVICES_CACHE_DISABLED", None)

        # Mock Redis to fail ping
        mock_redis_instance = MagicMock()
        mock_redis_instance.ping.return_value = False
        mock_redis.return_value = mock_redis_instance

        # Should fall back to MemoryCache
        backend = get_cache_backend()
        assert isinstance(backend, MemoryCache)

        # Clean up
        del os.environ["SWI_METSERVICES_REDIS_HOST"]
        del os.environ["SWI_METSERVICES_REDIS_PORT"]

    @patch("app.utils.cache.redis.Redis")
    def test_redis_successful_connection(self, mock_redis):
        """Test that Redis is used when connection is successful."""
        # Set Redis environment variables
        os.environ["SWI_METSERVICES_REDIS_HOST"] = "localhost"
        os.environ["SWI_METSERVICES_REDIS_PORT"] = "6379"
        os.environ.pop("SWI_METSERVICES_CACHE_DISABLED", None)

        # Mock Redis to succeed ping
        mock_redis_instance = MagicMock()
        mock_redis_instance.ping.return_value = True
        mock_redis.return_value = mock_redis_instance

        # Should return Redis instance
        backend = get_cache_backend()
        assert backend == mock_redis_instance

        # Clean up
        del os.environ["SWI_METSERVICES_REDIS_HOST"]
        del os.environ["SWI_METSERVICES_REDIS_PORT"]

    @patch("app.utils.cache.redis.Redis")
    def test_redis_client_reused_across_calls(self, mock_redis):
        """Test that a successfully connected Redis client is reused, not recreated/re-pinged."""
        os.environ["SWI_METSERVICES_REDIS_HOST"] = "localhost"
        os.environ["SWI_METSERVICES_REDIS_PORT"] = "6379"
        os.environ.pop("SWI_METSERVICES_CACHE_DISABLED", None)

        mock_redis_instance = MagicMock()
        mock_redis_instance.ping.return_value = True
        mock_redis.return_value = mock_redis_instance

        backend1 = get_cache_backend()
        backend2 = get_cache_backend()

        assert backend1 is backend2
        assert backend1 == mock_redis_instance
        mock_redis.assert_called_once()

        # Clean up
        del os.environ["SWI_METSERVICES_REDIS_HOST"]
        del os.environ["SWI_METSERVICES_REDIS_PORT"]


class TestCacheKeyGeneration:
    """Test cache key generation."""

    def test_generate_cache_key(self):
        """Test that cache keys are generated consistently."""
        # Create a mock request
        mock_request = MagicMock(spec=Request)
        mock_request.url = "http://example.com/api/test?param=value"

        # Generate key
        key1 = generate_cache_key(mock_request)
        key2 = generate_cache_key(mock_request)

        # Should be consistent
        assert key1 == key2
        assert key1.startswith("cache:")

        # Different URLs should give different keys
        mock_request.url = "http://example.com/api/test?param=different"
        key3 = generate_cache_key(mock_request)
        assert key3 != key1

    def test_generate_cache_key_from_args_ignores_request_and_response(self):
        """A different injected Request/Response object shouldn't change the key.

        FastAPI calls endpoints with keyword arguments only, so any endpoint
        declaring `request: Request` or `response: Response` params gets a
        fresh object per call. Neither has a stable repr, so both must be
        excluded from the key regardless of the parameter's name.
        """

        def sample_endpoint(model, request=None, response=None):
            pass

        key1 = generate_cache_key_from_args(
            sample_endpoint,
            (),
            {
                "model": "aa",
                "request": MagicMock(spec=Request),
                "response": MagicMock(spec=Response),
            },
        )
        key2 = generate_cache_key_from_args(
            sample_endpoint,
            (),
            {
                "model": "aa",
                "request": MagicMock(spec=Request),
                "response": MagicMock(spec=Response),
            },
        )

        assert key1 == key2


class TestCacheResponseDecorator:
    """Test the cache_response decorator."""

    @pytest.mark.asyncio
    async def test_cache_disabled_in_decorator(self):
        """Test that decorator bypasses cache when disabled."""
        # Set environment variable to disable cache
        os.environ["SWI_METSERVICES_CACHE_DISABLED"] = "true"

        # Create a simple async function to decorate
        @cache_response(ttl=60)
        async def test_function():
            return {"result": "test"}

        # Call the decorated function
        response = await test_function()

        # Should return the function result (not cached)
        assert response == {"result": "test"}

        # Clean up
        del os.environ["SWI_METSERVICES_CACHE_DISABLED"]

    @pytest.mark.asyncio
    @patch("app.utils.cache.get_cache_backend")
    async def test_cache_hit(self, mock_get_backend):
        """Test that decorator returns cached response on cache hit."""
        # Mock cache backend
        mock_cache = MagicMock()
        mock_cache.get.return_value = '{"cached": "response"}'
        mock_get_backend.return_value = mock_cache

        # Create a simple async function to decorate
        @cache_response(ttl=60)
        async def test_function():
            return {"result": "test"}

        # Call the decorated function
        response = await test_function()

        # Should return cached response
        assert response == {"cached": "response"}

        # Should have called cache.get
        mock_cache.get.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.utils.cache.get_cache_backend")
    async def test_cache_miss_and_store(self, mock_get_backend):
        """Test that decorator executes function and stores result on cache miss."""
        # Mock cache backend
        mock_cache = MagicMock()
        mock_cache.get.return_value = None  # Cache miss
        mock_get_backend.return_value = mock_cache

        # Create a simple async function to decorate
        @cache_response(ttl=60)
        async def test_function():
            return {"result": "test"}

        # Call the decorated function
        response = await test_function()

        # Should return function result
        assert response == {"result": "test"}

        # Should have called cache.get and cache.setex
        mock_cache.get.assert_called_once()
        mock_cache.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_response_binary_response_round_trip(self):
        """A Response with binary (non-UTF8) content should survive a cache round-trip.

        Regression test: previously the cached bytes were stored raw and a
        subsequent json.loads() on read raised UnicodeDecodeError.
        """
        os.environ.pop("SWI_METSERVICES_REDIS_HOST", None)
        os.environ.pop("SWI_METSERVICES_REDIS_PORT", None)
        original_cache_disabled = os.environ.pop("SWI_METSERVICES_CACHE_DISABLED", None)

        try:
            binary_body = bytes([0x00, 0xFF, 0x80, 0x01, 0xFE])  # not valid UTF-8

            @cache_response(ttl=60)
            async def netcdf_like_endpoint():
                return Response(content=binary_body, media_type="application/x-netcdf")

            first = await netcdf_like_endpoint()
            assert first.body == binary_body

            second = await netcdf_like_endpoint()  # cache hit; must not raise
            assert isinstance(second, Response)
            assert second.body == binary_body
            assert second.media_type == "application/x-netcdf"
        finally:
            if original_cache_disabled is not None:
                os.environ["SWI_METSERVICES_CACHE_DISABLED"] = original_cache_disabled

    @pytest.mark.asyncio
    async def test_cache_response_replays_headers_on_hit(self):
        """Headers set on a `response` side-channel param during a miss are
        replayed on a later cache hit, since a hit skips the function body
        (and therefore the header mutation) entirely.
        """
        os.environ.pop("SWI_METSERVICES_REDIS_HOST", None)
        os.environ.pop("SWI_METSERVICES_REDIS_PORT", None)
        original_cache_disabled = os.environ.pop("SWI_METSERVICES_CACHE_DISABLED", None)

        try:

            @cache_response(ttl=60)
            async def endpoint_with_headers(response: Response = None):
                response.headers["Cache-Control"] = "public, max-age=600"
                return {"result": "ok"}

            response1 = Response()
            result1 = await endpoint_with_headers(response=response1)
            assert result1 == {"result": "ok"}
            assert response1.headers["Cache-Control"] == "public, max-age=600"

            # A fresh Response object, as FastAPI would inject per-request.
            response2 = Response()
            result2 = await endpoint_with_headers(response=response2)
            assert result2 == {"result": "ok"}
            assert response2.headers["Cache-Control"] == "public, max-age=600"
        finally:
            if original_cache_disabled is not None:
                os.environ["SWI_METSERVICES_CACHE_DISABLED"] = original_cache_disabled


class TestEnvironmentVariableHandling:
    """Test environment variable handling."""

    def test_cache_disabled_case_insensitive(self):
        """Test that cache disabled is case insensitive."""
        # Test various case combinations
        for value in ["true", "True", "TRUE", "TrUe"]:
            os.environ["SWI_METSERVICES_CACHE_DISABLED"] = value
            backend = get_cache_backend()
            assert backend is None, f"Cache should be disabled for value: {value}"
            del os.environ["SWI_METSERVICES_CACHE_DISABLED"]

    def test_cache_enabled_when_not_true(self):
        """Test that cache is enabled when value is not 'true'."""
        # Test various non-true values
        for value in ["false", "False", "FALSE", "0", "no", ""]:
            os.environ["SWI_METSERVICES_CACHE_DISABLED"] = value
            backend = get_cache_backend()
            assert backend is not None, f"Cache should be enabled for value: {value}"
            del os.environ["SWI_METSERVICES_CACHE_DISABLED"]
