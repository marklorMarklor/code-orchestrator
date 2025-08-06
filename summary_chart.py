"""Summary chart utilities for the MCP project.

This module encapsulates helper functions to generate descriptive charts
from tabular data.  It provides bar, line and heatmap charts using
matplotlib and seaborn.  The functions are designed to be flexible
while keeping the API simple: pass in a pandas DataFrame along with
the relevant column names, and the chart is saved to disk.  A JSON
file describing the aggregated data can also be produced to feed a
frontend such as a React component.

Functions
---------
* :func:`generate_bar_chart` – count occurrences of values in a column.
* :func:`generate_line_chart` – time series or aggregated value over time.
* :func:`generate_heatmap_chart` – 2D pivot table visualised as a heatmap.

Example
-------

>>> import pandas as pd
>>> from mcp_datagouv.visualizer.summary_chart import generate_bar_chart
>>> df = pd.DataFrame({'commune': ['Paris', 'Lyon', 'Paris', 'Marseille']})
>>> out = generate_bar_chart(df, column='commune', output_path='communes.png')
>>> print(out['image'])
communes.png
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

sns.set_theme(style="whitegrid")


def _ensure_output_dir(path: Path) -> None:
    """Create the parent directory for a file if it does not exist."""
    path.parent.mkdir(parents=True, exist_ok=True)


def generate_bar_chart(
    df: pd.DataFrame,
    *,
    column: str,
    output_path: str = "bar_chart.png",
    topn: Optional[int] = None,
    metadata_json: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a bar chart summarising the distribution of a categorical column.

    Parameters
    ----------
    df : pandas.DataFrame
        Input dataset.
    column : str
        The categorical column to summarise.  A ``ValueError`` is raised if
        the column does not exist in the DataFrame.
    output_path : str, optional
        Path where the PNG image will be saved.  Relative paths are
        interpreted relative to the current working directory.  Defaults
        to ``"bar_chart.png"``.
    topn : int, optional
        If provided, only the top ``n`` most frequent values will be
        plotted.  Others are aggregated into an ``"Other"`` category.
    metadata_json : str, optional
        If provided, a JSON file containing the value counts will be
        written to the given path.

    Returns
    -------
    Dict[str, Any]
        A dictionary containing the keys:

        ``image`` : str
            Path to the saved chart image.
        ``data`` : Dict[str, int]
            A mapping of category labels to counts.
        ``metadata`` : Optional[str]
            Path to the JSON file if ``metadata_json`` was supplied.

    Raises
    ------
    ValueError
        If ``column`` is not present in ``df``.
    """
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not found in DataFrame")

    counts = df[column].value_counts().sort_values(ascending=False)

    if topn is not None and topn > 0 and len(counts) > topn:
        top_counts = counts.iloc[:topn]
        other_count = counts.iloc[topn:].sum()
        counts = top_counts.append(pd.Series({'Other': other_count}))

    # Plot
    plt.figure(figsize=(8, 6))
    ax = sns.barplot(x=counts.index, y=counts.values, palette="deep")
    ax.set_xlabel(column)
    ax.set_ylabel("Count")
    ax.set_title(f"Distribution of {column}")
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()

    output_file = Path(output_path)
    _ensure_output_dir(output_file)
    plt.savefig(output_file)
    plt.close()

    # Optionally write metadata
    metadata_path = None
    if metadata_json is not None:
        metadata_file = Path(metadata_json)
        _ensure_output_dir(metadata_file)
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(counts.to_dict(), f, ensure_ascii=False, indent=2)
        metadata_path = str(metadata_file)

    return {
        "image": str(output_file),
        "data": counts.to_dict(),
        "metadata": metadata_path,
    }


