"""
Integration tests for Svalbox photo spheres served next to other providers.
"""

import asyncio

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.v3.endpoints import spheres
from app.main import app
from app.models.spheres import SphereGeojson, SphereNodePanorama
from app.utils.cache import MemoryCache

client = TestClient(app)

LIP_URL = spheres.SphereProjectLinks["The Living Ice Project"]["geojson_url"]
SVALBOX_URL = spheres.SphereProjectLinks["Svalbox"]["geojson_url"]


def lip_geojson():
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [16.1305, 78.1762]},
                "properties": {
                    "id": "lip-1",
                    "filename": "https://example.com/lip-1.jpg",
                    "thumbnail": "https://example.com/lip-1-thumb.jpg",
                    "label": "LIP sphere",
                },
            }
        ],
    }


def svalbox_feature(uid, lon, lat, date, doi="111"):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat, 500.0]},
        "properties": {
            "file": "SHOULD-NEVER-BE-READ",
            "datetime": date,
            "uid": uid,
            "doi": doi,
            "api_link": f"https://zenodo.org/api/iiif/record:{doi}:{uid}.jpg/full/!4000,4000/0/default.jpg",
        },
    }


def svalbox_geojson():
    return {
        "type": "FeatureCollection",
        "features": [
            svalbox_feature("a", 16.13008, 78.17615, "2021-07-01T10:00:00Z"),
            # Same spot as "a" but newer: this one must win
            svalbox_feature("a-new", 16.13008, 78.17615, "2022-07-01T10:00:00Z"),
            # ~100 m from "a"
            svalbox_feature("b", 16.13008, 78.17705, "2022-07-02T10:00:00Z", doi="222"),
            {"type": "Feature", "geometry": None, "properties": {}},  # malformed
        ],
    }


@pytest.fixture(autouse=True)
def zenodo_calls(monkeypatch):
    calls = []

    async def fake_zenodo(_client, doi):
        calls.append(doi)
        return {"label": f"Record {doi}", "author": "Fake Author", "license": "cc"}

    monkeypatch.setattr(spheres, "fetch_zenodo_metadata", fake_zenodo)
    return calls


@pytest.fixture(autouse=True)
def shared_cache(monkeypatch):
    """A fresh in-memory stand-in for Redis (the test suite disables caching)."""
    cache = MemoryCache()
    monkeypatch.setattr(spheres, "get_cache_backend", lambda: cache)
    return cache


@pytest.fixture(autouse=True)
def fresh_state():
    for state in (
        spheres._spatial_index,
        spheres._position_grid,
        spheres._distance_matrix,
        spheres._bearing_matrix,
        spheres._geojson_cache,
    ):
        state.clear()

    yield
    for state in (
        spheres._spatial_index,
        spheres._position_grid,
        spheres._distance_matrix,
        spheres._bearing_matrix,
    ):
        state.clear()


def serve(monkeypatch, **by_url):
    async def fake_fetch(url):
        payload = by_url.get(url)
        if payload is None:
            raise HTTPException(status_code=500, detail="down")
        return payload

    monkeypatch.setattr(spheres, "fetch_geojson_from_url", fake_fetch)


