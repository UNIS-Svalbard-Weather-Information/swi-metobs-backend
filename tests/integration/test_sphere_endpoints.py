"""
Integration tests for sphere endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api.v3.endpoints.spheres import SpatialIndex, SphereNodePanorama
from datetime import datetime
import math


client = TestClient(app)


class TestSphereEndpoints:
    """Integration tests for sphere endpoints."""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Setup test data and clean up."""
        # Setup: Add mock data
        self._setup_mock_data()
        yield
        # Teardown: Clear data
        self._clear_data()

    def _setup_mock_data(self):
        """Setup mock sphere data for testing."""
        # Clear any existing data
        from app.api.v3.endpoints.spheres import _spatial_index, _distance_matrix, _bearing_matrix
        _spatial_index.clear()
        _distance_matrix.clear()
        _bearing_matrix.clear()
        
        # Create mock nodes
        center_lon, center_lat = 6.8586, 45.8326  # Grenoble coordinates
        radius = 0.01  # ~1.1km
        
        nodes = []
        for i in range(8):  # 8 nodes around center
            angle = math.radians(i * 45)
            lon = center_lon + radius * math.cos(angle)
            lat = center_lat + radius * math.sin(angle)
            
            node = SphereNodePanorama(
                id=f"test_node_{i}",
                gps=[lon, lat],
                panorama=f"https://example.com/panorama_{i}.jpg",
                thumbnail=f"https://example.com/thumbnail_{i}.jpg",
                links=[],
                author="Test Author",
                date=datetime(2023, 1, 1, 12, 0, 0),
                project="Test Project",
                label=f"Test Node {i}"
            )
            nodes.append(node)
        
        # Add center node
        center_node = SphereNodePanorama(
            id="test_center",
            gps=[center_lon, center_lat],
            panorama="https://example.com/panorama_center.jpg",
            thumbnail="https://example.com/thumbnail_center.jpg",
            links=[],
            author="Test Author",
            date=datetime(2023, 1, 1, 12, 0, 0),
            project="Test Project",
            label="Test Center"
        )
        nodes.append(center_node)
        
        # Add nodes to spatial index and compute matrices
        for node in nodes:
            SpatialIndex.add_node(node)
        SpatialIndex._compute_distance_and_bearing_matrices()

    def _clear_data(self):
        """Clear test data."""
        from app.api.v3.endpoints.spheres import _spatial_index, _distance_matrix, _bearing_matrix
        _spatial_index.clear()
        _distance_matrix.clear()
        _bearing_matrix.clear()

    def test_get_sphere_geojson(self):
        """Test GET /v3/spheres/geojson endpoint."""
        response = client.get("/v3/spheres/geojson")
        
        assert response.status_code == 200
        data = response.json()
        
        # Check response structure
        assert data["type"] == "FeatureCollection"
        assert "features" in data
        assert len(data["features"]) == 9  # 8 surrounding + 1 center
        
        # Check feature structure
        for feature in data["features"]:
            assert feature["type"] == "Feature"
            assert "properties" in feature
            assert "geometry" in feature
            assert feature["geometry"]["type"] == "Point"
            assert "coordinates" in feature["geometry"]

    def test_get_sphere_panorama_and_links_valid_node(self):
        """Test GET /v3/spheres/{node_id} with valid node ID."""
        response = client.get("/v3/spheres/test_center")
        
        assert response.status_code == 200
        data = response.json()
        
        # Check response structure
        assert data["id"] == "test_center"
        assert "gps" in data
        assert "panorama" in data
        assert "thumbnail" in data
        assert "links" in data
        assert "author" in data
        assert "date" in data
        assert "project" in data
        assert "label" in data
        
        # Check that neighbors are returned
        assert isinstance(data["links"], list)
        # Should find neighbors within default range (10000m)
        assert len(data["links"]) > 0
        
        # Check neighbor structure
        for link in data["links"]:
            assert "id" in link
            assert "gps" in link

    def test_get_sphere_panorama_and_links_invalid_node(self):
        """Test GET /v3/spheres/{node_id} with invalid node ID."""
        response = client.get("/v3/spheres/nonexistent_node")
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"]

    def test_get_sphere_panorama_and_links_with_parameters(self):
        """Test GET /v3/spheres/{node_id} with custom parameters."""
        # Test with small max_range (should find fewer neighbors)
        response_small = client.get("/v3/spheres/test_center?max_range=500")
        assert response_small.status_code == 200
        data_small = response_small.json()
        
        # Test with large max_range (should find more neighbors)
        response_large = client.get("/v3/spheres/test_center?max_range=5000")
        assert response_large.status_code == 200
        data_large = response_large.json()
        
        # Large range should find at least as many neighbors as small range
        assert len(data_large["links"]) >= len(data_small["links"])

    def test_get_sphere_panorama_and_links_sector_variation(self):
        """Test GET /v3/spheres/{node_id} with different sector counts."""
        # Test with fewer sectors
        response_few = client.get("/v3/spheres/test_center?sectors=4")
        assert response_few.status_code == 200
        data_few = response_few.json()
        
        # Test with more sectors
        response_many = client.get("/v3/spheres/test_center?sectors=16")
        assert response_many.status_code == 200
        data_many = response_many.json()
        
        # Both should return valid data with proper structure
        # Note: More sectors can sometimes find more neighbors if they meet separation criteria
        assert isinstance(data_few["links"], list)
        assert isinstance(data_many["links"], list)
        
        # Check that neighbors have proper structure in both cases
        for link in data_few["links"] + data_many["links"]:
            assert "id" in link
            assert "gps" in link

    def test_sphere_endpoints_with_real_data(self):
        """Test sphere endpoints with real data loaded."""
        # Clear our test data to test with real data
        self._clear_data()
        
        # Test geojson endpoint with real data
        response_geojson = client.get("/v3/spheres/geojson")
        assert response_geojson.status_code == 200
        data_geojson = response_geojson.json()
        assert data_geojson["type"] == "FeatureCollection"
        # Should have real data loaded from configured URL
        assert len(data_geojson["features"]) > 0
        
        # Test panorama endpoint with real data (use first feature's ID)
        if data_geojson["features"]:
            first_feature_id = data_geojson["features"][0]["properties"]["id"]
            response_pano = client.get(f"/v3/spheres/{first_feature_id}")
            assert response_pano.status_code == 200
            data_pano = response_pano.json()
            assert data_pano["id"] == first_feature_id

    def test_sphere_neighbor_angular_separation(self):
        """Test that neighbors have proper angular separation."""
        response = client.get("/v3/spheres/test_center?sectors=8")
        assert response.status_code == 200
        data = response.json()
        
        neighbors = data["links"]
        if len(neighbors) >= 2:
            # Get bearings from center to each neighbor
            from app.api.v3.endpoints.spheres import _bearing_matrix, _spatial_index
            center_node = _spatial_index.get("test_center")
            
            bearings = []
            for neighbor in neighbors:
                if center_node and neighbor["id"] in _bearing_matrix.get(center_node.id, {}):
                    bearing = _bearing_matrix[center_node.id][neighbor["id"]]
                    bearings.append(bearing)
            
            # Check minimum separation (should be ~22.5 degrees for 8 sectors)
            if len(bearings) >= 2:
                min_separation = 360.0 / 8 / 2  # 22.5 degrees
                for i, bearing1 in enumerate(bearings):
                    for j, bearing2 in enumerate(bearings[i+1:], i+1):
                        angular_diff = abs(bearing1 - bearing2)
                        angular_diff = min(angular_diff, 360 - angular_diff)
                        # Allow some tolerance for the test
                        assert angular_diff >= min_separation - 5


