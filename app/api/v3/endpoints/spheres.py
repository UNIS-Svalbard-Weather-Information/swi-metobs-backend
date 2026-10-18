from fastapi import HTTPException, APIRouter, Query
from app.models.spheres import SphereGeojson, SphereNodePanorama, SphereNode
from app.utils.cache import cache_response, get_cache_backend
import json
import os
import httpx
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime, timedelta
import asyncio
import math
import numpy as np
from collections import defaultdict
from loguru import logger

# Get the router from parent
router = APIRouter()

SVALBOX_PROJECT = "Svalbox"
SVALBOX_ID_PREFIX = "svalbox-"
# Spheres of the same project closer than this are the same spot: keep the latest
SVALBOX_DEDUPE_RADIUS_M = 3.0
ZENODO_RECORD_URL = "https://zenodo.org/api/records/{doi}"
ZENODO_DOI_URL = "https://doi.org/10.5281/zenodo.{doi}"

# "type" selects how the project's GeoJSON is turned into sphere nodes
SphereProjectLinks = {
    "The Living Ice Project": {
        "type": "lip",
        "geojson_url": os.getenv(
            "SPHERE_LIP_GEOJSON_FETCH",
            "https://livingiceproject.com/static/shapes/spheres.geojson",
        ),
        "base_url": os.getenv("SPHERE_LIP_BASE_URL", "https://livingiceproject.com/"),
    },
    SVALBOX_PROJECT: {
        "type": "svalbox",
        "geojson_url": os.getenv(
            "SPHERE_SVALBOX_GEOJSON_FETCH",
            "https://svalbox.unis.no/geoserver/svalbox/ows?service=WFS&version=2.0.0"
            "&request=GetFeature&typeName=svalbox%3Aphoto_sphere"
            "&srsName=EPSG%3A4326&outputFormat=application%2Fjson",
        ),
        "base_url": "",
    },
}

# Cache for storing fetched GeoJSON data and spatial index
_geojson_cache: Dict[str, Dict] = {}
_cache_timestamp: Dict[str, datetime] = {}
CACHE_TTL = timedelta(hours=1)  # Cache for 1 hour

# Shared cache (Redis when configured), so that all workers and nodes reuse the
# fetched, credited and deduplicated nodes instead of each redoing the work
PROJECT_NODES_CACHE_KEY = "spheres:nodes:{project}"
PROJECT_NODES_TTL = 3600
# Zenodo record metadata (title, authors, license) per DOI; it does not change
DOI_METADATA_CACHE_KEY = "spheres:doi:{doi}"
DOI_METADATA_TTL = 24 * 3600

# Every sphere gets a label, as existing clients require one
SVALBOX_DEFAULT_LABEL = "Svalbox 360 image"

# Serialises the first load, so that concurrent requests and the start-up
# warm-up do not all fetch and index the data
_load_lock = asyncio.Lock()

# Spatial index for efficient neighbor search
_spatial_index: Dict[str, SphereNodePanorama] = {}  # id -> node
_position_grid: Dict[Tuple[float, float], List[str]] = defaultdict(
    list
)  # (grid_x, grid_y) -> [node_ids]
GRID_SIZE = 0.001  # Approximately 111 meters at equator (0.001 degrees)

# Distance matrix cache: node_id -> {other_node_id: distance}
_distance_matrix: Dict[str, Dict[str, float]] = {}
# Bearing matrix cache: node_id -> {other_node_id: bearing}
_bearing_matrix: Dict[str, Dict[str, float]] = {}


