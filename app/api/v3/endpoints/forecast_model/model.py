from abc import ABC, abstractmethod
from typing import Dict, Any, List

from app.models.stations import StationTimeseries
from app.version import VERSION as backend_version

from app.utils.function_name import get_function_name

import numpy as np

from metpy.calc import (
    wind_direction,
    wind_speed,
)

from loguru import logger

from datetime import datetime


class WeatherModel(ABC):
    name: str
    provider: str
    resolution: str
    projection: Dict[str, Any]
    variables_surface: Dict[str, Any]
    variables_profile: Dict[str, Any]
    latitude: float = None
    longitude: float = None
    time: datetime = None

    @abstractmethod
    def get_profile(
        self, lat: float, lon: float, time: str, variable: str
    ) -> StationTimeseries:
        """Fetch profile data for a given variable at a specific location and time."""
        pass

    @abstractmethod
    def get_surface(
        self, lat: float, lon: float, time: str, variable: str
    ) -> StationTimeseries:
        """Fetch surface data for a given variable at a specific location and time."""
        pass


def reproject_variable(x, y, projection=None, longitude=None, latitude=None):
    if projection is None or longitude is None or latitude is None:
        logger.warning(
            "Projection or longitude/latitude not provided. Returning original x and y."
        )
        return x, y

    cone = np.sin(np.abs(np.deg2rad(projection["latitude_of_projection_origin"])))
    diffn = projection["longitude_of_central_meridian"] - longitude
    if diffn > 180.0:
        diffn -= 360.0
    elif diffn < -180.0:
        diffn += 360.0
    alpha = np.deg2rad(diffn) * cone
    eastward = x * np.cos(alpha) - y * np.sin(alpha)
    northward = y * np.cos(alpha) + x * np.sin(alpha)

    return eastward, northward


def compute_wind_direction(x, y, projection=None, **kwargs):
    # Implement logic to compute wind direction from x and y wind components
    if projection:
        u, v = reproject_variable(x, y, projection, **kwargs)
    else:
        u, v = x, y
    return wind_direction(u, v)


def compute_wind_speed(x, y, projection=None, **kwargs):
    # Implement logic to compute wind speed from x and y wind components
    if projection:
        u, v = reproject_variable(x, y, projection, **kwargs)
    else:
        u, v = x, y
    return wind_speed(u, v)


def _select_variables(
    variables_selected: List[str], variables_available: dict
) -> List[str]:
    """
    Select the model variables needed for the requested variables.

    Parameters:
    variables_selected (List[str]): List of variable names requested by the user.
    variables_available (dict): Dictionary of available variables in the model, where keys are variable names and values are dictionaries containing 'model_variable' which is a list of model variable names needed for computation.

    Returns:
    List[str]: List of model variable names that need to be fetched from the dataset.
    """
    variables_to_fetch = set()
    for var in variables_selected:
        if var in variables_available:
            model_vars = variables_available[var].get("model_variable", [])
            variables_to_fetch.update(model_vars)
        else:
            logger.warning(f"Requested variable '{var}' is not available in the model.")
            raise ValueError(
                f"Requested variable '{var}' is not available in the model."
            )

    return list(variables_to_fetch)


def update_history(ds, information):
    ds.attrs["history"] = (
        ds.attrs.get("history", "")
        + f"\n{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')} sw-swi-srm_swi-metobs-backend::{get_function_name()} (v{backend_version}) | {information}"
    )
    return ds
