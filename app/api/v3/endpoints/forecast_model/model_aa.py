from typing import List
import threading
import atexit
from functools import lru_cache

from app.api.v3.endpoints.forecast_model.model import (
    WeatherModel,
    compute_wind_direction,
    compute_wind_speed,
    _select_variables,
    update_history,
)
from app.models.stations import StationTimeseries

from metpy.calc import (
    relative_humidity_from_specific_humidity,
    dewpoint_from_specific_humidity,
)

# from metpy.units import units
from pyproj import CRS, Transformer

import xarray as xr
from datetime import datetime, timedelta
import numpy as np

from loguru import logger


class ModelAromeArctic(WeatherModel):
    name = "Arome Arctic"
    provider = "Norwegian Meteorological Institute"
    resolution = 2500  # in meters
    projection = {
        "grid_mapping_name": "lambert_conformal_conic",
        "standard_parallel": [77.5, 77.5],
        "longitude_of_central_meridian": -25.0,
        "latitude_of_projection_origin": 77.5,
        "earth_radius": 6371000.0,
        "proj4": "+proj=lcc +lat_0=77.5 +lon_0=-25 +lat_1=77.5 +lat_2=77.5 +no_defs +R=6.371e+06",
        "origin": {"x": 278620.94, "y": -897985.7},
    }
    variables_surface = {
        "air_temperature_2m": {
            "unit": "degC",
            "description": "Temperature at 2 meters",
            "model_variable": ["air_temperature_2m"],
            "function": lambda x, *args, **kwargs: x,
        },
        "wind_speed_10m": {
            "unit": "m/s",
            "description": "Wind speed at 10 meters",
            "model_variable": ["wind_speed"],
            "function": lambda x, *args, **kwargs: x,
        },
        "wind_direction_10m": {
            "unit": "degrees",
            "description": "Wind direction at 10 meters",
            "model_variable": ["wind_direction"],
            "function": lambda x, *args, **kwargs: x,
        },
        "surface_pressure": {
            "unit": "hPa",
            "description": "Surface pressure",
            "model_variable": ["surface_air_pressure"],
            "function": lambda x, *args, **kwargs: x,
        },
    }
    variables_profile = {
        "air_temperature": {
            "unit": "degC",
            "description": "Temperature profile",
            "model_variable": ["air_temperature_ml"],
            "function": lambda x, *args, **kwargs: x,
        },
        "wind_speed": {
            "unit": "m/s",
            "description": "Wind speed profile",
            "model_variable": ["x_wind_ml", "y_wind_ml"],
            "function": compute_wind_speed,
        },
        "wind_direction": {
            "unit": "degrees",
            "description": "Wind direction profile",
            "model_variable": ["x_wind_ml", "y_wind_ml"],
            "function": compute_wind_direction,
        },
        "dew_point_temperature": {
            "unit": "degC",
            "description": "Dew point temperature profile",
            "model_variable": [
                "air_pressure_ml",
                "air_temperature_ml",
                "specific_humidity_ml",
            ],
            "function": lambda p, t, q, *args, **kwargs: (
                dewpoint_from_specific_humidity(p, t, q)
            ),
        },
        "relative_humidity": {
            "unit": "%",
            "description": "Relative humidity profile",
            "model_variable": [
                "air_pressure_ml",
                "air_temperature_ml",
                "specific_humidity_ml",
            ],
            "function": lambda p, t, q, *args, **kwargs: (
                relative_humidity_from_specific_humidity(p, t, q)
            ),
        },
        "specific_humidity": {
            "unit": "kg/kg",
            "description": "Specific humidity profile",
            "model_variable": ["specific_humidity_ml"],
            "function": lambda x, *args, **kwargs: x,
        },
    }

    latitude: float = None
    longitude: float = None
    x: float = None
    y: float = None
    time: datetime = None

    ds: xr.Dataset = None  # Placeholder for the dataset, to be loaded when needed
    ds_selected: List[str] = None

    def __init__(self, longitude: float, latitude: float, time: datetime):
        self.longitude = longitude
        self.latitude = latitude
        self.time = time

        x, y = self._get_xy_from_latlon(self.latitude, self.longitude)
        x, y = self._get_close_from_xy(x, y)
        logger.debug(
            f"Converted lat/lon to x/y: ({self.latitude}, {self.longitude}) -> ({x}, {y})"
        )

        self.x = x
        self.y = y

    def get_profile(self, variable: List[str]) -> StationTimeseries:

        variables_download = _select_variables(variable, self.variables_profile)
        variable_hybrid_to_elevation = [
            "air_temperature_ml",
            "surface_air_pressure",
            "air_pressure_ml",
            "air_temperature_0m",
        ]

        variables_download = variables_download + [
            v for v in variable_hybrid_to_elevation if v not in variables_download
        ]

        ds = self._get_ds(variables_download)
        ds = self._project_hybrid_pressure_levels(ds)
        ds = self._compute_variable_functions(ds, variable)

        return ds[variable + ["z"]]

    def get_surface(self, variable: List[str]) -> StationTimeseries:
        variables_download = _select_variables(variable, self.variables_surface)

        ds = self._get_ds(variables_download)
        ds = self._compute_variable_functions(ds, variable)

        return ds[variable]

    ####################################################################
    ####################################################################
    # Internal helper methods for coordinate transformation and dataset handling

    def _get_xy_from_latlon(self, lat: float, lon: float):
        """
        Convert latitude and longitude to x/y coordinates based on the Lambert Conformal Conic projection.

        Parameters:
        lat (float): Latitude in degrees
        lon (float): Longitude in degrees

        Returns:
        tuple: (x, y) coordinates in meters
        """
        model_crs = CRS.from_proj4(self.projection["proj4"])
        latlon_crs = CRS.from_epsg(4326)  # WGS84 coordinate system
        transformer = Transformer.from_crs(latlon_crs, model_crs, always_xy=True)
        x, y = transformer.transform(lon, lat)
        return x, y

    def _get_close_from_xy(self, x: float, y: float):
        """
        Given x and y coordinates, find the closest grid point coordinates based on the model's resolution and origin.
        """
        origin_x = self.projection["origin"]["x"]
        origin_y = self.projection["origin"]["y"]
        resolution = self.resolution  # 2.5 km resolution

        nx = int((x - origin_x) / resolution)
        ny = int((y - origin_y) / resolution)

        x = origin_x + nx * resolution
        y = origin_y + ny * resolution

        return x, y

    def _get_ds(self, variables: List[str]):
        vars = set(variables)
        if "air_pressure_ml" in vars:
            vars.remove("air_pressure_ml")
            vars.update(["ap", "b", "surface_air_pressure"])

        logger.debug(
            f"Fetching dataset subset for variables: {vars} at x={self.x}, y={self.y}, time={self.time}"
        )

        ds = ModelAromeArcticConnector().get_subset(
            x=self.x, y=self.y, time=self.time, variables=frozenset(vars)
        )

        # This code is from the UNISACSI by Lukas Frank (MIT License)
        if "air_pressure_ml" in variables:
            ap, b, sp = xr.broadcast(ds["ap"], ds["b"], ds["surface_air_pressure"])
            ds["air_pressure_ml"] = ap + b * sp

        return update_history(
            ds, "Fetched dataset subset for variables: " + ", ".join(vars)
        )

    def _project_hybrid_pressure_levels(self, ds: xr.Dataset) -> xr.Dataset:
        """
        Reproject the hybrid pressure levels to elevation coordinates.
        """
        if "air_pressure_ml" not in ds:
            raise ValueError(
                "Surface air pressure (air_pressure_ml) is required for reprojection."
            )

        ds["z"] = xr.zeros_like(ds["air_pressure_ml"])
        ds["z"].attrs = {
            "units": "m",
            "long_name": "Height above mean sea level",
            "standard_name": "altitude",
        }

        for c, n in enumerate(range(1, len(ds["hybrid"]) + 1)):
            if c == 0:
                p_d = ds["surface_air_pressure"] / ds["air_pressure_ml"].isel(hybrid=-n)
                Tm = 0.5 * (
                    ds["air_temperature_0m"] + ds["air_temperature_ml"].isel(hybrid=-n)
                )
            else:
                p_d = ds["air_pressure_ml"].isel(hybrid=-n + 1) / ds[
                    "air_pressure_ml"
                ].isel(hybrid=-n)
                Tm = 0.5 * (
                    ds["air_temperature_ml"].isel(hybrid=-n + 1)
                    + ds["air_temperature_ml"].isel(hybrid=-n)
                )
            ds["z"][dict(hybrid=-n)] = ds["z"].isel(
                hybrid=-n + 1
            ) + 287.0 * Tm / 9.81 * np.log(p_d)

        return update_history(
            ds, "Compute the z coordinate from hybrid pressure levels"
        )

    def _compute_variable_functions(
        self, ds: xr.Dataset, variables: List[str]
    ) -> xr.Dataset:
        for var in variables:
            if (
                var in self.variables_profile
                and "function" in self.variables_profile[var]
            ):
                var_info = self.variables_profile[var]
            elif (
                var in self.variables_surface
                and "function" in self.variables_surface[var]
            ):
                var_info = self.variables_surface[var]
            else:
                continue  # No function defined for this variable, skip

            func = var_info["function"]
            model_vars = var_info["model_variable"]
            ds[var] = (
                func(
                    *[ds[v].metpy.quantify() for v in model_vars],
                    projection=self.projection,
                    latitude=self.latitude,
                    longitude=self.longitude,
                )
                .metpy.convert_units(var_info["unit"])
                .metpy.dequantify()
            )
            ds[var].attrs["description"] = var_info["description"]

        return update_history(ds, f"Computed variables: {','.join(variables)}")


