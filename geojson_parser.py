"""
GeoJSON Parser Module
=====================

This module defines :func:`parse_geojson`, a helper for loading
GeoJSON files into a :class:`geopandas.GeoDataFrame`.  GeoJSON is a standard
format for representing geographic features with associated properties.  A
GeoDataFrame integrates geographic geometries with tabular data, enabling
powerful spatial analyses and visualisation using the Pandas API alongside
geospatial operations.

Because :mod:`geopandas` is not part of the Python standard library and may
not be installed in all environments, this parser attempts to import it
dynamically.  If GeoPandas (and its dependency :mod:`shapely`) is not
available, the parser will raise an :class:`ImportError` with a clear
message indicating that the user should install the missing packages.  No
fallback to plain :class:`pandas.DataFrame` is provided because many of
the downstream components (e.g., mapping/animation utilities) require a
genuine :class:`geopandas.GeoDataFrame`.

Example
-------
>>> from geojson_parser import parse_geojson
>>> gdf = parse_geojson("/path/to/geo.json")
>>> gdf.plot()  # Visualise the geometry

Functions
---------
parse_geojson(file_path: str) -> geopandas.GeoDataFrame
    Read a GeoJSON file and return a GeoDataFrame with geometry and
    properties.

"""

from __future__ import annotations

import json
import os
from typing import Any, Dict

def parse_geojson(file_path: str):
    """Parse a GeoJSON file into a :class:`geopandas.GeoDataFrame`.

    This function loads a GeoJSON file from disk, verifies that it
    represents a FeatureCollection or a single Feature, and then uses
    :func:`geopandas.GeoDataFrame.from_features` to construct a
    GeoDataFrame.  The resulting GeoDataFrame contains one row per feature
    with columns for each property plus a special ``geometry`` column of
    Shapely objects representing the geometric shape.

    Parameters
    ----------
    file_path : str
        Path to a GeoJSON file on disk.  The file must exist and be
        syntactically valid JSON conforming to the GeoJSON specification.

    Returns
    -------
    geopandas.GeoDataFrame
        A GeoDataFrame containing the properties and geometries from
        the GeoJSON features.

    Raises
    ------
    FileNotFoundError
        If ``file_path`` does not point to an existing file.
    ImportError
        If :mod:`geopandas` (or its dependencies) is not installed.
    json.JSONDecodeError
        If the file is not valid JSON.
    ValueError
        If the JSON does not contain a valid GeoJSON Feature or
        FeatureCollection.

    Notes
    -----
    - This parser does not attempt to coerce arbitrary JSON into a
      GeoDataFrame; the input must be a GeoJSON object with a ``type``
      field of ``"FeatureCollection"`` or ``"Feature"``.
    - The coordinates of the geometries are not reprojected; they remain
      in the coordinate reference system (CRS) specified in the GeoJSON
      (or assume WGS84 if unspecified).  Downstream consumers may
      reproject as necessary.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"GeoJSON file not found: {file_path}")

    # Load the JSON content
    with open(file_path, 'r', encoding='utf-8') as f:
        try:
            data: Dict[str, Any] = json.load(f)
        except json.JSONDecodeError:
            # Propagate JSON errors to caller
            raise

    # Validate GeoJSON structure
    if not isinstance(data, dict) or 'type' not in data:
        raise ValueError("Invalid GeoJSON: top‑level object must be a dict with a 'type' key")
    geo_type = data['type']
    if geo_type == 'FeatureCollection':
        features = data.get('features')
        if not isinstance(features, list):
            raise ValueError("Invalid GeoJSON: 'features' must be a list")
        # If there are no features we return an empty GeoDataFrame with no geometry
        if not features:
            # Late import of geopandas
            try:
                import geopandas as gpd  # type: ignore
            except ImportError as e:
                raise ImportError(
                    "geopandas is required to parse GeoJSON files. Please install geopandas and its"
                    " dependencies (e.g. shapely, fiona)."
                ) from e
            return gpd.GeoDataFrame()
        # Build GeoDataFrame from features
        try:
            import geopandas as gpd  # type: ignore
        except ImportError as e:
            raise ImportError(
                "geopandas is required to parse GeoJSON files. Please install geopandas and its"
                " dependencies (e.g. shapely, fiona)."
            ) from e
        return gpd.GeoDataFrame.from_features(features)
    elif geo_type == 'Feature':
        # Single feature; wrap in a list for from_features
        try:
            import geopandas as gpd  # type: ignore
        except ImportError as e:
            raise ImportError(
                "geopandas is required to parse GeoJSON files. Please install geopandas and its"
                " dependencies (e.g. shapely, fiona)."
            ) from e
        return gpd.GeoDataFrame.from_features([data])
    else:
        raise ValueError(f"Unsupported GeoJSON type '{geo_type}'. Must be 'FeatureCollection' or 'Feature'.")
