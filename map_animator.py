"""Map animation utilities for the MCP project.

This module defines functions that take a tabular or geospatial data
set and produce time–based animations of event locations.  In
accordance with the project specification, the main consumer of these
functions is the ``AgentVisualizer`` which is invoked by the
orchestrator when a user asks to visualise how events evolve over
time on a map.

The primary entry point in this module is :func:`create_periodic_animation`
which groups the input by a temporal period (for example, by month)
and builds an animated GIF from a sequence of scatter plot frames.

Dependencies
------------
The implementation deliberately avoids requiring heavy geospatial
libraries such as ``geopandas`` or ``shapely`` because these may not
be available in every environment.  Instead the caller must either
provide explicit latitude and longitude column names or supply a
GeoDataFrame if ``geopandas`` is installed.  If ``geopandas`` is
present at runtime the geometry will be used automatically.  The
animation is assembled using the Pillow library which is already a
dependency of matplotlib.

Example
-------

>>> from mcp_datagouv.visualizer.map_animator import create_periodic_animation
>>> import pandas as pd
>>> df = pd.DataFrame({
...     'date': pd.date_range('2021-01-01', periods=90, freq='D'),
...     'lat': [48.85 + i*0.01 for i in range(90)],
...     'lon': [2.35  + i*0.01 for i in range(90)]
... })
>>> meta = create_periodic_animation(df, datetime_col='date', lat_col='lat', lon_col='lon', period='M')
>>> print(meta['gif'])
mcp_datagouv/visualizer/output/map_animation.gif

"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import matplotlib.pyplot as plt
import pandas as pd
from PIL import Image

# Optional dependency: try to import geopandas for automatic
# extraction of coordinates from a GeoDataFrame.  If geopandas is
# unavailable, the functions will require explicit latitude and
# longitude columns.
try:
    import geopandas as gpd  # type: ignore
except ImportError:  # pragma: no cover - geopandas might not be installed
    gpd = None  # type: ignore


def _extract_coordinates(df: pd.DataFrame, lat_col: Optional[str], lon_col: Optional[str]) -> Tuple[pd.Series, pd.Series]:
    """Return latitude and longitude series for plotting.

    If ``lat_col`` and ``lon_col`` are provided they are used directly.  If
    both are ``None`` and ``geopandas`` is installed and ``df`` is a
    ``GeoDataFrame``, the geometry attribute will be queried for point
    coordinates.  An exception is raised otherwise.

    Parameters
    ----------
    df : pandas.DataFrame
        The input data structure, potentially a GeoDataFrame.
    lat_col, lon_col : str or None
        Names of the columns containing latitude and longitude values.

    Returns
    -------
    Tuple[pd.Series, pd.Series]
        A pair of series (latitudes, longitudes).

    Raises
    ------
    ValueError
        If neither explicit latitude/longitude columns nor a geometry
        column are available.
    """
    # Use explicit columns if provided
    if lat_col is not None and lon_col is not None:
        if lat_col not in df.columns or lon_col not in df.columns:
            raise ValueError(f"Columns '{lat_col}' and '{lon_col}' not found in DataFrame")
        return df[lat_col].astype(float), df[lon_col].astype(float)

    # Fallback to geometry if geopandas is available
    if gpd is not None and isinstance(df, gpd.GeoDataFrame):
        if df.empty:
            return pd.Series(dtype=float), pd.Series(dtype=float)
        geom = df.geometry
        # Ensure we have point geometries.  Attempt to extract x/y.
        try:
            lat = geom.y.astype(float)
            lon = geom.x.astype(float)
            return lat, lon
        except Exception as exc:  # pragma: no cover - geometry extraction may fail
            raise ValueError(
                "The provided GeoDataFrame does not contain simple point geometries or lacks x/y accessors"
            ) from exc

    # At this point we cannot determine coordinates
    raise ValueError(
        "Cannot extract coordinates: please specify 'lat_col' and 'lon_col' or install geopandas and provide a GeoDataFrame"
    )


def _make_output_directory(output_dir: Path) -> None:
    """Ensure that the given directory exists.

    Parameters
    ----------
    output_dir : Path
        The directory to create if it does not already exist.
    """
    output_dir.mkdir(parents=True, exist_ok=True)


def _save_frames_to_gif(frame_paths: Iterable[Path], gif_path: Path, duration: float = 1.0) -> None:
    """Assemble individual PNG frames into a GIF.

    Uses Pillow's Image API to concatenate images.  The first frame is
    opened and subsequent frames are appended.  The duration parameter
    controls how long each frame is displayed (in milliseconds).

    Parameters
    ----------
    frame_paths : Iterable[Path]
        Sequence of paths to PNG images.  The order of this iterable
        dictates the sequence of frames in the GIF.
    gif_path : Path
        Destination path for the GIF.
    duration : float, optional
        Duration of each frame in seconds.  Defaults to 1 second.
    """
    frames: List[Image.Image] = [Image.open(str(fp)) for fp in frame_paths]
    if not frames:
        raise ValueError("No frames provided to assemble GIF")
    # Convert duration from seconds to milliseconds as required by Pillow
    duration_ms = int(duration * 1000)
    first, *rest = frames
    first.save(
        gif_path,
        save_all=True,
        append_images=rest,
        duration=duration_ms,
        loop=0,
    )


def create_periodic_animation(
    df: pd.DataFrame,
    datetime_col: str,
    *,
    lat_col: Optional[str] = None,
    lon_col: Optional[str] = None,
    period: str = "M",
    output_dir: str = "./output",
    filename: str = "map_animation.gif",
    duration: float = 1.0,
    dpi: int = 150,
) -> Dict[str, object]:
    """Generate an animated map grouping events by a temporal period.

    This function creates a scatter plot for each time slice (month by
    default) and compiles them into an animated GIF.  It also writes a
    JSON metadata file associating each period with its frame file name.

    Parameters
    ----------
    df : pandas.DataFrame
        Input dataset.  Must contain a datetime column specified by
        ``datetime_col``.  If ``lat_col`` and ``lon_col`` are not
        provided, ``df`` must be a GeoDataFrame with point geometries
        and geopandas must be installed.
    datetime_col : str
        Name of the column containing timestamp information.  This column
        will be converted to datetime using ``pandas.to_datetime``.
    lat_col, lon_col : str, optional
        Names of the latitude and longitude columns.  Both must be
        provided if ``geopandas`` is not available.  If omitted and
        ``df`` is a GeoDataFrame, the geometry column is used.
    period : str, optional
        Temporal frequency string (as understood by
        ``pandas.Grouper``) used to group the data.  Default is
        monthly (``"M"``).  Examples include ``"Y"`` for yearly,
        ``"Q"`` for quarterly, etc.
    output_dir : str, optional
        Directory in which to place the generated frames, GIF and
        metadata file.  The directory is created if necessary.  Defaults
        to ``"./output"``.
    filename : str, optional
        Name of the GIF file (without directory).  Defaults to
        ``"map_animation.gif"``.
    duration : float, optional
        Duration (in seconds) of each frame in the final GIF.  Defaults
        to 1.0 second per frame.
    dpi : int, optional
        Resolution for saving the individual frames.  Higher values
        produce larger files.  Defaults to 150.

    Returns
    -------
    Dict[str, object]
        A dictionary containing:

        ``gif`` : str
            Absolute path to the generated GIF.
        ``frames`` : List[str]
            Paths to the individual frame images.
        ``metadata`` : str
            Path to the JSON metadata file.
        ``periods`` : List[str]
            String representations of each period (e.g. ``"2021-01-01"``).

    Raises
    ------
    ValueError
        If the datetime column cannot be parsed or if coordinate
        extraction fails.
    """
    if datetime_col not in df.columns:
        raise ValueError(f"Column '{datetime_col}' not found in DataFrame")

    # Ensure output directory exists
    output_path = Path(output_dir)
    _make_output_directory(output_path)

    # Copy the DataFrame to avoid mutating the caller's data
    data = df.copy()
    # Convert datetime column
    try:
        data[datetime_col] = pd.to_datetime(data[datetime_col])
    except Exception as exc:
        raise ValueError(f"Failed to convert column '{datetime_col}' to datetime") from exc

    # Group by period
    data["__period__"] = data[datetime_col].dt.to_period(period).dt.start_time
    groups = data.groupby("__period__")

    # Extract all coordinates once for computing bounding box
    all_lat, all_lon = _extract_coordinates(data, lat_col, lon_col)
    if all_lat.empty or all_lon.empty:
        raise ValueError("No coordinate data available for plotting")
    margin = 0.02  # Add some margin to bounding box
    lat_min, lat_max = all_lat.min() - margin, all_lat.max() + margin
    lon_min, lon_max = all_lon.min() - margin, all_lon.max() + margin

    frame_paths: List[Path] = []
    period_labels: List[str] = []

    for period_value, group in groups:
        period_str = str(period_value.date() if hasattr(period_value, "date") else period_value)
        period_labels.append(period_str)
        lat, lon = _extract_coordinates(group, lat_col, lon_col)

        fig, ax = plt.subplots(figsize=(8, 6))
        # Plot the scatter points; use a consistent colour across periods
        ax.scatter(lon, lat, c="#1f77b4", alpha=0.75, s=20, edgecolor="black", linewidth=0.2)
        ax.set_xlim(lon_min, lon_max)
        ax.set_ylim(lat_min, lat_max)
        ax.set_title(f"Events for {period_str}")
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.5)

        # Save frame
        frame_file = output_path / f"{period_str.replace(':', '-')}.png"
        fig.tight_layout()
        fig.savefig(frame_file, dpi=dpi)
        plt.close(fig)
        frame_paths.append(frame_file)

    # Assemble GIF
    gif_path = output_path / filename
    _save_frames_to_gif(frame_paths, gif_path, duration)

    # Write metadata JSON
    metadata = {
        "gif": str(gif_path.resolve()),
        "frames": [str(fp.resolve()) for fp in frame_paths],
        "periods": period_labels,
    }
    metadata_path = output_path / f"{Path(filename).stem}_metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    return {
        "gif": str(gif_path.resolve()),
        "frames": [str(fp.resolve()) for fp in frame_paths],
        "metadata": str(metadata_path.resolve()),
        "periods": period_labels,
    }
