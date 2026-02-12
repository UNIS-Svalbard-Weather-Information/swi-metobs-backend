"""
Unit tests for sphere utility functions.
"""

import pytest
import math
from app.api.v3.endpoints.spheres import SpatialIndex
from app.models.spheres import SphereNodePanorama, SphereNode
from datetime import datetime


class TestSpatialIndex:
    """Test cases for SpatialIndex utility functions."""

    def test_get_grid_key(self):
        """Test grid key calculation."""
        # Test basic grid key calculation
        grid_key = SpatialIndex._get_grid_key(6.8586, 45.8326)
        assert len(grid_key) == 2
        assert isinstance(grid_key[0], float)
        assert isinstance(grid_key[1], float)
        
        # Test that same coordinates produce same grid key
        grid_key2 = SpatialIndex._get_grid_key(6.8586, 45.8326)
        assert grid_key == grid_key2
        
        # Test that different coordinates produce different grid keys
        grid_key3 = SpatialIndex._get_grid_key(7.0, 46.0)
        assert grid_key != grid_key3

    def test_haversine_distance(self):
        """Test Haversine distance calculation."""
        # Test distance from a point to itself (should be 0)
        distance = SpatialIndex._haversine_distance(0.0, 0.0, 0.0, 0.0)
        assert distance == 0.0
        
        # Test known distance (approximate)
        # Distance between (0,0) and (1,0) should be about 111km at equator
        distance = SpatialIndex._haversine_distance(0.0, 0.0, 1.0, 0.0)
        assert 110000 < distance < 112000  # Approximate check
        
        # Test distance between Grenoble and Lyon (approximate)
        distance = SpatialIndex._haversine_distance(5.7278, 45.1885, 4.8357, 45.7640)
        assert 80000 < distance < 100000  # About 90km

    def test_calculate_bearing(self):
        """Test bearing calculation."""
        # Test bearing from a point to itself (should be 0)
        bearing = SpatialIndex._calculate_bearing(0.0, 0.0, 0.0, 0.0)
        assert bearing == 0.0
        
        # Test bearing from (0,0) to (1,0) - should be east (90 degrees)
        bearing = SpatialIndex._calculate_bearing(0.0, 0.0, 1.0, 0.0)
        assert 85 < bearing < 95  # Approximate due to projection
        
        # Test bearing from (0,0) to (0,1) - should be north (0 degrees)
        bearing = SpatialIndex._calculate_bearing(0.0, 0.0, 0.0, 1.0)
        assert -5 < bearing < 5  # Approximate due to projection
        
        # Test that bearing is normalized to 0-360 range
        bearing = SpatialIndex._calculate_bearing(0.0, 0.0, -1.0, 0.0)
        assert 265 < bearing < 275  # West direction


class TestDistanceMatrix:
    """Test cases for distance matrix computation."""

    def test_distance_matrix_creation(self):
        """Test distance matrix creation with mock nodes."""
        # Create some mock nodes
        nodes = [
            SphereNodePanorama(
                id="node1",
                gps=[0.0, 0.0],
                panorama="https://example.com/pano1.jpg",
                thumbnail="https://example.com/thumb1.jpg",
                links=[],
                author="Test",
                date=datetime.now(),
                project="Test",
                label="Node 1"
            ),
            SphereNodePanorama(
                id="node2",
                gps=[1.0, 0.0],
                panorama="https://example.com/pano2.jpg",
                thumbnail="https://example.com/thumb2.jpg",
                links=[],
                author="Test",
                date=datetime.now(),
                project="Test",
                label="Node 2"
            ),
            SphereNodePanorama(
                id="node3",
                gps=[0.0, 1.0],
                panorama="https://example.com/pano3.jpg",
                thumbnail="https://example.com/thumb3.jpg",
                links=[],
                author="Test",
                date=datetime.now(),
                project="Test",
                label="Node 3"
            )
        ]
        
        # Add nodes to spatial index
        for node in nodes:
            SpatialIndex.add_node(node)
        
        # Compute distance matrix
        SpatialIndex._compute_distance_and_bearing_matrices()
        
        # Check that distance matrix was created
        from app.api.v3.endpoints.spheres import _distance_matrix, _bearing_matrix
        assert len(_distance_matrix) == 3
        assert len(_bearing_matrix) == 3
        
        # Check self-distances are 0
        assert _distance_matrix["node1"]["node1"] == 0.0
        assert _distance_matrix["node2"]["node2"] == 0.0
        assert _distance_matrix["node3"]["node3"] == 0.0
        
        # Check that distances are symmetric
        assert _distance_matrix["node1"]["node2"] == _distance_matrix["node2"]["node1"]
        assert _distance_matrix["node1"]["node3"] == _distance_matrix["node3"]["node1"]
        
        # Check that bearings are reasonable
        bearing_1_to_2 = _bearing_matrix["node1"]["node2"]
        bearing_2_to_1 = _bearing_matrix["node2"]["node1"]
        assert 80 < bearing_1_to_2 < 100  # East direction
        assert 260 < bearing_2_to_1 < 280  # West direction


