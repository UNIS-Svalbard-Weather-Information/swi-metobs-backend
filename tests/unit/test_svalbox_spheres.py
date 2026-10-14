"""
Unit tests for the Svalbox photo sphere provider.
"""

from datetime import datetime, timezone

import pytest

from app.api.v3.endpoints import spheres
from app.api.v3.endpoints.spheres import (
    keep_latest_per_spot,
    parse_svalbox_feature,
)
from app.models.spheres import SphereGeojson, SphereNodePanorama
from app.utils.cache import MemoryCache


def svalbox_feature(uid="abc-1", lon=16.13, lat=78.17, doi="7277342", **overrides):
    properties = {
        "comment": None,
        "file": "SHOULD-NEVER-BE-READ",
        "datetime": "2022-07-27T09:22:45Z",
        "make": "Hasselblad",
        "uid": uid,
        "doi": doi,
        "api_link": f"https://zenodo.org/api/iiif/record:{doi}:{uid}.jpg/full/!4000,4000/0/default.jpg",
        "vft_id": None,
    }
    properties.update(overrides)
    return {
        "type": "Feature",
        "id": f"photo_sphere.{uid}",
        "geometry": {"type": "Point", "coordinates": [lon, lat, 521.5]},
        "properties": properties,
    }


def node(id_, lon, lat, date):
    return SphereNodePanorama(
        id=id_,
        gps=[lon, lat],
        panorama=f"https://example.com/{id_}.jpg",
        links=[],
        date=date,
    )


class TestModel:
    def test_thumbnail_is_optional(self):
        n = node("a", 1.0, 2.0, None)
        assert n.thumbnail is None

    def test_bad_panorama_extension_still_rejected(self):
        with pytest.raises(ValueError):
            SphereNodePanorama(
                id="a", gps=[1.0, 2.0], panorama="https://example.com/a.txt", links=[]
            )

    def test_bad_thumbnail_extension_still_rejected(self):
        with pytest.raises(ValueError):
            SphereNodePanorama(
                id="a",
                gps=[1.0, 2.0],
                panorama="https://example.com/a.jpg",
                thumbnail="https://example.com/a.txt",
                links=[],
            )


class TestParseSvalboxFeature:
    def test_maps_fields(self):
        meta = {
            "7277342": {"label": "A title", "author": "Fake Author", "license": "cc"}
        }
        n = parse_svalbox_feature(svalbox_feature(), meta)

        assert n.id == "svalbox-abc-1"
        assert n.gps == [16.13, 78.17, 521.5]
        assert str(n.panorama).endswith("default.jpg")
        assert n.thumbnail is None
        assert n.date == datetime(2022, 7, 27, 9, 22, 45, tzinfo=timezone.utc)
        assert n.project == "Svalbox"
        assert n.label == "A title"
        assert n.author == "Fake Author"
        assert n.license == "cc"
        assert n.doi == "https://doi.org/10.5281/zenodo.7277342"

    def test_works_without_doi_metadata(self):
        n = parse_svalbox_feature(svalbox_feature(), {})
        assert n.author is None and n.license is None
        # existing clients require a label on every sphere
        assert n.label == spheres.SVALBOX_DEFAULT_LABEL

    def test_never_exposes_file_property(self):
        n = parse_svalbox_feature(svalbox_feature())
        assert "SHOULD-NEVER-BE-READ" not in n.model_dump_json()

    def test_2d_coordinates(self):
        f = svalbox_feature()
        f["geometry"]["coordinates"] = [16.13, 78.17]
        assert parse_svalbox_feature(f).gps == [16.13, 78.17]

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda f: f["properties"].pop("uid"),
            lambda f: f["properties"].update(api_link=None),
            lambda f: f["geometry"].update(coordinates=[]),
        ],
    )
    def test_malformed_feature_raises(self, mutate):
        f = svalbox_feature()
        mutate(f)
        with pytest.raises(Exception):
            parse_svalbox_feature(f)


class TestGeojsonCompatibility:
    def test_coordinates_are_2d_even_with_altitude(self):
        n = parse_svalbox_feature(svalbox_feature())
        assert len(n.gps) == 3  # altitude kept on the node (/spheres/{id})

        feature = SphereGeojson.from_sphere_nodes([n]).features[0]

        assert feature.geometry.coordinates == [16.13, 78.17]


