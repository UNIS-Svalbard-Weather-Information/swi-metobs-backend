"""
Unit tests for the GeoJSON feature parser of the sphere endpoints.
"""

import pytest

from app.api.v3.endpoints.spheres import (
    SphereGeojson,
    parse_geojson_feature_to_sphere_node,
)


def feature(**properties):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [21.79, 79.75]},
        "properties": {
            "filename": "https://static.example.com/spheres/Sph_A.JPG",
            "thumbnail": "static/thumbnails/Sph_A.thumbnail",
            "date": "2026-04-30T00:00:00",
            "label": "Oxfordhalvoya",
            **properties,
        },
    }


class TestAuthor:
    def test_artist_is_the_photographer(self):
        node = parse_geojson_feature_to_sphere_node(
            feature(artist="Test Photographer"), "https://example.com/"
        )

        assert node.author == "Test Photographer"

    def test_author_property_still_wins_when_present(self):
        node = parse_geojson_feature_to_sphere_node(
            feature(author="Some Author", artist="Test Photographer"),
            "https://example.com/",
        )

        assert node.author == "Some Author"

    @pytest.mark.parametrize("missing", [{}, {"artist": None}, {"artist": ""}])
    def test_no_photographer_gives_none(self, missing):
        node = parse_geojson_feature_to_sphere_node(
            feature(**missing), "https://example.com/"
        )

        assert node.author is None

    def test_photographer_reaches_the_geojson(self):
        node = parse_geojson_feature_to_sphere_node(
            feature(artist="Test Photographer"), "https://example.com/"
        )

        properties = SphereGeojson.from_sphere_nodes([node]).features[0].properties

        assert properties.author == "Test Photographer"
