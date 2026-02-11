from pydantic import BaseModel, conlist, field_validator, HttpUrl
from datetime import datetime
from typing import List, Optional


class SphereNode(BaseModel):
    id: str
    gps: conlist(float, min_length=2, max_length=3)

    @field_validator("gps")
    def validate_hours(cls, v: list) -> list:
        """Ensure than lat and lon are in reasonable range"""
        assert -180 <= v[0] <= 180
        assert -90 <= v[1] <= 90
        if len(v) == 3:
            assert v[2] < 10000
        return v


class SphereNodePanorama(SphereNode):
    panorama: HttpUrl
    thumbnail: HttpUrl
    links: list[SphereNode]
    author: Optional[str] = None
    date: Optional[datetime] = None
    project: Optional[str] = None
    label: Optional[str] = None

    @field_validator("panorama", "thumbnail")
    def validate_image_url(cls, value: HttpUrl) -> HttpUrl:
        valid_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
        if not any(value.lower().endswith(ext) for ext in valid_extensions):
            raise ValueError(
                f"URL must point to an image file with a valid extension: {valid_extensions}"
            )
        return value


class Geometry(BaseModel):
    type: str = "Point"
    coordinates: conlist(float, min_length=2, max_length=3)


class Properties(BaseModel):
    id: str
    panorama: Optional[HttpUrl] = None
    thumbnail: Optional[HttpUrl] = None
    author: Optional[str] = None
    date: Optional[datetime] = None
    project: Optional[str] = None
    label: Optional[str] = None


class Feature(BaseModel):
    type: str = "Feature"
    properties: Properties
    geometry: Geometry


class SphereGeojson(BaseModel):
    type: str = "FeatureCollection"
    features: List[Feature]

    @classmethod
    def from_sphere_nodes(cls, nodes: List[SphereNodePanorama]):
        features = []
        for node in nodes:
            properties = Properties(
                id=node.id,
                panorama=node.panorama,
                thumbnail=node.thumbnail,
                author=node.author,
                date=node.date,
                project=node.project,
                label=node.label,
            )
            geometry = Geometry(coordinates=node.gps)
            feature = Feature(properties=properties, geometry=geometry)
            features.append(feature)
        return cls(features=features)
