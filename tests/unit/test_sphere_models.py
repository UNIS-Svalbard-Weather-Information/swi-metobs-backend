"""
Unit tests for sphere models.
"""

import pytest
from datetime import datetime
from app.models.spheres import SphereNode, SphereNodePanorama, SphereGeojson, Geometry, Properties, Feature
from pydantic import ValidationError


class TestSphereNode:
    """Test cases for SphereNode model."""

    def test_valid_sphere_node_2d(self):
        """Test valid SphereNode with 2D coordinates."""
        node = SphereNode(id="test_node", gps=[6.8586, 45.8326])
        assert node.id == "test_node"
        assert node.gps == [6.8586, 45.8326]

    def test_valid_sphere_node_3d(self):
        """Test valid SphereNode with 3D coordinates (including altitude)."""
        node = SphereNode(id="test_node_3d", gps=[6.8586, 45.8326, 1200.5])
        assert node.id == "test_node_3d"
        assert node.gps == [6.8586, 45.8326, 1200.5]

    def test_invalid_sphere_node_latitude_range(self):
        """Test invalid SphereNode with out-of-range latitude."""
        with pytest.raises(ValidationError):
            SphereNode(id="invalid_node", gps=[6.8586, 100.0])  # Latitude > 90

    def test_invalid_sphere_node_longitude_range(self):
        """Test invalid SphereNode with out-of-range longitude."""
        with pytest.raises(ValidationError):
            SphereNode(id="invalid_node", gps=[200.0, 45.8326])  # Longitude > 180

    def test_invalid_sphere_node_altitude_range(self):
        """Test invalid SphereNode with out-of-range altitude."""
        with pytest.raises(ValidationError):
            SphereNode(id="invalid_node", gps=[6.8586, 45.8326, 15000.0])  # Altitude >= 10000

    def test_invalid_sphere_node_too_few_coordinates(self):
        """Test invalid SphereNode with insufficient coordinates."""
        with pytest.raises(ValidationError):
            SphereNode(id="invalid_node", gps=[6.8586])  # Only 1 coordinate

    def test_invalid_sphere_node_too_many_coordinates(self):
        """Test invalid SphereNode with too many coordinates."""
        with pytest.raises(ValidationError):
            SphereNode(id="invalid_node", gps=[6.8586, 45.8326, 100.0, 50.0])  # 4 coordinates


class TestSphereNodePanorama:
    """Test cases for SphereNodePanorama model."""

    def test_valid_sphere_node_panorama(self):
        """Test valid SphereNodePanorama with all fields."""
        node = SphereNodePanorama(
            id="panorama_node",
            gps=[6.8586, 45.8326],
            panorama="https://example.com/panorama.jpg",
            thumbnail="https://example.com/thumbnail.jpg",
            links=[],
            author="Test Author",
            date=datetime(2023, 1, 1, 12, 0, 0),
            project="Test Project",
            label="Test Label"
        )
        assert node.id == "panorama_node"
        assert node.gps == [6.8586, 45.8326]
        assert str(node.panorama) == "https://example.com/panorama.jpg"
        assert str(node.thumbnail) == "https://example.com/thumbnail.jpg"
        assert node.author == "Test Author"
        assert node.project == "Test Project"
        assert node.label == "Test Label"

    def test_invalid_panorama_url_extension(self):
        """Test invalid panorama URL without proper image extension."""
        with pytest.raises(ValidationError):
            SphereNodePanorama(
                id="invalid_node",
                gps=[6.8586, 45.8326],
                panorama="https://example.com/file.pdf",  # Invalid extension
                thumbnail="https://example.com/thumbnail.jpg",
                links=[]
            )

    def test_invalid_thumbnail_url_extension(self):
        """Test invalid thumbnail URL without proper image extension."""
        with pytest.raises(ValidationError):
            SphereNodePanorama(
                id="invalid_node",
                gps=[6.8586, 45.8326],
                panorama="https://example.com/panorama.jpg",
                thumbnail="https://example.com/file.doc",  # Invalid extension
                links=[]
            )

    def test_valid_url_extensions(self):
        """Test valid URL extensions."""
        valid_extensions = [".jpg", ".jpeg", ".png", ".gif", ".webp", ".thumbnail"]
        
        for ext in valid_extensions:
            node = SphereNodePanorama(
                id=f"node_{ext}",
                gps=[6.8586, 45.8326],
                panorama=f"https://example.com/panorama{ext}",
                thumbnail=f"https://example.com/thumbnail{ext}",
                links=[]
            )
            assert node.id == f"node_{ext}"


class TestSphereGeojson:
    """Test cases for SphereGeojson model and related classes."""

    def test_valid_geometry(self):
        """Test valid Geometry object."""
        geometry = Geometry(coordinates=[6.8586, 45.8326])
        assert geometry.type == "Point"
        assert geometry.coordinates == [6.8586, 45.8326]

    def test_valid_properties(self):
        """Test valid Properties object."""
        props = Properties(
            id="test_node",
            panorama="https://example.com/panorama.jpg",
            thumbnail="https://example.com/thumbnail.jpg",
            author="Test Author",
            date=datetime(2023, 1, 1),
            project="Test Project",
            label="Test Label"
        )
        assert props.id == "test_node"
        assert str(props.panorama) == "https://example.com/panorama.jpg"

    def test_valid_feature(self):
        """Test valid Feature object."""
        geometry = Geometry(coordinates=[6.8586, 45.8326])
        properties = Properties(id="test_node")
        feature = Feature(properties=properties, geometry=geometry)
        assert feature.type == "Feature"
        assert feature.properties.id == "test_node"

    def test_sphere_geojson_from_sphere_nodes(self):
        """Test SphereGeojson creation from SphereNodePanorama objects."""
        nodes = [
            SphereNodePanorama(
                id="node1",
                gps=[6.8586, 45.8326],
                panorama="https://example.com/pano1.jpg",
                thumbnail="https://example.com/thumb1.jpg",
                links=[],
                author="Author1",
                date=datetime(2023, 1, 1),
                project="Project1",
                label="Label1"
            ),
            SphereNodePanorama(
                id="node2",
                gps=[6.8600, 45.8330],
                panorama="https://example.com/pano2.jpg",
                thumbnail="https://example.com/thumb2.jpg",
                links=[],
                author="Author2",
                date=datetime(2023, 1, 2),
                project="Project2",
                label="Label2"
            )
        ]
        
        geojson = SphereGeojson.from_sphere_nodes(nodes)
        assert geojson.type == "FeatureCollection"
        assert len(geojson.features) == 2
        assert geojson.features[0].properties.id == "node1"
        assert geojson.features[1].properties.id == "node2"

    def test_empty_sphere_geojson(self):
        """Test SphereGeojson creation from empty node list."""
        geojson = SphereGeojson.from_sphere_nodes([])
        assert geojson.type == "FeatureCollection"
        assert len(geojson.features) == 0