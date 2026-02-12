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

# Get the router from parent
router = APIRouter()

# Configure logging
logger = logging.getLogger(__name__)

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
    def find_neighbors(
        target_node: SphereNodePanorama, max_range: float, sectors: int
    ) -> List[SphereNode]:
        """Find neighboring nodes using spatial indexing."""
        if len(target_node.gps) < 2:
            return []

        target_lon, target_lat = target_node.gps[0], target_node.gps[1]
        target_grid = SpatialIndex._get_grid_key(target_lon, target_lat)

        # Get all candidate nodes from nearby grid cells
        candidate_ids = set()

        # Check the target grid and surrounding grids
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                check_grid = (
                    target_grid[0] + dx * GRID_SIZE,
                    target_grid[1] + dy * GRID_SIZE,
                )
                if check_grid in _position_grid:
                    candidate_ids.update(_position_grid[check_grid])

        # Filter candidates by distance and organize by sector
        neighbors_by_sector = defaultdict(list)

        for node_id in candidate_ids:
            if node_id == target_node.id:
                continue  # Skip self

            candidate = _spatial_index.get(node_id)
            if candidate and len(candidate.gps) >= 2:
                distance = SpatialIndex._haversine_distance(
                    target_lon, target_lat, candidate.gps[0], candidate.gps[1]
                )

                if distance <= max_range:
                    # Calculate sector for this neighbor
                    bearing = SpatialIndex._calculate_bearing(
                        target_lon, target_lat, candidate.gps[0], candidate.gps[1]
                    )
                    sector = int(bearing / (360.0 / sectors)) % sectors

                    neighbors_by_sector[sector].append((distance, candidate))

        # For each sector, keep only the closest neighbor
        result_nodes = []
        for sector, neighbors in neighbors_by_sector.items():
            if neighbors:
                # Sort by distance and take the closest
                closest = min(neighbors, key=lambda x: x[0])[1]

                # Convert to SphereNode (without panorama/thumbnail data)
                result_nodes.append(SphereNode(id=closest.id, gps=closest.gps))

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
        logger.info(f"Loaded and indexed {len(nodes)} sphere nodes")
        return nodes
    return list(_spatial_index.values())


@router.get("/geojson", response_model=SphereGeojson)
async def get_sphere_geojson() -> SphereGeojson:
    """
    Return the GeoJson of all the sphere from all the project to be displayed by Leaflet
    """
    nodes = await ensure_data_loaded()
    return SphereGeojson.from_sphere_nodes(nodes)


@router.get("/{node_id}", response_model=SphereNodePanorama)
async def get_sphere_panorama_and_links(
    node_id: str, max_range: float = 5, sectors: float = 30
) -> SphereNodePanorama:
    """
    Return the detail of one sphere with the neibouring nodes withing a distance of
    max_range of the neibouring sphere and with the closes neibouring sphere for each sectors degree arround the head node
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
