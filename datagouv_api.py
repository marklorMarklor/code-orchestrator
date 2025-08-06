"""Interface to the data.gouv.fr public API.

The functions and classes defined in this module provide a thin
abstraction over the official API exposed by data.gouv.fr.  They
allow searching for datasets by keyword and inspecting the resources
attached to a dataset.  Network calls are wrapped in a session with
basic retry logic and reasonable timeouts to reduce the likelihood of
transient errors causing the orchestrator to fail.  When an error
does occur, empty lists are returned rather than exceptions being
propagated to the caller – the orchestrator can decide how to
handle missing results.

Examples
--------
>>> from mcp_datagouv.datagouv_api import search_datasets, get_resources
>>> datasets = search_datasets("indices de consommation", limit=3)
>>> for ds in datasets:
...     print(ds["title"], ds["id"])
>>> resources = get_resources(datasets[0]["id"])
>>> for res in resources:
...     print(res["title"], res["format"], res["url"])

Note
----
The API used here is version 2 of data.gouv.fr.  See
https://www.data.gouv.fr/api/2/ for further documentation.  If this
interface changes in the future a minimal effort should be made to
retain backward compatibility for existing callers.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Iterable, List, Optional

import requests
from requests.adapters import HTTPAdapter, Retry

# Configure a module-level logger.  The orchestrator can override
# logging configuration globally if desired.
logger = logging.getLogger(__name__)

API_BASE_URL = "https://www.data.gouv.fr/api/2"


def _create_session(retries: int = 3, backoff_factor: float = 0.5) -> requests.Session:
    """Return a `requests.Session` configured with retry logic.

    Parameters
    ----------
    retries : int
        Total number of retries for failed requests (HTTP errors or
        connection issues).  A small number of retries strikes a
        balance between resiliency and not hammering the API.
    backoff_factor : float
        Factor by which the sleep interval is increased between
        attempts.  See urllib3 Retry documentation for details.

    Returns
    -------
    requests.Session
        A session object pre-configured with retry behaviour.
    """
    session = requests.Session()
    # We choose a conservative retry policy: retry only idempotent GET
    # requests on a set of status codes where a retry makes sense.
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
    # Identify ourselves with a custom User-Agent; some servers will
    # reject requests with the default python-requests agent.
    session.headers.update({"User-Agent": "mcp_datagouv/0.1 (AgentAPIFetch)"})
    return session


class DataGouvAPI:
    """Client for the data.gouv.fr API.

    This class encapsulates a `requests.Session` configured with retry
    logic and exposes methods to search for datasets and list their
    resources.  It is safe to share a single instance across multiple
    calls within the same process.  Each call will perform its own
    error handling and return empty results on failure.
    """

    def __init__(
        self,
        base_url: str = API_BASE_URL,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or _create_session()

    def _request(self, url: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Internal helper to perform a GET request with error handling.

        Parameters
        ----------
        url : str
            Absolute URL to request.  The caller is responsible for
            constructing this properly from `self.base_url`.
        params : dict, optional
            Query parameters to include in the request.

        Returns
        -------
        dict or None
            Parsed JSON response if successful, otherwise None.
        """
        try:
            logger.debug("Requesting URL %s with params %s", url, params)
            response = self.session.get(url, params=params, timeout=10)
            # If a non-200 response occurs we still attempt to parse the JSON
            # because some 4xx errors return useful messages.  However we
            # deliberately do not raise for status so that retries can occur.
            json_data = response.json()
            if response.status_code >= 400:
                logger.warning(
                    "Received HTTP %s for %s: %s", response.status_code, url, json_data
                )
                # For client errors simply return None; the caller will
                # decide whether to retry or abort.  For server errors
                # the Retry adapter will have handled retries already.
                return None
            return json_data
        except requests.exceptions.JSONDecodeError:
            # If the server does not return JSON we cannot proceed.
            logger.error("Non-JSON response received from %s", url)
            return None
        except requests.RequestException as exc:
            logger.error("Request exception for %s: %s", url, exc)
            return None

    def search_datasets(
        self, query: str, limit: int = 10, page: int = 1
    ) -> List[Dict[str, Any]]:
        """Search for datasets matching a free text query.

        Parameters
        ----------
        query : str
            Free text query.  The API performs a full-text search over
            dataset titles, descriptions and tags.  An empty string
            returns recent datasets but is not recommended.
        limit : int, default 10
            Maximum number of datasets to return.  The API will be
            queried for a page of results sized according to this
            limit.  Note that the API returns additional paging
            information which is ignored here.
        page : int, default 1
            Page of results to return.  Useful when retrieving more
            than one page of results.

        Returns
        -------
        list of dict
            Each element is a dictionary representing a dataset.  The
            keys include at least: ``id``, ``title``, ``slug``,
            ``description``, ``resources_link`` (URL to list resources).
            Additional keys from the API are preserved.
        """
        if not query:
            # If the caller passes an empty query we still attempt a
            # request but log a warning.  The API will return latest
            # datasets by default.
            logger.info("Empty search query submitted to search_datasets")
        url = f"{self.base_url}/datasets/"
        params = {"q": query, "page": page, "page_size": limit}
        json_data = self._request(url, params=params)
        if not json_data or "data" not in json_data:
            return []
        datasets = []
        for item in json_data.get("data", []):
            # The API includes a 'resources' key which is a dict
            # containing an API link to list the resources.  We expose
            # it under a clearer name.
            resources_link = None
            if isinstance(item.get("resources"), dict):
                resources_link = item["resources"].get("href")
            dataset_record = {
                **item,
                "resources_link": resources_link,
            }
            datasets.append(dataset_record)
        return datasets

    def get_resources(
        self, dataset_id: str, limit: Optional[int] = None, page: int = 1
    ) -> List[Dict[str, Any]]:
        """Return the list of resources attached to a dataset.

        Parameters
        ----------
        dataset_id : str
            Identifier of the dataset.  This can be obtained from the
            output of :meth:`search_datasets`.
        limit : int, optional
            Maximum number of resources to return.  If None, all
            available resources on the first page are returned.  The
            API itself returns up to 50 resources per page.
        page : int, default 1
            Page of resources to return.

        Returns
        -------
        list of dict
            Each element is a dictionary representing a resource.  The
            keys include at least: ``id``, ``title``, ``format``,
            ``url``, ``filetype`` and other metadata from the API.  If
            no resources are available or an error occurs an empty
            list is returned.
        """
        if not dataset_id:
            logger.warning("get_resources called with empty dataset_id")
            return []
        url = f"{self.base_url}/datasets/{dataset_id}/resources/"
        # Use a high page_size to fetch as many resources as possible in one call.
        params = {"page": page, "page_size": limit or 50}
        json_data = self._request(url, params=params)
        if not json_data or "data" not in json_data:
            return []
        return json_data.get("data", [])

    def search_resources(
        self,
        query: str,
        dataset_limit: int = 5,
        resource_limit_per_dataset: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Search for resources across multiple datasets.

        This convenience method first searches for datasets matching
        ``query`` and then fetches resources for each of the top
        ``dataset_limit`` datasets.  Resources are returned as a flat
        list with additional fields identifying the originating
        dataset.  This can be useful when the orchestrator needs to
        present multiple candidate files to a downstream parser.

        Parameters
        ----------
        query : str
            Free text search term.
        dataset_limit : int, default 5
            The number of datasets to retrieve resources from.
        resource_limit_per_dataset : int, optional
            If provided, limits the number of resources retrieved per
            dataset.  If None, all resources from the first page are
            returned.

        Returns
        -------
        list of dict
            Flat list of resources.  Each resource dict contains all
            keys returned by the API plus ``dataset_id`` and
            ``dataset_title`` fields identifying the source dataset.
        """
        datasets = self.search_datasets(query, limit=dataset_limit)
        resources: List[Dict[str, Any]] = []
        for ds in datasets:
            ds_id = ds.get("id")
            ds_title = ds.get("title")
            ds_resources = self.get_resources(ds_id, limit=resource_limit_per_dataset)
            for res in ds_resources:
                # Copy the resource dictionary and annotate with dataset
                # metadata.  We avoid modifying the original dict in
                # place to preserve referential transparency for the
                # caller.
                annotated = {
                    **res,
                    "dataset_id": ds_id,
                    "dataset_title": ds_title,
                }
                resources.append(annotated)
        return resources


def search_datasets(query: str, limit: int = 10, page: int = 1) -> List[Dict[str, Any]]:
    """Module-level convenience wrapper around :meth:`DataGouvAPI.search_datasets`.

    This function instantiates a temporary client and delegates the
    call.  It is provided for situations where constructing a class
    instance is unnecessary or undesirable.
    """
    client = DataGouvAPI()
    return client.search_datasets(query, limit=limit, page=page)


def get_resources(dataset_id: str, limit: Optional[int] = None, page: int = 1) -> List[Dict[str, Any]]:
    """Module-level convenience wrapper around :meth:`DataGouvAPI.get_resources`.

    Creates a temporary client and returns the resources attached to a
    dataset.
    """
    client = DataGouvAPI()
    return client.get_resources(dataset_id, limit=limit, page=page)


def search_resources(
    query: str, dataset_limit: int = 5, resource_limit_per_dataset: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Module-level convenience wrapper around :meth:`DataGouvAPI.search_resources`.

    This helper is especially useful when only a quick resource search is
    needed without explicitly constructing a client instance.
    """
    client = DataGouvAPI()
    return client.search_resources(query, dataset_limit=dataset_limit, resource_limit_per_dataset=resource_limit_per_dataset)