class TestFindNeighbors:
    """Test cases for find_neighbors method."""

    def setup_method(self):
        """Setup test data."""
        # Clear any existing data
        from app.api.v3.endpoints.spheres import _spatial_index, _distance_matrix, _bearing_matrix
        _spatial_index.clear()
        _distance_matrix.clear()
        _bearing_matrix.clear()
        
        # Create test nodes in a circle around center
        center_lon, center_lat = 0.0, 0.0
        radius = 0.1  # Small radius for testing
        
        self.nodes = []
        for i in range(4):  # 4 nodes at 90 degree intervals
            angle = math.radians(i * 90)
            lon = center_lon + radius * math.cos(angle)
            lat = center_lat + radius * math.sin(angle)
            
            node = SphereNodePanorama(
                id=f"node_{i}",
                gps=[lon, lat],
                panorama=f"https://example.com/pano{i}.jpg",
                thumbnail=f"https://example.com/thumb{i}.jpg",
                links=[],
                author="Test",
                date=datetime.now(),
                project="Test",
                label=f"Node {i}"
            )
            self.nodes.append(node)
        
        # Add center node
        self.center_node = SphereNodePanorama(
            id="center",
            gps=[center_lon, center_lat],
            panorama="https://example.com/center.jpg",
            thumbnail="https://example.com/center_thumb.jpg",
            links=[],
            author="Test",
            date=datetime.now(),
            project="Test",
            label="Center"
        )
        self.nodes.append(self.center_node)
        
        # Add nodes to spatial index and compute matrices
        for node in self.nodes:
            SpatialIndex.add_node(node)
        SpatialIndex._compute_distance_and_bearing_matrices()

    def test_find_neighbors_basic(self):
        """Test basic neighbor finding."""
        neighbors = SpatialIndex.find_neighbors(self.center_node, max_range=20000, sectors=4)
        
        # Should find all 4 surrounding nodes
        assert len(neighbors) == 4
        
        # All neighbors should be SphereNode instances
        for neighbor in neighbors:
            assert isinstance(neighbor, SphereNode)
            assert neighbor.id in [f"node_{i}" for i in range(4)]

    def test_find_neighbors_distance_filtering(self):
        """Test distance-based filtering."""
        # Very small range should find no neighbors
        neighbors = SpatialIndex.find_neighbors(self.center_node, max_range=100, sectors=4)
        assert len(neighbors) == 0
        
        # Large range should find all neighbors
        neighbors = SpatialIndex.find_neighbors(self.center_node, max_range=20000, sectors=4)
        assert len(neighbors) == 4

    def test_find_neighbors_sector_filtering(self):
        """Test sector-based filtering."""
        # With 8 sectors, should get fewer neighbors due to angular separation
        neighbors_4 = SpatialIndex.find_neighbors(self.center_node, max_range=20000, sectors=4)
        neighbors_8 = SpatialIndex.find_neighbors(self.center_node, max_range=20000, sectors=8)
        
        # More sectors should result in fewer or equal neighbors
        assert len(neighbors_8) <= len(neighbors_4)
        
        # With 8 sectors, should get at most 8 neighbors
        assert len(neighbors_8) <= 8

    def test_find_neighbors_angular_separation(self):
        """Test that neighbors have minimum angular separation."""
        sectors = 4
        neighbors = SpatialIndex.find_neighbors(self.center_node, max_range=20000, sectors=sectors)
        
        if len(neighbors) >= 2:
            # Get bearings of selected neighbors
            bearings = []
            from app.api.v3.endpoints.spheres import _bearing_matrix
            for neighbor in neighbors:
                bearing = _bearing_matrix[self.center_node.id][neighbor.id]
                bearings.append(bearing)
            
            # Check minimum separation
            min_separation = 360.0 / sectors / 2
            for i, bearing1 in enumerate(bearings):
                for j, bearing2 in enumerate(bearings[i+1:], i+1):
                    angular_diff = abs(bearing1 - bearing2)
                    angular_diff = min(angular_diff, 360 - angular_diff)
                    assert angular_diff >= min_separation - 1  # Allow small tolerance

    def test_find_neighbors_invalid_input(self):
        """Test with invalid input."""
        # Test with node that has invalid GPS (too few coordinates)
        # Create a mock node that bypasses validation for testing
        class MockSphereNodePanorama:
            def __init__(self):
                self.id = "invalid"
                self.gps = [0.0]  # Invalid GPS - only 1 coordinate
                self.panorama = "https://example.com/invalid.jpg"
                self.thumbnail = "https://example.com/invalid_thumb.jpg"
                self.links = []
                self.author = "Test"
                self.date = datetime.now()
                self.project = "Test"
                self.label = "Invalid"
        
        invalid_node = MockSphereNodePanorama()
        
        neighbors = SpatialIndex.find_neighbors(invalid_node, max_range=1000, sectors=4)
        assert len(neighbors) == 0