class SpatialIndex:
    """Spatial indexing system for efficient neighbor search."""

    @staticmethod
    def _get_grid_key(lon: float, lat: float) -> Tuple[float, float]:
        """Convert coordinates to grid key."""
        grid_x = round(lon / GRID_SIZE) * GRID_SIZE
        grid_y = round(lat / GRID_SIZE) * GRID_SIZE
        return (grid_x, grid_y)

    @staticmethod
    def _haversine_distance(
        lon1: float, lat1: float, lon2: float, lat2: float
    ) -> float:
        """Calculate Haversine distance between two points in meters."""
        # Convert degrees to radians
        lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])

        # Haversine formula
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.asin(math.sqrt(a))

        # Earth radius in meters
        r = 6371000
        return c * r

    @staticmethod
    def _calculate_bearing(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
        """Calculate bearing from point 1 to point 2 in degrees."""
        lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])

        dlon = lon2 - lon1
        y = math.sin(dlon) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(
            lat2
        ) * math.cos(dlon)

        bearing = math.degrees(math.atan2(y, x))
        return (bearing + 360) % 360  # Normalize to 0-360

    @staticmethod
    def add_node(node: SphereNodePanorama):
        """Add a node to the spatial index."""
        if len(node.gps) >= 2:
            lon, lat = node.gps[0], node.gps[1]
            grid_key = SpatialIndex._get_grid_key(lon, lat)
            _position_grid[grid_key].append(node.id)
            _spatial_index[node.id] = node

    @staticmethod
    def _compute_distance_and_bearing_matrices():
        """
        Compute distance and bearing matrices for all nodes.

        This method creates two N×N matrices where N is the number of nodes:
        - Distance matrix: Stores the Haversine distance (in meters) between each pair of nodes
        - Bearing matrix: Stores the compass bearing (in degrees) from each node to every other node

        The matrices are computed once when data is loaded and cached for efficient neighbor lookup.
        This approach has O(N²) time complexity during initialization but enables O(1) distance
        and bearing lookups during neighbor search operations.
        """
        global _distance_matrix, _bearing_matrix

        node_ids = list(_spatial_index.keys())

        # Initialize matrices
        _distance_matrix = {node_id: {} for node_id in node_ids}
        _bearing_matrix = {node_id: {} for node_id in node_ids}

        # Nodes without a usable position take no part, as before
        valid_ids = [i for i in node_ids if len(_spatial_index[i].gps) >= 2]
        if not valid_ids:
            return

        lon = np.radians([_spatial_index[i].gps[0] for i in valid_ids])
        lat = np.radians([_spatial_index[i].gps[1] for i in valid_ids])
        cos_lat, sin_lat = np.cos(lat), np.sin(lat)

        # One vectorised row per node (same formulas as _haversine_distance and
        # _calculate_bearing): much faster than N^2 scalar calls
        for row, node_id in enumerate(valid_ids):
            dlon = lon - lon[row]
            dlat = lat - lat[row]
            a = np.sin(dlat / 2) ** 2 + cos_lat[row] * cos_lat * np.sin(dlon / 2) ** 2
            distance = 2 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0))) * 6371000

            y = np.sin(dlon) * cos_lat
            x = cos_lat[row] * sin_lat - sin_lat[row] * cos_lat * np.cos(dlon)
            bearing = (np.degrees(np.arctan2(y, x)) + 360) % 360

            # Distance and bearing to self are 0
            distance[row] = 0.0
            bearing[row] = 0.0

            _distance_matrix[node_id] = dict(zip(valid_ids, distance.tolist()))
            _bearing_matrix[node_id] = dict(zip(valid_ids, bearing.tolist()))

    @staticmethod
    def find_neighbors(
        target_node: SphereNodePanorama, max_range: float, sectors: int
    ) -> List[SphereNode]:
        """
        Find neighboring nodes using precomputed distance matrix and bearing-based filtering.

        This method implements an efficient neighbor search algorithm:
        1. Uses the precomputed distance matrix to quickly find all nodes within max_range
        2. Sorts neighbors by distance (closest first)
        3. Applies minimum angular separation filtering to ensure well-distributed neighbors
        4. Selects at most 'sectors' neighbors, each separated by at least (360°/sectors)/2

        The algorithm ensures that selected neighbors are both close and well-distributed
        around the target node, providing good coverage for panorama navigation.

        Args:
            target_node: The node to find neighbors for
            max_range: Maximum distance in meters for neighbors
            sectors: Number of angular sectors (determines minimum separation)

        Returns:
            List of SphereNode objects representing the selected neighbors
        """
        if len(target_node.gps) < 2:
            logger.warning(f"Target node {target_node.id} has invalid GPS coordinates")
            return []

        if target_node.id not in _distance_matrix:
            logger.warning(f"Target node {target_node.id} not found in distance matrix")
            return []

        # Get all nodes within max_range distance
        neighbors_within_range = []

        for other_node_id, distance in _distance_matrix[target_node.id].items():
            if other_node_id == target_node.id:
                continue  # Skip self

            if distance <= max_range:
                other_node = _spatial_index.get(other_node_id)
                if other_node and len(other_node.gps) >= 2:
                    bearing = _bearing_matrix[target_node.id][other_node_id]
                    neighbors_within_range.append((distance, bearing, other_node))

        neighbors_within_range.sort(key=lambda x: x[0])

        # If no neighbors within range, return empty list
        if not neighbors_within_range:
            return []

        # Apply minimum angular separation filtering
        selected_neighbors = []
        selected_bearings = []
        min_angular_separation = 360.0 / sectors / 2  # Half of sector width

        for distance, bearing, neighbor_node in neighbors_within_range:
            # Check if this neighbor is sufficiently separated from already selected ones
            is_separated = True
            for selected_bearing in selected_bearings:
                angular_diff = abs(bearing - selected_bearing)
                # Handle circular difference (0-360 degrees)
                angular_diff = min(angular_diff, 360 - angular_diff)
                if angular_diff < min_angular_separation:
                    is_separated = False
                    break

            if is_separated:
                selected_neighbors.append((distance, bearing, neighbor_node))
                selected_bearings.append(bearing)

                # If we have enough neighbors (one per sector), we can stop
                if len(selected_neighbors) >= sectors:
                    break

        # Convert selected neighbors to SphereNode objects
        result_nodes = []
        for distance, bearing, neighbor_node in selected_neighbors:
            result_nodes.append(SphereNode(id=neighbor_node.id, gps=neighbor_node.gps))

        return result_nodes


