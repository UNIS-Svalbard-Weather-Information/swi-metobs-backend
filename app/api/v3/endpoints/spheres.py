from fastapi import HTTPException, APIRouter
import json
from pathlib import Path
from app.models.spheres import SphereGeojson, SphereNodePanorama, SphereNode
from app.utils.error import handle_validation_error
import os
import httpx
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging
import math
from collections import defaultdict
from loguru import logger

# Get the router from parent
router = APIRouter()

SphereProjectLinks = {
    "The Living Ice Project": {
        "geojson_url": os.getenv(
            "SPHERE_LIP_GEOJSON_FETCH",
            "https://livingiceproject.com/static/shapes/spheres.geojson",
        ),
        "base_url": os.getenv("SPHERE_LIP_BASE_URL", "https://livingiceproject.com/"),
    }
}

# Cache for storing fetched GeoJSON data and spatial index
_geojson_cache: Dict[str, Dict] = {}
_cache_timestamp: Dict[str, datetime] = {}
CACHE_TTL = timedelta(hours=1)  # Cache for 1 hour

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
        n = len(node_ids)

        # Initialize matrices
        _distance_matrix = {node_id: {} for node_id in node_ids}
        _bearing_matrix = {node_id: {} for node_id in node_ids}

        # Compute distances and bearings between all pairs
        for i, node_id1 in enumerate(node_ids):
            node1 = _spatial_index[node_id1]
            if len(node1.gps) < 2:
                continue

            lon1, lat1 = node1.gps[0], node1.gps[1]

            for j, node_id2 in enumerate(node_ids):
                if i == j:
                    # Distance to self is 0
                    _distance_matrix[node_id1][node_id2] = 0.0
                    _bearing_matrix[node_id1][node_id2] = 0.0
                    continue

                node2 = _spatial_index[node_id2]
                if len(node2.gps) < 2:
                    continue

                lon2, lat2 = node2.gps[0], node2.gps[1]

                # Compute distance
                distance = SpatialIndex._haversine_distance(lon1, lat1, lon2, lat2)
                _distance_matrix[node_id1][node_id2] = distance

                # Compute bearing
                bearing = SpatialIndex._calculate_bearing(lon1, lat1, lon2, lat2)
                _bearing_matrix[node_id1][node_id2] = bearing

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
        thumbnail=absolute_thumbnail,  # Let the model handle URL resolution
        links=[],  # Will be populated later if needed
        author=properties.get("author"),
        date=properties.get("date"),
        project=properties.get("project"),
        label=properties.get("label"),
        base_url=base_url,  # Pass base URL for relative URL resolution
    )


async def get_all_sphere_nodes() -> List[SphereNodePanorama]:
    """Fetch and parse all sphere nodes from all projects."""
    all_nodes = []

    for project_name, project_config in SphereProjectLinks.items():
        try:
            geojson_url = project_config["geojson_url"]
            base_url = project_config.get("base_url", "")

            geojson_data = await fetch_geojson_from_url(geojson_url)

            if geojson_data.get("type") == "FeatureCollection":
                features = geojson_data.get("features", [])

                for feature in features:
                    try:
                        node = parse_geojson_feature_to_sphere_node(feature, base_url)
                        # Set the project if not already set in the feature
                        if not node.project:
                            node.project = project_name
                        all_nodes.append(node)
                    except Exception as e:
                        logger.error(f"Failed to parse feature in {project_name}: {e}")
                        continue

        except Exception as e:
            logger.error(f"Failed to process project {project_name}: {e}")
            continue

    return all_nodes


async def ensure_data_loaded() -> List[SphereNodePanorama]:
    """Ensure all sphere data is loaded and indexed."""
    if not _spatial_index:
        nodes = await get_all_sphere_nodes()
        for node in nodes:
            SpatialIndex.add_node(node)

        # Compute distance and bearing matrices
        SpatialIndex._compute_distance_and_bearing_matrices()

        logger.info(f"Loaded and indexed {len(nodes)} sphere nodes")
        logger.info(
            f"Computed distance and bearing matrices for {len(_distance_matrix)} nodes"
        )
        return nodes
    return list(_spatial_index.values())


@router.get("/geojson", response_model=SphereGeojson)
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
async def get_sphere_panorama_and_links(
    node_id: str, max_range: float = 10000, sectors: int = 5
) -> SphereNodePanorama:
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
    )

    return result
