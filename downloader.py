"""Utilities for downloading and inspecting resources from data.gouv.fr.

The functions in this module provide a straightforward way to fetch a
file by URL, store it on disk in a temporary location and infer its
format based on the URL, HTTP headers and, where necessary, the
contents of the file itself.  The goal is to provide the downstream
parsers with a local path and a best-effort guess of the file type
without placing strict constraints on the resource.  When dealing
with compressed archives (ZIP, GZip) the downloader will attempt to
extract the contained file if there is exactly one candidate; for
archives containing multiple files it will leave the archive intact
and return the archive's path.

Examples
--------
>>> from mcp_datagouv.downloader import download
>>> result = download("https://example.com/data.csv")
>>> result["format"]
'csv'
>>> result["path"]  # doctest: +ELLIPSIS
'.../data.csv'

Note
----
The downloader does not attempt to perform content validation beyond
basic format detection.  Consumers of the downloaded file should
validate its contents before relying on the data.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter, Retry

# Configure module level logger
logger = logging.getLogger(__name__)


def _create_session(retries: int = 3, backoff_factor: float = 0.5) -> requests.Session:
    """Create a requests session with retry logic suitable for downloads."""
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": "mcp_datagouv/0.1 (AgentAPIFetch) downloader"})
    return session


def _infer_extension_from_content_type(content_type: Optional[str]) -> Optional[str]:
    """Guess a file extension given a MIME content type.

    Returns the extension including the leading dot if recognised,
    otherwise None.  Common types not in the standard `mimetypes`
    database are handled explicitly.
    """
    if not content_type:
        return None
    content_type = content_type.split(";")[0].strip().lower()
    # Common non-standard types used by data.gouv.fr
    overrides = {
        "application/geo+json": ".geojson",
        "application/vnd.geo+json": ".geojson",
        "application/json": ".json",
        "application/ld+json": ".json",
        "text/csv": ".csv",
        "text/plain": ".txt",
    }
    if content_type in overrides:
        return overrides[content_type]
    return mimetypes.guess_extension(content_type) or None


def _detect_format(path: Path) -> str:
    """Return a simplified format string based on the file extension.

    The returned format is lowercased without leading dots.  If no
    obvious format can be determined it defaults to 'unknown'.
    """
    suffix = path.suffix.lower()
    if not suffix:
        return "unknown"
    # Normalise certain extensions
    mapping = {
        ".geojson": "geojson",
        ".json": "json",
        ".csv": "csv",
        ".txt": "txt",
        ".xml": "xml",
        ".xls": "xls",
        ".xlsx": "xlsx",
        ".tsv": "tsv",
        ".zip": "zip",
        ".gz": "gz",
    }
    return mapping.get(suffix, suffix.lstrip("."))


def download(url: str, dest_dir: Optional[str] = None) -> Dict[str, str]:
    """Download a resource from ``url`` to a local temporary file.

    Parameters
    ----------
    url : str
        The absolute URL of the file to download.
    dest_dir : str, optional
        Directory into which the file will be saved.  If omitted a
        temporary directory is created and returned as part of the
        path.

    Returns
    -------
    dict with keys ``path`` and ``format``
        ``path`` is the absolute filesystem path of the downloaded
        (and possibly extracted) file.  ``format`` is a best guess at
        the file's format such as ``csv``, ``json``, ``geojson`` or
        ``zip``.  If the resource is a compressed archive containing
        multiple files the archive will be returned and the format
        reflects its container type.

    Raises
    ------
    ValueError
        If ``url`` is falsy or not a valid HTTP URL.
    RuntimeError
        If a network error prevents the file from being downloaded
        after the configured number of retries.
    """
    if not url or not isinstance(url, str):
        raise ValueError("A valid URL must be provided")
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"Unsupported URL scheme for download: {url}")

    session = _create_session()
    try:
        logger.debug("Fetching %s", url)
        response = session.get(url, stream=True, timeout=15)
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed to download {url}: {exc}") from exc

    if response.status_code >= 400:
        raise RuntimeError(f"Failed to download {url}: HTTP {response.status_code}")

    # Determine target directory and ensure it exists
    if dest_dir is None:
        dest_dir = tempfile.mkdtemp(prefix="mcp_dg_dl_")
    else:
        os.makedirs(dest_dir, exist_ok=True)
    dest_path = Path(dest_dir)

    # Determine filename and extension.  Start with the URL's path.
    filename = os.path.basename(re.sub(r"\?.*$", "", url))  # strip query parameters
    name, ext = os.path.splitext(filename)
    if not ext:
        # Try to infer from Content-Type header
        ext = _infer_extension_from_content_type(response.headers.get("Content-Type")) or ""
        filename = f"{name}{ext}"
    # If we still don't have a name, fall back to a generic one
    if not name:
        name = "download"
        filename = f"{name}{ext}"

    file_path = dest_path / filename
    # Write to disk in chunks to avoid excessive memory usage
    try:
        with open(file_path, "wb") as fh:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:  # filter out keep-alive chunks
                    fh.write(chunk)
    except Exception as exc:
        # Clean up partially downloaded file
        if file_path.exists():
            try:
                file_path.unlink()
            except OSError:
                pass
        raise RuntimeError(f"Error writing to {file_path}: {exc}") from exc

    # Optionally extract compressed archives containing exactly one file
    fmt = _detect_format(file_path)
    # For gzip, attempt to decompress a single-member archive
    if fmt in {"gz", "gzip"}:
        import gzip
        try:
            with gzip.open(file_path, "rb") as gz:
                inner_name = os.path.splitext(filename)[0]
                inner_path = dest_path / inner_name
                with open(inner_path, "wb") as out_fh:
                    shutil.copyfileobj(gz, out_fh)
            # Remove the outer gz file
            file_path.unlink()
            file_path = inner_path
            fmt = _detect_format(file_path)
        except Exception as exc:
            logger.warning("Failed to extract gzip archive %s: %s", file_path, exc)
            # Keep the original file and treat as gzip
            fmt = "gz"
    # For zip archives, extract only if a single file is present
    elif fmt == "zip":
        import zipfile
        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                namelist = [n for n in zf.namelist() if not n.endswith("/")]
                if len(namelist) == 1:
                    inner_name = namelist[0]
                    extracted_path = dest_path / Path(inner_name).name
                    with zf.open(inner_name) as in_fh, open(extracted_path, "wb") as out_fh:
                        shutil.copyfileobj(in_fh, out_fh)
                    file_path.unlink()
                    file_path = extracted_path
                    fmt = _detect_format(file_path)
        except Exception as exc:
            logger.warning("Failed to handle zip archive %s: %s", file_path, exc)
            # Keep the zip as is

    return {"path": str(file_path), "format": fmt}


__all__ = ["download"]