async def fetch_geojson_from_url(url: str) -> Dict:
    """Fetch GeoJSON data from a URL with caching."""
    # Check if we have cached data that's still valid
    if url in _geojson_cache:
        cached_time = _cache_timestamp.get(url)
        if cached_time and datetime.now() - cached_time < CACHE_TTL:
            logger.info(f"Using cached GeoJSON data for {url}")
            return _geojson_cache[url]

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            geojson_data = response.json()

            # Cache the data
            _geojson_cache[url] = geojson_data
            _cache_timestamp[url] = datetime.now()
            logger.info(f"Fetched and cached GeoJSON data from {url}")

            return geojson_data
    except Exception as e:
        logger.error(f"Failed to fetch GeoJSON from {url}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch GeoJSON data from {url}: {str(e)}"
        )


def parse_geojson_feature_to_sphere_node(
    feature: Dict, base_url: str = ""
) -> SphereNodePanorama:
    """Convert a GeoJSON feature to a SphereNodePanorama object."""
    properties = feature.get("properties", {})
    geometry = feature.get("geometry", {})

    # Extract coordinates (handle both 2D and 3D)
    coordinates = geometry.get("coordinates", [])
    if len(coordinates) >= 2:
        gps = [coordinates[0], coordinates[1]]  # [longitude, latitude]
        if len(coordinates) == 3:
            gps.append(coordinates[2])  # altitude
    else:
        gps = [0.0, 0.0]  # default if coordinates are invalid

    # Extract panorama and thumbnail URLs from properties
    # Use the filename from panorama URL as the ID if not provided
    panorama_url = properties.get("filename", "")
    node_id = properties.get(
        "id", os.path.basename(panorama_url) if panorama_url else "unknown"
    )

    # Handle relative URLs by prepending base_url if needed
    def make_absolute_url(url: str) -> str:
        if not url:
            return ""
        if url.startswith(("http://", "https://")):
            return url
        if base_url and not url.startswith("/"):
            return base_url + url
        elif base_url:
            return base_url.rstrip("/") + url
        return url

    absolute_panorama = make_absolute_url(panorama_url)
    absolute_thumbnail = make_absolute_url(properties.get("thumbnail", ""))

    return SphereNodePanorama(
        id=node_id,
        gps=gps,
        panorama=absolute_panorama,  # Let the model handle URL resolution
        thumbnail=absolute_thumbnail or None,  # Optional: not every source has one
        links=[],  # Will be populated later if needed
        # The Living Ice Project credits the photographer as "artist"
        author=properties.get("author") or properties.get("artist") or None,
        date=properties.get("date"),
        project=properties.get("project"),
        label=properties.get("label"),
        base_url=base_url,  # Pass base URL for relative URL resolution
    )