class TestSvalboxProvider:
    async def test_both_projects_are_loaded(self, monkeypatch):
        serve(
            monkeypatch,
            **{LIP_URL: lip_geojson(), SVALBOX_URL: svalbox_geojson()},
        )

        nodes = await spheres.get_all_sphere_nodes()

        projects = {n.project for n in nodes}
        assert projects == {"The Living Ice Project", "Svalbox"}
        svalbox_ids = {n.id for n in nodes if n.project == "Svalbox"}
        # "a" dropped for the newer picture at the same spot, malformed skipped
        assert svalbox_ids == {"svalbox-a-new", "svalbox-b"}

    async def test_zenodo_is_called_once_per_distinct_doi(
        self, monkeypatch, zenodo_calls
    ):
        serve(monkeypatch, **{SVALBOX_URL: svalbox_geojson()})

        await spheres.get_all_sphere_nodes()

        assert sorted(zenodo_calls) == ["111", "222"]

    async def test_geojson_has_credits_and_no_file_data(self, monkeypatch):
        serve(monkeypatch, **{SVALBOX_URL: svalbox_geojson()})

        nodes = await spheres.get_all_sphere_nodes()
        body = SphereGeojson.from_sphere_nodes(nodes).model_dump_json()

        assert "SHOULD-NEVER-BE-READ" not in body
        props = SphereGeojson.from_sphere_nodes(nodes).features[0].properties
        assert props.thumbnail is None
        assert props.license == "cc"
        assert props.doi.startswith("https://doi.org/10.5281/zenodo.")

    async def test_svalbox_failure_still_serves_lip(self, monkeypatch):
        serve(monkeypatch, **{LIP_URL: lip_geojson()})  # Svalbox raises

        nodes = await spheres.get_all_sphere_nodes()

        assert [n.id for n in nodes] == ["lip-1"]

    async def test_zenodo_failure_keeps_spheres(self, monkeypatch):
        serve(monkeypatch, **{SVALBOX_URL: svalbox_geojson()})

        async def zenodo_down(_client, _doi):
            return {}

        monkeypatch.setattr(spheres, "fetch_zenodo_metadata", zenodo_down)

        nodes = await spheres.get_all_sphere_nodes()

        assert len(nodes) == 2
        assert all(n.author is None and n.license is None for n in nodes)

    async def test_second_process_reuses_the_shared_cache(self, monkeypatch):
        serve(monkeypatch, **{LIP_URL: lip_geojson(), SVALBOX_URL: svalbox_geojson()})
        first = await spheres.get_all_sphere_nodes()

        # another worker: nothing reachable, everything comes from the cache
        serve(monkeypatch)
        second = await spheres.get_all_sphere_nodes()

        assert [n.model_dump() for n in second] == [n.model_dump() for n in first]

    async def test_failed_provider_is_not_cached(self, monkeypatch, shared_cache):
        serve(monkeypatch, **{LIP_URL: lip_geojson()})

        await spheres.get_all_sphere_nodes()

        assert shared_cache.get("spheres:nodes:Svalbox") is None
        assert shared_cache.get("spheres:nodes:The Living Ice Project") is not None

    async def test_concurrent_first_requests_load_once(self, monkeypatch):
        fetches = []

        async def counting_fetch(url):
            fetches.append(url)
            await asyncio.sleep(0.01)  # let the other requests pile up
            if url == LIP_URL:
                return lip_geojson()
            return svalbox_geojson()

        monkeypatch.setattr(spheres, "fetch_geojson_from_url", counting_fetch)

        await asyncio.gather(*(spheres.ensure_data_loaded() for _ in range(5)))

        # one fetch per provider, not one per request
        assert len(fetches) == len(spheres.SphereProjectLinks)

    async def test_warm_up_loads_the_index(self, monkeypatch):
        serve(monkeypatch, **{LIP_URL: lip_geojson(), SVALBOX_URL: svalbox_geojson()})

        await spheres.warm_up()

        assert "svalbox-b" in spheres._spatial_index
        assert "lip-1" in spheres._distance_matrix

    async def test_warm_up_never_raises(self, monkeypatch):
        async def boom():
            raise RuntimeError("boom")

        monkeypatch.setattr(spheres, "ensure_data_loaded", boom)

        await spheres.warm_up()

    def test_geojson_matches_what_the_frontend_parses(self, monkeypatch):
        """Existing clients: 2D coordinates, string label, string panorama."""
        serve(monkeypatch, **{LIP_URL: lip_geojson(), SVALBOX_URL: svalbox_geojson()})

        features = client.get("/v3/spheres/geojson").json()["features"]

        assert features
        for f in features:
            assert len(f["geometry"]["coordinates"]) == 2
            assert isinstance(f["properties"]["label"], str)
            assert f["properties"]["panorama"].startswith("https://")
            assert f["properties"]["project"]

    def test_endpoint_panorama_without_thumbnail_and_cross_provider_links(
        self, monkeypatch
    ):
        serve(
            monkeypatch,
            **{LIP_URL: lip_geojson(), SVALBOX_URL: svalbox_geojson()},
        )

        response = client.get("/v3/spheres/svalbox-a-new?max_range=1000&sectors=5")

        assert response.status_code == 200
        data = response.json()
        assert data["thumbnail"] is None
        assert data["project"] == "Svalbox"
        assert data["license"] == "cc"
        linked = {link["id"] for link in data["links"]}
        # a Svalbox neighbour (north) and the LIP sphere (~10 m east): one index
        assert linked == {"svalbox-b", "lip-1"}

    def test_endpoint_geojson_lists_both_projects(self, monkeypatch):
        serve(
            monkeypatch,
            **{LIP_URL: lip_geojson(), SVALBOX_URL: svalbox_geojson()},
        )

        response = client.get("/v3/spheres/geojson")

        assert response.status_code == 200
        ids = {f["properties"]["id"] for f in response.json()["features"]}
        assert ids == {"lip-1", "svalbox-a-new", "svalbox-b"}