def generate_line_chart(
    df: pd.DataFrame,
    *,
    date_col: str,
    value_col: Optional[str] = None,
    aggfunc: str = "count",
    freq: str = "M",
    output_path: str = "line_chart.png",
    metadata_json: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a line chart over time.

    The DataFrame is resampled on ``date_col`` at the given frequency
    (for example, monthly) using ``aggfunc`` (one of ``"count"`` or
    ``"sum"``).  If ``value_col`` is ``None`` and ``aggfunc`` is
    ``"count"`` the number of rows per period is computed.  Otherwise
    ``aggfunc`` is applied to ``value_col``.

    Parameters
    ----------
    df : pandas.DataFrame
        Input dataset.
    date_col : str
        Name of the datetime column to resample on.
    value_col : str, optional
        Column on which to apply the aggregation.  Ignored if
        ``aggfunc`` is ``"count"``.
    aggfunc : str, optional
        Either ``"count"`` or ``"sum"``.  Determines how the data is
        aggregated.  Defaults to ``"count"``.
    freq : str, optional
        Frequency string passed to ``pandas.Grouper``.  Defaults to
        monthly (``"M"``).
    output_path : str, optional
        Where to save the resulting PNG.  Defaults to ``"line_chart.png"``.
    metadata_json : str, optional
        If provided, write the aggregated data to this JSON file.

    Returns
    -------
    Dict[str, Any]
        Dictionary with keys ``image`` (path to PNG), ``data`` (the
        aggregated series as a mapping), and ``metadata`` (path to
        JSON if written).

    Raises
    ------
    ValueError
        If the specified columns are missing or ``aggfunc`` is invalid.
    """
    if date_col not in df.columns:
        raise ValueError(f"Column '{date_col}' not found in DataFrame")
    if aggfunc not in {"count", "sum"}:
        raise ValueError("aggfunc must be 'count' or 'sum'")
    if aggfunc == "sum" and (value_col is None or value_col not in df.columns):
        raise ValueError("value_col must be provided and exist in DataFrame when aggfunc='sum'")

    data = df.copy()
    data[date_col] = pd.to_datetime(data[date_col])
    if aggfunc == "count":
        series = data.set_index(date_col).resample(freq).size()
    else:  # sum
        series = data.set_index(date_col)[value_col].resample(freq).sum()

    # Plot line chart
    plt.figure(figsize=(8, 6))
    ax = sns.lineplot(x=series.index, y=series.values, marker="o")
    ax.set_xlabel(date_col)
    ylabel = "Count" if aggfunc == "count" else f"Sum of {value_col}"
    ax.set_ylabel(ylabel)
    ax.set_title(f"{ylabel} by {freq}")
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()

    output_file = Path(output_path)
    _ensure_output_dir(output_file)
    plt.savefig(output_file)
    plt.close()

    # Optionally write metadata
    metadata_path = None
    if metadata_json is not None:
        metadata_file = Path(metadata_json)
        _ensure_output_dir(metadata_file)
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump({str(k): v for k, v in series.items()}, f, ensure_ascii=False, indent=2)
        metadata_path = str(metadata_file)

    return {
        "image": str(output_file),
        "data": {str(k): v for k, v in series.items()},
        "metadata": metadata_path,
    }


def generate_heatmap_chart(
    df: pd.DataFrame,
    *,
    index_col: str,
    columns_col: str,
    values_col: str,
    aggfunc: str = "sum",
    output_path: str = "heatmap_chart.png",
    metadata_json: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a heatmap from a pivot of three columns.

    The function constructs a pivot table using ``index_col`` as the
    rows, ``columns_col`` as the columns and applies ``aggfunc`` over
    ``values_col``.  The result is then visualised as a heatmap.

    Parameters
    ----------
    df : pandas.DataFrame
        Input dataset.
    index_col : str
        Column to be used as the rows of the heatmap.
    columns_col : str
        Column to be used as the columns of the heatmap.
    values_col : str
        Column whose values will be aggregated into the heatmap cells.
    aggfunc : str, optional
        Aggregation function, either ``"sum"`` or ``"mean"``.
        Defaults to ``"sum"``.
    output_path : str, optional
        Where to save the heatmap PNG.  Defaults to ``"heatmap_chart.png"``.
    metadata_json : str, optional
        If provided, the pivot table will be written to this JSON file.

    Returns
    -------
    Dict[str, Any]
        Contains the ``image`` path, the pivot table as ``data`` (nested
        mapping), and optionally ``metadata`` path.

    Raises
    ------
    ValueError
        If any of the specified columns are missing or ``aggfunc`` is
        invalid.
    """
    for col in (index_col, columns_col, values_col):
        if col not in df.columns:
            raise ValueError(f"Column '{col}' not found in DataFrame")
    if aggfunc not in {"sum", "mean"}:
        raise ValueError("aggfunc must be 'sum' or 'mean'")

    pivot_table = pd.pivot_table(df, index=index_col, columns=columns_col, values=values_col, aggfunc=aggfunc, fill_value=0)

    plt.figure(figsize=(8, 6))
    ax = sns.heatmap(pivot_table, annot=True, fmt=".2f", cmap="viridis")
    ax.set_title(f"Heatmap of {values_col} ({aggfunc})")
    plt.tight_layout()

    output_file = Path(output_path)
    _ensure_output_dir(output_file)
    plt.savefig(output_file)
    plt.close()

    # Optionally write metadata
    metadata_path = None
    if metadata_json is not None:
        metadata_file = Path(metadata_json)
        _ensure_output_dir(metadata_file)
        # Convert pivot table to nested dict with string keys for JSON
        pivot_dict: Dict[str, Dict[str, Any]] = {str(row): {str(col): val for col, val in pivot_table.loc[row].items()} for row in pivot_table.index}
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(pivot_dict, f, ensure_ascii=False, indent=2)
        metadata_path = str(metadata_file)

    return {
        "image": str(output_file),
        "data": {str(row): {str(col): pivot_table.loc[row, col] for col in pivot_table.columns} for row in pivot_table.index},
        "metadata": metadata_path,
    }