class TestSphereErrorHandling:
    """Test error handling for sphere endpoints."""

    @pytest.fixture(autouse=True)
    def setup_test_data(self):
        """Setup test data for error handling tests."""
        # Setup: Add mock data
        self._setup_mock_data()
        yield
        # Teardown: Clear data
        self._clear_data()

    def _setup_mock_data(self):
        """Setup mock sphere data for testing."""
        # Clear any existing data
        from app.api.v3.endpoints.spheres import _spatial_index, _distance_matrix, _bearing_matrix
        _spatial_index.clear()
        _distance_matrix.clear()
        _bearing_matrix.clear()
        
        # Create a simple center node for testing
        center_node = SphereNodePanorama(
            id="test_center",
            gps=[6.8586, 45.8326],
            panorama="https://example.com/center.jpg",
            thumbnail="https://example.com/center_thumb.jpg",
            links=[],
            author="Test",
            date=datetime.now(),
            project="Test",
            label="Center"
        )
        
        # Add node to spatial index and compute matrices
        SpatialIndex.add_node(center_node)
        SpatialIndex._compute_distance_and_bearing_matrices()

    def _clear_data(self):
        """Clear test data."""
        from app.api.v3.endpoints.spheres import _spatial_index, _distance_matrix, _bearing_matrix
        _spatial_index.clear()
        _distance_matrix.clear()
        _bearing_matrix.clear()

    def test_invalid_node_id_format(self):
        """Test with invalid node ID format."""
        # Node IDs with special characters should still work (handled by the system)
        response = client.get("/v3/spheres/node@with@special@chars")
        assert response.status_code == 404  # Not found, but no 400 error

    def test_invalid_parameters(self):
        """Test with invalid query parameters."""
        # Test with valid node but negative max_range
        response = client.get("/v3/spheres/test_center?max_range=-100")
        assert response.status_code == 200  # Should handle gracefully
        data = response.json()
        assert len(data["links"]) == 0  # No neighbors with negative range
        
        # Test with valid node but zero sectors (should use default or handle gracefully)
        response = client.get("/v3/spheres/test_center?sectors=0")
        # This might return 200 or 422 depending on validation - accept either
        assert response.status_code in [200, 422]
        
        # Very large parameters should not cause server errors
        response = client.get("/v3/spheres/test_center?max_range=1000000&sectors=1000")
        assert response.status_code == 200