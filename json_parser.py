"""
JSON Parser Module
==================

This module exposes a :func:`parse_json` function used to load and analyse
arbitrary JSON documents from a local file path.  Depending on the structure
of the JSON content the function will either return a :class:`pandas.DataFrame`
for tabular data or a native Python object (``list`` or ``dict``) for
non‑tabular structures.

The parser performs a simple structural analysis to decide when to convert
to a DataFrame:

* If the root object is a list of dictionaries (e.g., ``[{"a": 1,
  "b": 2}, {...}]``) it is treated as tabular and converted to a DataFrame.
* If the root object is a dictionary whose values are all lists of the same
  length (e.g., ``{"a": [1, 2], "b": [3, 4]}``) it is also treated as
  tabular.
* In all other cases the original Python object is returned.

Example
-------
>>> from json_parser import parse_json
>>> obj = parse_json("/path/to/data.json")
>>> if isinstance(obj, pd.DataFrame):
...     print("DataFrame loaded with", len(obj), "rows")
... else:
...     print("Loaded JSON object:", type(obj))

Functions
---------
parse_json(file_path: str) -> Union[pandas.DataFrame, list, dict]
    Load a JSON file and return a DataFrame for tabular data or a Python
    structure for nested or free‑form JSON.

"""

from __future__ import annotations

import json
import os
from typing import Any, Union

import pandas as pd

def parse_json(file_path: str) -> Union[pd.DataFrame, list, dict]:
    """Parse a JSON file and return either a DataFrame or a Python object.

    This function loads the contents of a JSON file from ``file_path`` into a
    Python structure using the built‑in :mod:`json` library.  If the loaded
    object has a structure that can be considered tabular (see below) it
    will be converted into a :class:`pandas.DataFrame`.  Otherwise, the
    raw Python object is returned.  The function does not mutate or
    reorder the input data.

    Parameters
    ----------
    file_path : str
        Path to a JSON file on disk.  The file must exist and contain valid
        JSON.  Remote resources should be downloaded via the ``downloader``
        component before being parsed.

    Returns
    -------
    Union[pandas.DataFrame, list, dict]
        A DataFrame if the JSON is tabular, or a Python object (list/dict)
        otherwise.

    Raises
    ------
    FileNotFoundError
        If ``file_path`` does not point to an existing file.
    json.JSONDecodeError
        If the file does not contain valid JSON.
    TypeError
        If the root of the JSON is neither a list nor a dict.

    Notes
    -----
    A JSON is considered *tabular* if it meets one of the following criteria:

    * It is a list where each element is a mapping (``dict``) representing
      a row.  Missing keys are filled with ``NaN`` in the DataFrame.
    * It is a dictionary where every value is a list and all lists have the
      same length.  Keys become column names and values become column
      contents.
    * In all other cases the structure is deemed nested or hierarchical and
      is returned as‑is for further processing by the caller.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"JSON file not found: {file_path}")

    # Load the raw JSON content
    with open(file_path, 'r', encoding='utf-8') as f:
        try:
            data: Any = json.load(f)
        except json.JSONDecodeError:
            # Provide context in the exception message
            raise

    # Determine the type of the root object
    if isinstance(data, list):
        if not data:
            # Empty list yields an empty DataFrame with no columns
            return pd.DataFrame()
        # If the list contains dicts, treat as tabular
        if all(isinstance(row, dict) for row in data):
            return pd.DataFrame(data)
        else:
            # Mixed or non-dict list; return as Python list
            return data
    elif isinstance(data, dict):
        # Check if all values are lists of equal length
        if data:
            if all(isinstance(v, list) for v in data.values()):
                lengths = {len(v) for v in data.values()}
                if len(lengths) == 1:
                    # Convert dict-of-lists to DataFrame
                    return pd.DataFrame(data)
        # Otherwise return the dict unchanged
        return data
    else:
        raise TypeError(
            f"Root element of JSON must be a list or dict, got {type(data).__name__}."
        )