class TestKeepLatestPerSpot:
    def test_same_spot_keeps_most_recent(self):
        old = node("old", 16.0, 78.0, datetime(2020, 1, 1))
        new = node("new", 16.0, 78.0, datetime(2022, 1, 1))
        mid = node("mid", 16.0, 78.0, datetime(2021, 1, 1))

        kept = keep_latest_per_spot([old, new, mid])

        assert [n.id for n in kept] == ["new"]

    def test_distant_spheres_are_both_kept(self):
        a = node("a", 16.0, 78.0, datetime(2020, 1, 1))
        b = node("b", 16.01, 78.0, datetime(2022, 1, 1))  # ~240 m away

        assert {n.id for n in keep_latest_per_spot([a, b])} == {"a", "b"}

    def test_within_radius_but_not_identical_coordinates(self):
        a = node("a", 16.0, 78.0, datetime(2020, 1, 1))
        b = node("b", 16.0, 78.00001, datetime(2021, 1, 1))  # ~1 m away

        assert [n.id for n in keep_latest_per_spot([a, b], radius_m=3.0)] == ["b"]

    def test_dated_beats_undated(self):
        undated = node("undated", 16.0, 78.0, None)
        dated = node("dated", 16.0, 78.0, datetime(2019, 1, 1))

        assert [n.id for n in keep_latest_per_spot([undated, dated])] == ["dated"]

    def test_tie_keeps_first_in_input_order(self):
        d = datetime(2020, 1, 1)
        a = node("a", 16.0, 78.0, d)
        b = node("b", 16.0, 78.0, d)

        assert [n.id for n in keep_latest_per_spot([a, b])] == ["a"]

    def test_empty(self):
        assert keep_latest_per_spot([]) == []


class FakeResponse:
    def __init__(self, payload=None, error=None):
        self._payload, self._error = payload, error

    def raise_for_status(self):
        if self._error:
            raise self._error

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, responses):
        self.responses, self.calls = responses, []

    async def get(self, url):
        self.calls.append(url)
        return self.responses[url.rsplit("/", 1)[-1]]


class TestZenodoMetadata:
    @pytest.fixture(autouse=True)
    def shared_cache(self, monkeypatch):
        cache = MemoryCache()
        monkeypatch.setattr(spheres, "get_cache_backend", lambda: cache)
        return cache

    async def test_maps_record_and_caches(self):
        payload = {
            "metadata": {
                "title": "T",
                "creators": [{"name": "Fake One"}, {"name": "Fake Two"}],
                "license": {"id": "cc-by-nc-4.0"},
            }
        }
        client = FakeClient({"1": FakeResponse(payload)})

        first = await spheres.fetch_zenodo_metadata(client, "1")
        second = await spheres.fetch_zenodo_metadata(client, "1")

        assert first == {
            "label": "T",
            "author": "Fake One; Fake Two",
            "license": "cc-by-nc-4.0",
        }
        assert second == first
        assert len(client.calls) == 1

    async def test_cache_is_shared_through_the_backend(self, shared_cache):
        payload = {"metadata": {"title": "T"}}
        await spheres.fetch_zenodo_metadata(
            FakeClient({"1": FakeResponse(payload)}), "1"
        )
        # another process: no call needed, the shared cache has it
        other = FakeClient({})

        assert (await spheres.fetch_zenodo_metadata(other, "1"))["label"] == "T"
        assert other.calls == []

    async def test_failure_gives_empty_and_is_not_cached(self, shared_cache):
        client = FakeClient({"1": FakeResponse(error=RuntimeError("down"))})

        assert await spheres.fetch_zenodo_metadata(client, "1") == {}
        assert shared_cache.get("spheres:doi:1") is None

    async def test_broken_cache_backend_is_only_a_miss(self, monkeypatch):
        class Broken:
            def get(self, key):
                raise RuntimeError("redis down")

            def setex(self, key, ttl, value):
                raise RuntimeError("redis down")

        monkeypatch.setattr(spheres, "get_cache_backend", lambda: Broken())
        client = FakeClient({"1": FakeResponse({"metadata": {"title": "T"}})})

        assert (await spheres.fetch_zenodo_metadata(client, "1"))["label"] == "T"

    async def test_record_without_creators_or_license(self):
        client = FakeClient({"1": FakeResponse({"metadata": {"title": "T"}})})

        assert await spheres.fetch_zenodo_metadata(client, "1") == {
            "label": "T",
            "author": None,
            "license": None,
        }