def shared_cache_get(key: str):
    """Read a JSON value from the shared cache; any failure is a miss."""
    try:
        backend = get_cache_backend()
        raw = backend.get(key) if backend is not None else None
        return json.loads(raw) if raw else None
    except Exception as e:
        logger.warning(f"Shared cache read failed for {key}: {e}")
        return None


def shared_cache_set(key: str, value, ttl: int) -> None:
    """Write a JSON value to the shared cache; failures are only logged."""
    try:
        backend = get_cache_backend()
        if backend is not None:
            backend.setex(key, ttl, json.dumps(value))
    except Exception as e:
        logger.warning(f"Shared cache write failed for {key}: {e}")


async def fetch_zenodo_metadata(client: httpx.AsyncClient, doi: str) -> Dict:
    """Return title, author and license of a Zenodo record (shared cache, 24h).

    Failures are not cached and give an empty dict, so spheres stay usable
    without their credits when Zenodo is unreachable.
    """
    cache_key = DOI_METADATA_CACHE_KEY.format(doi=doi)
    cached = shared_cache_get(cache_key)
    if cached:
        return cached

    try:
        response = await client.get(ZENODO_RECORD_URL.format(doi=doi))
        response.raise_for_status()
        metadata = response.json().get("metadata", {})
    except Exception as e:
        logger.warning(f"Failed to fetch Zenodo metadata for DOI {doi}: {e}")
        return {}

    creators = [c.get("name") for c in metadata.get("creators", []) if c.get("name")]
    license_info = metadata.get("license") or {}
    result = {
        "label": metadata.get("title"),
        "author": "; ".join(creators) or None,
        "license": license_info.get("id"),
    }
    shared_cache_set(cache_key, result, DOI_METADATA_TTL)
    return result


async def fetch_dois_metadata(dois: Set[str]) -> Dict[str, Dict]:
    """Fetch the Zenodo metadata of each distinct DOI once, concurrently."""
    if not dois:
        return {}
    ordered = sorted(dois)
    async with httpx.AsyncClient(timeout=10.0) as client:
        results = await asyncio.gather(
            *(fetch_zenodo_metadata(client, doi) for doi in ordered)
        )
    return dict(zip(ordered, results))


def parse_svalbox_feature(
    feature: Dict, doi_metadata: Optional[Dict[str, Dict]] = None
) -> SphereNodePanorama:
    """Convert a Svalbox WFS feature to a SphereNodePanorama.

    Only whitelisted properties are read. The WFS `file` property (a local
    path with a user name) is deliberately never touched.
    """
    properties = feature.get("properties") or {}
    coordinates = (feature.get("geometry") or {}).get("coordinates") or []
    if len(coordinates) < 2:
        raise ValueError("Svalbox feature has no valid coordinates")
    gps = [coordinates[0], coordinates[1]]
    if len(coordinates) >= 3 and coordinates[2] is not None:
        gps.append(coordinates[2])

    uid = properties.get("uid")
    if not uid:
        raise ValueError("Svalbox feature has no uid")

    doi = str(properties["doi"]) if properties.get("doi") else None
    credits = (doi_metadata or {}).get(doi, {}) if doi else {}

    return SphereNodePanorama(
        id=f"{SVALBOX_ID_PREFIX}{uid}",
        gps=gps,
        panorama=properties.get("api_link"),
        links=[],
        author=credits.get("author"),
        date=properties.get("datetime"),
        project=SVALBOX_PROJECT,
        label=credits.get("label") or SVALBOX_DEFAULT_LABEL,
        license=credits.get("license"),
        doi=ZENODO_DOI_URL.format(doi=doi) if doi else None,
    )