class FakeAsyncClient:
    """Stands in for httpx.AsyncClient in fetch_geojson_from_url."""

    calls = []
    payload = {"type": "FeatureCollection", "features": []}
    error = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url):
        FakeAsyncClient.calls.append(url)
        if FakeAsyncClient.error:
            raise FakeAsyncClient.error
        return self

    def raise_for_status(self):
        pass

    def json(self):
        return FakeAsyncClient.payload


class TestFetchGeojson:
    @pytest.fixture(autouse=True)
    def fake_httpx(self, monkeypatch):
        FakeAsyncClient.calls = []
        FakeAsyncClient.error = None
        spheres._cache_timestamp.clear()
        monkeypatch.setattr(spheres.httpx, "AsyncClient", FakeAsyncClient)
        yield
        spheres._cache_timestamp.clear()

    async def test_fetches_then_serves_from_cache(self):
        first = await spheres.fetch_geojson_from_url("https://example.com/a")
        second = await spheres.fetch_geojson_from_url("https://example.com/a")

        assert first == second == FakeAsyncClient.payload
        assert FakeAsyncClient.calls == ["https://example.com/a"]

    async def test_failure_is_an_http_500(self):
        FakeAsyncClient.error = RuntimeError("provider down")

        with pytest.raises(HTTPException) as error:
            await spheres.fetch_geojson_from_url("https://example.com/down")

        assert error.value.status_code == 500


class TestSharedCacheFallbacks:
    async def test_invalid_cached_spheres_are_reloaded(self, monkeypatch, shared_cache):
        serve(monkeypatch, **{SVALBOX_URL: svalbox_geojson()})
        key = "spheres:nodes:Svalbox"
        shared_cache.setex(key, 60, '[{"not": "a sphere"}]')

        nodes = await spheres.get_all_sphere_nodes()

        assert {n.id for n in nodes} == {"svalbox-a-new", "svalbox-b"}
        # and the bad entry was replaced by a good one
        assert "svalbox-b" in shared_cache.get(key)

    async def test_no_dois_means_no_zenodo_call(self, zenodo_calls):
        assert await spheres.fetch_dois_metadata(set()) == {}
        assert zenodo_calls == []

    async def test_lip_feature_that_cannot_be_parsed_is_skipped(self, monkeypatch):
        geojson = lip_geojson()
        geojson["features"].append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [16.0, 78.0]},
                "properties": {"id": "no-panorama"},
            }
        )
        serve(monkeypatch, **{LIP_URL: geojson})

        nodes = await spheres.get_all_sphere_nodes()

        assert [n.id for n in nodes] == ["lip-1"]


class TestLipParser:
    def test_relative_urls_use_the_base_url(self):
        feature = {
            "geometry": {"coordinates": [16.0, 78.0, 12.0]},
            "properties": {
                "id": "rel",
                "filename": "spheres/a.jpg",
                "thumbnail": "/thumbs/a.jpg",
            },
        }

        node = spheres.parse_geojson_feature_to_sphere_node(
            feature, "https://example.com/"
        )

        assert str(node.panorama) == "https://example.com/spheres/a.jpg"
        assert str(node.thumbnail) == "https://example.com/thumbs/a.jpg"
        assert node.gps == [16.0, 78.0, 12.0]

    def test_invalid_coordinates_fall_back_to_origin(self):
        feature = {
            "geometry": {"coordinates": []},
            "properties": {"id": "x", "filename": "https://example.com/x.jpg"},
        }

        node = spheres.parse_geojson_feature_to_sphere_node(feature)

        assert node.gps == [0.0, 0.0]
        assert node.thumbnail is None


class TestMatrices:
    def test_nodes_without_a_position_are_ignored(self):
        broken = SphereNodePanorama.model_construct(
            id="broken", gps=[1.0], panorama="https://example.com/b.jpg", links=[]
        )
        spheres._spatial_index["broken"] = broken

        spheres.SpatialIndex._compute_distance_and_bearing_matrices()

        assert spheres._distance_matrix == {"broken": {}}


class TestStartup:
    def test_lifespan_starts_the_warm_up(self, monkeypatch):
        calls = []

        async def fake_warm_up():
            calls.append("warm_up")

        from app import main

        monkeypatch.setattr(main, "warm_up_spheres", fake_warm_up)

        with TestClient(main.app):
            pass

        assert calls == ["warm_up"]
