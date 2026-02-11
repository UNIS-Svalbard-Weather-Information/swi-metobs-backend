from fastapi import HTTPException, APIRouter
import json
from pathlib import Path
from app.models.spheres import SphereGeojson, SphereNodePanorama, SphereNode
from app.utils.error import handle_validation_error
import os

# Get the router from parent
router = APIRouter()

SphereProjectLinks = {
    "The Living Ice Project": os.getenv(
        "SPHERE_LIP_GEOJSON_FETCH",
        "https://livingiceproject.com/static/shapes/spheres.geojson",
    )
}


@router.get("/geojson", response_model=SphereGeojson)
def get_sphere_geojson() -> SphereGeojson:
    """
    Return the GeoJson of all the sphere from all the project to be displayed by Leaflet
    """
    pass


@router.get("/{node_id}", response_model=SphereNodePanorama)
def get_sphere_panorama_and_links(
    node_id: str, max_range: float = 5, sectors: float = 30
) -> SphereNodePanorama:
    """
    Return the detail of one sphere with the neibouring nodes withing a distance of
    max_range of the neibouring sphere and with the closes neibouring sphere for each sectors degree arround the head node
    """
    pass