def keep_latest_per_spot(
    nodes: List[SphereNodePanorama], radius_m: float = SVALBOX_DEDUPE_RADIUS_M
) -> List[SphereNodePanorama]:
    """Among nodes within radius_m of each other, keep only the most recent one.

    Nodes without a date lose against dated ones. Input order breaks ties.
    """
    # Newest first, so the first node of a spot is the one we keep
    ranked = sorted(
        nodes,
        key=lambda n: (n.date is not None, n.date.timestamp() if n.date else 0.0),
        reverse=True,
    )
    lat_window = radius_m / 111_000  # degrees of latitude, cheap prefilter
    kept: List[SphereNodePanorama] = []
    for node in ranked:
        lon, lat = node.gps[0], node.gps[1]
        duplicate = any(
            abs(k.gps[1] - lat) <= lat_window
            and SpatialIndex._haversine_distance(lon, lat, k.gps[0], k.gps[1])
            <= radius_m
            for k in kept
        )
        if not duplicate:
            kept.append(node)
    return kept


async def load_lip_nodes(
    project_name: str, project_config: Dict
) -> List[SphereNodePanorama]:
    """Load the nodes of a project served as a LIP-style GeoJSON."""
    base_url = project_config.get("base_url", "")
    geojson_data = await fetch_geojson_from_url(project_config["geojson_url"])

    nodes = []
    if geojson_data.get("type") == "FeatureCollection":
        for feature in geojson_data.get("features", []):
            try:
                node = parse_geojson_feature_to_sphere_node(feature, base_url)
                # Set the project if not already set in the feature
                if not node.project:
                    node.project = project_name
                nodes.append(node)
            except Exception as e:
                logger.error(f"Failed to parse feature in {project_name}: {e}")
    return nodes


async def load_svalbox_nodes(
    project_name: str, project_config: Dict
) -> List[SphereNodePanorama]:
    """Load Svalbox photo spheres, credited from Zenodo, one per spot."""
    geojson_data = await fetch_geojson_from_url(project_config["geojson_url"])
    features = geojson_data.get("features", [])

    dois = {
        str(f["properties"]["doi"])
        for f in features
        if (f.get("properties") or {}).get("doi")
    }
    doi_metadata = await fetch_dois_metadata(dois)

    nodes = []
    for feature in features:
        try:
            nodes.append(parse_svalbox_feature(feature, doi_metadata))
        except Exception as e:
            logger.error(f"Failed to parse feature in {project_name}: {e}")

    unique_nodes = keep_latest_per_spot(nodes)
    logger.info(
        f"{project_name}: kept {len(unique_nodes)} of {len(nodes)} spheres "
        f"(most recent per spot)"
    )
    return unique_nodes


PROJECT_LOADERS = {"lip": load_lip_nodes, "svalbox": load_svalbox_nodes}


async def load_project_nodes(
    project_name: str, project_config: Dict
) -> List[SphereNodePanorama]:
    """Load a project's nodes, through the shared cache when it has them."""
    cache_key = PROJECT_NODES_CACHE_KEY.format(project=project_name)
    cached = shared_cache_get(cache_key)
    if cached is not None:
        try:
            nodes = [SphereNodePanorama.model_validate(n) for n in cached]
            logger.info(f"{project_name}: {len(nodes)} spheres from the shared cache")
            return nodes
        except Exception as e:
            logger.warning(f"Ignoring invalid cached spheres for {project_name}: {e}")

    loader = PROJECT_LOADERS[project_config.get("type", "lip")]
    nodes = await loader(project_name, project_config)
    if nodes:
        shared_cache_set(
            cache_key, [n.model_dump(mode="json") for n in nodes], PROJECT_NODES_TTL
        )
    return nodes


