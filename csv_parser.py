"""
CSV Parser Module
=================

This module provides a single function, :func:`parse_csv`, to load a comma‑
separated values (CSV) file from a local path into a :class:`pandas.DataFrame`.
The parser is designed to be resilient in the face of common data issues (e.g.,
varying encodings or missing columns) and to surface meaningful exceptions
where automatic recovery is not possible.

The parser does **not** download remote resources itself; if you need to
retrieve a file from a URL you should use the ``downloader`` component
described in the project specification to obtain a local file path before
calling this function.

Example
-------
>>> from csv_parser import parse_csv
>>> df = parse_csv("/path/to/your/file.csv")
>>> print(df.head())

Functions
---------
parse_csv(file_path: str) -> pandas.DataFrame
    Load a CSV file into a DataFrame with sensible defaults and basic error
    handling.

"""

from __future__ import annotations

import os
from typing import Optional, Iterable, Any

import pandas as pd

def _detect_encoding(sample: bytes) -> Optional[str]:
    """Attempt to detect the encoding of a byte sample using the built‑in
    ``codecs`` module.  If detection fails, ``None`` is returned.

    The detection heuristics here are intentionally simple; they only try a
    handful of common encodings.  For more robust detection consider
    installing and using ``chardet`` or ``charset_normalizer``, but those
    libraries are not available in the current environment.

    Parameters
    ----------
    sample: bytes
        A chunk of bytes from the file to inspect.

    Returns
    -------
    Optional[str]
        A guessed encoding name, or ``None`` if no encoding could be
        determined.
    """
    # Try a few common encodings in order of preference.  'utf‑8' is
    # ubiquitous, followed by 'ISO‑8859‑1' (latin1) and 'windows‑1252'.
    candidate_encodings = ["utf-8", "ISO-8859-1", "windows-1252", "utf-16"]
    for enc in candidate_encodings:
        try:
            sample.decode(enc)
        except Exception:
            continue
        else:
            return enc
    return None

def parse_csv(file_path: str, *, delimiter: str = ",", encoding: Optional[str] = None,
              **read_csv_kwargs: Any) -> pd.DataFrame:
    """Parse a CSV file and return a :class:`pandas.DataFrame`.

    This function wraps :func:`pandas.read_csv` with additional logic to
    gracefully handle common issues such as unknown encodings or missing
    files.  It also exposes the most frequently used parameters (delimiter
    and encoding) while allowing arbitrary keyword arguments to be passed
    through to :func:`pandas.read_csv` via ``**read_csv_kwargs``.

    Parameters
    ----------
    file_path : str
        Path to the CSV file on disk.  The file must already exist; remote
        resources should be downloaded using the ``downloader`` module before
        being parsed.
    delimiter : str, optional
        The character that separates columns in the file.  By default
        ``","`` (comma) is used.
    encoding : str, optional
        Name of the character encoding to use when decoding the file.  If
        ``None``, the parser will attempt to detect an encoding based on
        sampling the first few kilobytes of the file.  Supplying an explicit
        encoding is strongly recommended when you know the file's encoding.
    **read_csv_kwargs
        Additional keyword arguments are passed directly to
        :func:`pandas.read_csv`.  This allows you to override default
        behaviours such as specifying column names, data types, or handling
        missing values.

    Returns
    -------
    pandas.DataFrame
        A DataFrame containing the data from the CSV.

    Raises
    ------
    FileNotFoundError
        If ``file_path`` does not point to an existing file.
    UnicodeDecodeError
        If the file cannot be decoded with the detected or provided
        encoding.  Consider specifying ``encoding`` explicitly.
    pandas.errors.EmptyDataError
        If the file is empty.
    pandas.errors.ParserError
        If there is a problem parsing the file (malformed CSV).
    Exception
        Any other unexpected exception raised by :func:`pandas.read_csv` is
        propagated to the caller.

    Notes
    -----
    - The caller is responsible for verifying that the returned DataFrame
      contains the expected columns and data types.  If required columns
      are missing, a ``KeyError`` may occur later in the processing pipeline.
    - Only a small set of encodings are auto‑detected.  If your file uses
      another encoding, set ``encoding`` explicitly.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"CSV file not found: {file_path}")

    # Read a small sample to guess encoding if none provided
    # Only attempt detection on binary (non‑text) file.
    if encoding is None:
        with open(file_path, 'rb') as f:
            sample = f.read(4096)
        encoding = _detect_encoding(sample) or 'utf-8'

    try:
        df = pd.read_csv(
            file_path,
            sep=delimiter,
            encoding=encoding,
            **read_csv_kwargs
        )
    except UnicodeDecodeError:
        # Re‑attempt with 'latin1' as a common fallback if auto detection fails
        if encoding.lower() != 'iso-8859-1':
            try:
                df = pd.read_csv(
                    file_path,
                    sep=delimiter,
                    encoding='ISO-8859-1',
                    **read_csv_kwargs
                )
            except Exception:
                # Reraise the original decode error
                raise
        else:
            raise
    return df
