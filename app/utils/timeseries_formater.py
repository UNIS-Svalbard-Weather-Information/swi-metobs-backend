from app.models.stations import StationTimeseries, StationTimeseriesDataPoint

import xarray as xr
import pandas as pd
from itertools import product

from loguru import logger


def format_xarray_to_timeseries(
    ds: xr.Dataset, station_id: str = None
) -> StationTimeseries:

    if not ("z" in ds or "time" in ds):
        raise ValueError(
            "Dataset must contain 'z' or 'time' dimensions for formatting."
        )

    ds = ds.squeeze()

    ts = []

    logger.debug(
        f"{ds.dims} dimensions found in dataset. {ds.data_vars} variables found. {ds.z.dims[0] if 'z' in ds else 'No z dimension'} z dimension found."
    )

    if "time" in ds.dims and "z" in ds:
        iterable_dims = product(ds.time.values, ds[ds.z.dims[0]].values)
        dim_z = ds.z.dims[0]
        dim_time = "time"
    elif "time" in ds.dims and "z" not in ds:
        iterable_dims = product(ds.time.values, [None])
        dim_z = None
        dim_time = "time"
    elif "z" in ds and "time" not in ds.dims and "time" in ds.coords:
        iterable_dims = product([ds.time.values], ds[ds.z.dims[0]].values)
        dim_z = ds.z.dims[0]
        dim_time = None
    elif "time" in ds.coords:
        iterable_dims = product([ds.time.values], [None])
        dim_z = None
        dim_time = None
    else:
        raise ValueError(
            "Dataset must contain 'z' or 'time' dimensions for formatting."
        )

    for t, cz in iterable_dims:
        logger.debug(
            f"type(t): {type(t)} value of t: {t}, type(cz): {type(cz)} value of cz: {cz}"
        )
        data_point = {
            "timestamp": pd.to_datetime(t),
            "location": {
                "lat": round(float(ds.latitude.values), 4),
                "lon": round(float(ds.longitude.values), 4),
            },
        }

        ds_sel = ds

        ds_sel = ds_sel.sel({"time": t}) if dim_time else ds_sel
        ds_sel = ds_sel.sel({dim_z: cz}) if dim_z else ds_sel

        for var in ds_sel.data_vars:
            logger.debug(
                f"Processing variable '{var}' for time '{t}' and z '{cz}' value is {ds_sel[var].values}"
            )
            data_point[var] = round(float(ds_sel[var].values), 3)

        ts.append(StationTimeseriesDataPoint(**data_point))

    return StationTimeseries(
        id=station_id
        if station_id
        else "forecast_model_at_{lat:.0f}_{lon:.0f}".format(
            lat=ds.latitude.values * 1e4, lon=ds.longitude.values * 1e4
        ),
        timeseries=ts,
    )