async def get_all_sphere_nodes() -> List[SphereNodePanorama]:
    """Fetch and parse all sphere nodes from all projects."""
    all_nodes = []

    for project_name, project_config in SphereProjectLinks.items():
        try:
            all_nodes.extend(await load_project_nodes(project_name, project_config))
        except Exception as e:
            logger.error(f"Failed to process project {project_name}: {e}")
            continue

    return all_nodes


async def ensure_data_loaded() -> List[SphereNodePanorama]:
    """Ensure all sphere data is loaded and indexed."""
    if _spatial_index:
        return list(_spatial_index.values())

    async with _load_lock:
        # Another task may have finished the load while we waited
        if _spatial_index:
            return list(_spatial_index.values())

        nodes = await get_all_sphere_nodes()
        for node in nodes:
            SpatialIndex.add_node(node)

        # CPU bound (N^2): keep it off the event loop
        await asyncio.to_thread(SpatialIndex._compute_distance_and_bearing_matrices)

        logger.info(f"Loaded and indexed {len(nodes)} sphere nodes")
        logger.info(
            f"Computed distance and bearing matrices for {len(_distance_matrix)} nodes"
        )
        return nodes


async def warm_up() -> None:
    """Load the spheres in the background when the server starts."""
    try:
        await ensure_data_loaded()
    except Exception as e:
        logger.error(f"Sphere warm-up failed: {e}")


@router.get("/geojson", response_model=SphereGeojson)
@cache_response(ttl=3600)
async def get_sphere_geojson() -> SphereGeojson:
    """
    Return the GeoJSON of all sphere nodes from all projects to be displayed by Leaflet.

    This endpoint fetches and caches GeoJSON data from configured sphere projects,
    parses the features into SphereNodePanorama objects, and returns them in a
    standardized GeoJSON FeatureCollection format.

    Returns:
        SphereGeojson: A GeoJSON FeatureCollection containing all available sphere nodes
                      with their positions, panorama URLs, and metadata
    """
    nodes = await ensure_data_loaded()
    return SphereGeojson.from_sphere_nodes(nodes)


@router.get("/{node_id}", response_model=SphereNodePanorama)
@cache_response(ttl=360)
async def get_sphere_panorama_and_links(
    node_id: str,
    max_range: float = 10000,
    sectors: int = Query(5, ge=1),
):
    """
    Return the detail of one sphere with neighboring nodes within a distance of
    max_range (default 10000m) from the target sphere.

    The algorithm uses a precomputed distance matrix for efficient neighbor search
    and applies bearing-based filtering to ensure neighbors are well-distributed
    around the target node. For each angular sector (360°/sectors), it selects
    the closest neighbor that maintains a minimum angular separation of
    (360°/sectors)/2 from already selected neighbors.

    Args:

        node_id: The ID of the sphere node to retrieve

        max_range: Maximum distance in meters for neighboring nodes (default: 10000m)

        sectors: Number of angular sectors to divide the 360° view (default: 5)

    Returns:

        SphereNodePanorama: The target node with its panorama, thumbnail, and
                           filtered list of neighboring nodes
    """
    # Ensure data is loaded
    await ensure_data_loaded()

    # Find the target node
    target_node = _spatial_index.get(node_id)
    if not target_node:
        raise HTTPException(
            status_code=404, detail=f"Sphere node with id {node_id} not found"
        )

    # Find neighbors using spatial indexing
    neighbors = SpatialIndex.find_neighbors(target_node, max_range, int(sectors))

    # Create a copy of the target node with neighbors
    result = SphereNodePanorama(
        id=target_node.id,
        gps=target_node.gps,
        panorama=target_node.panorama,
        thumbnail=target_node.thumbnail,
        links=neighbors,
        author=target_node.author,
        date=target_node.date,
        project=target_node.project,
        label=target_node.label,
        license=target_node.license,
        doi=target_node.doi,
    )

    return result
