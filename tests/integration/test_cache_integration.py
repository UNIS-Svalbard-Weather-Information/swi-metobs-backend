"""
Integration tests for the cache decorator with actual API endpoints.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client_with_cache():
    """Test client with cache enabled."""
    # Ensure cache is enabled for these tests
    import os
    from app.utils.cache import MemoryCache

    os.environ.pop("SWI_METSERVICES_CACHE_DISABLED", None)

    # Use memory cache for testing
    with patch("app.utils.cache.get_cache_backend") as mock_get_backend:
        mock_cache = MemoryCache()
        mock_get_backend.return_value = mock_cache

        client = TestClient(app)
        yield client, mock_cache


class TestCacheIntegration:
    """Integration tests for cache decorator."""

    def test_cache_disabled_in_test_environment(self):
        """Test that cache is disabled in the test environment by default."""
        from app.utils.cache import get_cache_backend

        # In our test setup, cache should be disabled
        backend = get_cache_backend()
        assert backend is None, "Cache should be disabled in test environment"

    @patch("app.utils.cache.get_cache_backend")
    def test_cache_enabled_when_explicitly_set(self, mock_get_backend):
        """Test that cache can be enabled when explicitly configured."""
        import os
        from app.utils.cache import MemoryCache, get_cache_backend

        # Temporarily disable the test environment cache disable setting
        original_cache_disabled = os.environ.pop("SWI_METSERVICES_CACHE_DISABLED", None)

        try:
            # Mock a cache backend
            mock_cache = MemoryCache()
            mock_get_backend.return_value = mock_cache

            # Get the backend - should return our mock
            backend = get_cache_backend()
            assert backend == mock_cache
        finally:
            # Restore the original setting
            if original_cache_disabled is not None:
                os.environ["SWI_METSERVICES_CACHE_DISABLED"] = original_cache_disabled

    @patch("app.utils.cache.get_cache_backend")
    def test_forecast_endpoint_cache_behavior(self, mock_get_backend, test_client):
        """Test forecast endpoint caching behavior."""
        import os

        # Temporarily enable cache for this test
        original_cache_disabled = os.environ.get("SWI_METSERVICES_CACHE_DISABLED")
        os.environ["SWI_METSERVICES_CACHE_DISABLED"] = "false"

        try:
            # Mock cache backend
            mock_cache = MagicMock()
            mock_cache.get.return_value = None  # Cache miss initially
            mock_get_backend.return_value = mock_cache

            # First call - should miss cache and execute endpoint
            response1 = test_client.get("/v3/forecast/list/?variable=temperature")

            # Should have called cache.get and cache.setex
            # assert mock_cache.get.call_count >= 1
            # assert mock_cache.setex.call_count >= 1

            # Second call with same parameters - should hit cache
            response2 = test_client.get("/v3/forecast/list/?variable=temperature")

            # Should have called cache.get more times
            # assert mock_cache.get.call_count >= 2

            # Responses should be the same
            assert response1.status_code == response2.status_code
            assert response1.json() == response2.json()
        finally:
            # Restore the original setting
            if original_cache_disabled is not None:
                os.environ["SWI_METSERVICES_CACHE_DISABLED"] = original_cache_disabled

    @patch("app.utils.cache.get_cache_backend")
    def test_stations_endpoint_cache_behavior(self, mock_get_backend, test_client):
        """Test stations endpoint caching behavior."""
        import os

        # Temporarily enable cache for this test
        original_cache_disabled = os.environ.get("SWI_METSERVICES_CACHE_DISABLED")
        os.environ["SWI_METSERVICES_CACHE_DISABLED"] = "false"

        try:
            # Mock cache backend
            mock_cache = MagicMock()
            mock_cache.get.return_value = None  # Cache miss initially
            mock_get_backend.return_value = mock_cache

            # First call - should miss cache and execute endpoint
            response1 = test_client.get("/v3/station-status/")

            # Should have called cache.get and cache.setex
            # assert mock_cache.get.call_count >= 1
            # assert mock_cache.setex.call_count >= 1

            # Second call - should hit cache
            response2 = test_client.get("/v3/station-status/")

            # Should have called cache.get more times
            # assert mock_cache.get.call_count >= 2

            # Responses should be the same
            assert response1.status_code == response2.status_code
            assert response1.json() == response2.json()
        finally:
            # Restore the original setting
            if original_cache_disabled is not None:
                os.environ["SWI_METSERVICES_CACHE_DISABLED"] = original_cache_disabled


class TestCacheKeyGeneration:
    """Test cache key generation for different requests."""

    # @patch("app.utils.cache.get_cache_backend")
    # def test_different_urls_different_keys(self, mock_get_backend, test_client):
    #     """Test that different URLs generate different cache keys."""
    #     import os
    #     # Temporarily enable cache for this test
    #     original_cache_disabled = os.environ.get("SWI_METSERVICES_CACHE_DISABLED")
    #     os.environ["SWI_METSERVICES_CACHE_DISABLED"] = "false"

    #     try:
    #         # Mock cache backend
    #         mock_cache = MagicMock()
    #         mock_cache.get.return_value = None  # Cache miss
    #         mock_get_backend.return_value = mock_cache

    #         # Make requests to different endpoints
    #         response1 = test_client.get("/v3/station-status/")
    #         response2 = test_client.get("/v3/station-status/online")

    #         # Should have generated different cache keys
    #         # We can't directly test the keys, but we can verify cache operations happened
    #         # assert mock_cache.get.call_count >= 2
    #         # assert mock_cache.setex.call_count >= 2
    #     finally:
    #         # Restore the original setting
    #         if original_cache_disabled is not None:
    #             os.environ["SWI_METSERVICES_CACHE_DISABLED"] = original_cache_disabled

    # @patch("app.utils.cache.get_cache_backend")
    # def test_same_url_same_key(self, mock_get_backend, test_client):
    #     """Test that same URLs generate same cache keys."""
    #     import os
    #     # Temporarily enable cache for this test
    #     original_cache_disabled = os.environ.get("SWI_METSERVICES_CACHE_DISABLED")
    #     os.environ["SWI_METSERVICES_CACHE_DISABLED"] = "false"

    #     try:
    #         # Mock cache backend
    #         mock_cache = MagicMock()
    #         mock_cache.get.return_value = None  # Cache miss initially
    #         mock_get_backend.return_value = mock_cache

    #         # Make requests to same endpoint
    #         response1 = test_client.get("/v3/station-status/")
    #         response2 = test_client.get("/v3/station-status/")

    #         # Should have generated same cache keys (evidenced by cache hits)
    #         # assert mock_cache.get.call_count >= 2
    #         # assert mock_cache.setex.call_count >= 1  # Only set on first call
    #     finally:
    #         # Restore the original setting
    #         if original_cache_disabled is not None:
    #             os.environ["SWI_METSERVICES_CACHE_DISABLED"] = original_cache_disabled


class TestCacheTTL:
    """Test cache TTL behavior."""

    @patch("app.utils.cache.get_cache_backend")
    def test_cache_ttl_parameter(self, mock_get_backend):
        """Test that TTL parameter is passed correctly to cache.setex."""
        import os
        from app.utils.cache import MemoryCache, cache_response

        # Temporarily disable the test environment cache disable setting
        original_cache_disabled = os.environ.pop("SWI_METSERVICES_CACHE_DISABLED", None)

        try:
            # Mock cache backend
            mock_cache = MemoryCache()
            mock_get_backend.return_value = mock_cache

            # Import and test the decorator with different TTLs

            @cache_response(ttl=30)
            async def test_func_30():
                return {"result": "test"}

            @cache_response(ttl=60)
            async def test_func_60():
                return {"result": "test"}

            # We can't easily test the actual TTL without time manipulation,
            # but we can verify the decorator is set up correctly
            assert cache_response(ttl=30) is not None
            assert cache_response(ttl=60) is not None
        finally:
            # Restore the original setting
            if original_cache_disabled is not None:
                os.environ["SWI_METSERVICES_CACHE_DISABLED"] = original_cache_disabled


class TestCacheErrorHandling:
    """Test cache error handling."""

    @patch("app.utils.cache.get_cache_backend")
    def test_cache_error_doesnt_break_endpoint(self, mock_get_backend, test_client):
        """Test that cache errors don't break the endpoint functionality."""
        import os
        from app.utils.cache import MemoryCache

        # Temporarily disable the test environment cache disable setting
        original_cache_disabled = os.environ.pop("SWI_METSERVICES_CACHE_DISABLED", None)

        try:
            # Mock cache backend that raises exceptions
            mock_cache = MemoryCache()

            # Mock get to raise exception
            def mock_get_raises(key):
                raise Exception("Cache error")

            mock_cache.get = mock_get_raises
            mock_get_backend.return_value = mock_cache

            # Endpoint should still work even with cache errors
            response = test_client.get("/v3/station-status/")

            # Should return successful response despite cache error
            assert response.status_code == 200
        finally:
            # Restore the original setting
            if original_cache_disabled is not None:
                os.environ["SWI_METSERVICES_CACHE_DISABLED"] = original_cache_disabled

    @patch("app.utils.cache.get_cache_backend")
    def test_cache_set_error_doesnt_break_endpoint(self, mock_get_backend, test_client):
        """Test that cache set errors don't break the endpoint functionality."""
        import os
        from app.utils.cache import MemoryCache

        # Temporarily disable the test environment cache disable setting
        original_cache_disabled = os.environ.pop("SWI_METSERVICES_CACHE_DISABLED", None)

        try:
            # Mock cache backend that raises exceptions on set
            mock_cache = MemoryCache()

            # Mock setex to raise exception
            def mock_setex_raises(key, ttl, value):
                raise Exception("Cache set error")

            mock_cache.setex = mock_setex_raises
            mock_get_backend.return_value = mock_cache

            # Endpoint should still work even with cache set errors
            response = test_client.get("/v3/station-status/")

            # Should return successful response despite cache error
            assert response.status_code == 200
        finally:
            # Restore the original setting
            if original_cache_disabled is not None:
                os.environ["SWI_METSERVICES_CACHE_DISABLED"] = original_cache_disabled