class ModelAromeArcticConnector:
    _instance = None
    _lock = threading.Lock()
    __endpoint__ = "https://thredds.met.no/thredds/dodsC/aromearcticlatest/archive/arome_arctic_det_2_5km_latest.nc"
    ds: xr.Dataset = None
    _last_used = None
    _inactivity_timeout = timedelta(minutes=5)

    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            with self._lock:
                if not hasattr(self, "_initialized"):
                    atexit.register(self.close)
                    self._initialized = True
                    self._start_inactivity_timer()

    def _start_inactivity_timer(self):
        def timer_callback():
            with self._lock:
                self._check_inactivity()
            self._restart_inactivity_timer()

        self._timer = threading.Timer(
            self._inactivity_timeout.total_seconds(), timer_callback
        )
        self._timer.daemon = True
        self._timer.start()

    def _restart_inactivity_timer(self):
        if hasattr(self, "_timer"):
            self._timer.cancel()
        self._timer = threading.Timer(
            self._inactivity_timeout.total_seconds(), self._timer_callback
        )
        self._timer.daemon = True
        self._timer.start()

    def _timer_callback(self):
        with self._lock:
            self._check_inactivity()
        self._restart_inactivity_timer()

    def _check_inactivity(self):
        now = datetime.now()
        if (
            self.ds is not None
            and self._last_used is not None
            and (now - self._last_used) > self._inactivity_timeout
        ):
            logger.info(
                "Closing ModelAromeArcticConnector dataset due to inactivity..."
            )
            self.close()

    def _open_dataset(self):
        if self.ds is None:
            logger.info("Opening ModelAromeArcticConnector dataset...")
            self.ds = xr.open_dataset(self.__endpoint__)
        self._last_used = datetime.now()
        self._restart_inactivity_timer()

    @lru_cache(maxsize=128)
    def get_subset(
        self, x: float, y: float, time: datetime, variables: frozenset[str]
    ) -> xr.Dataset:
        variables_key = list(variables)
        with self._lock:
            self._check_inactivity()
            self._open_dataset()
            subset = self.ds.sel(time=time, x=x, y=y, method="nearest")[variables_key]
            self._last_used = datetime.now()
            return subset.load()

    def close(self):
        if hasattr(self, "_timer"):
            self._timer.cancel()
        if hasattr(self, "ds") and self.ds is not None:
            self.ds.close()
            self.ds = None
