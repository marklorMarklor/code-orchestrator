"""
AgentPlanner Module
-------------------

This module contains the `generate_plan` function used to convert the raw
output of a large language model (LLM) into an ordered list of actions
that can be executed by the MCP orchestrator.  The plan produced here
provides a structured description of which internal agents (APIs,
downloaders, parsers, visualisers, etc.) should be called, in what order
and with which parameters.

The expected input to this module is a dictionary coming from the
`AgentLLM`.  That dictionary usually contains high level fields such as
``intent`` (the user's overall goal expressed as a short verb),
``entities`` (keywords, dates, locations, dataset identifiers, etc.), and
occasionally an explicit list of ``actions``.  Because the exact schema of
the LLM output may evolve over time, this function attempts to be
defensive and interpret a variety of possible keys when building the plan.

The returned plan is a list of dictionaries.  Each dictionary
represents a single step in the execution pipeline and contains three
keys:

``type``
    A short name describing the nature of the step (e.g. ``search_dataset``
    or ``download_dataset``).  This is primarily informational; the
    orchestrator chooses which concrete agent to call based on the
    ``target`` field.

``target``
    The fully qualified name of the agent or submodule that should be
    invoked for this step.  For example ``datagouv_api.search`` will call
    the search method on the API client, while ``csv_parser.parse``
    indicates that a CSV parser should be used to process a downloaded
    resource.

``params``
    A dictionary of keyword arguments that will be forwarded to the target
    function when the step is executed.  All values should be JSON
    serialisable.  When referring to the results of previous steps, use
    placeholder strings (e.g. ``"$search_results[0].url"``) which the
    orchestrator will resolve at runtime.

Examples
~~~~~~~~

Minimal input with keywords::

    >>> llm_output = {
    ...     "intent": "search_dataset",
    ...     "entities": {"keywords": ["population", "Île-de-France"]}
    ... }
    >>> generate_plan(llm_output)
    [
        {
            "type": "search_dataset",
            "target": "datagouv_api.search",
            "params": {"keywords": ["population", "Île-de-France"]}
        },
        {
            "type": "download_dataset",
            "target": "downloader.download",
            "params": {"resource": "$search_results[0]"}
        },
        {
            "type": "parse_dataset",
            "target": "file_utils.auto_parse",
            "params": {"file_path": "$download_result.file_path"}
        }
    ]

Explicit actions provided by the LLM are passed through with normalised
keys::

    >>> llm_output = {
    ...     "intent": "custom",
    ...     "actions": [
    ...         {"action": "search", "target": "datagouv_api.search", "params": {"keywords": ["budget"]}},
    ...         {"action": "download", "target": "downloader.download", "params": {"url": "http://example.com/file.csv"}}
    ...     ]
    ... }
    >>> generate_plan(llm_output)
    [
        {"type": "search", "target": "datagouv_api.search", "params": {"keywords": ["budget"]}},
        {"type": "download", "target": "downloader.download", "params": {"url": "http://example.com/file.csv"}}
    ]

This module does not perform any network or filesystem access; it purely
constructs the execution plan.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping


def _normalise_entities(entities: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalise and clean up entity keys from the LLM output.

    The LLM may return slightly different names for common fields.  This
    helper consolidates them into canonical names so later logic can be
    simpler.  For example ``mot_clés`` and ``keywords`` are mapped to
    ``keywords``.

    Parameters
    ----------
    entities: Mapping[str, Any]
        The raw entities dictionary from the LLM output.

    Returns
    -------
    Dict[str, Any]
        A new dictionary with keys normalised and irrelevant values
        filtered out.
    """
    canonical: Dict[str, Any] = {}
    for key, value in entities.items():
        lower_key = key.lower().strip()
        # Map French and English variations to canonical names
        if lower_key in {"mot_clé", "mot_clés", "mots_clés", "keyword", "keywords", "query"}:
            canonical.setdefault("keywords", [])
            # Flatten single strings into a list
            if isinstance(value, str):
                canonical["keywords"].append(value)
            elif isinstance(value, (list, tuple, set)):
                canonical["keywords"].extend(value)
        elif lower_key in {"dataset", "dataset_id", "id", "identifiant"}:
            canonical["dataset_id"] = value
        elif lower_key in {"dataset_name", "nom_dataset", "title"}:
            canonical["dataset_name"] = value
        elif lower_key in {"file_format", "format", "format_fichier"}:
            canonical["file_format"] = str(value).lower()
        elif lower_key in {"date_range", "période", "periode"}:
            # Expect a mapping with start/end; keep as is
            if isinstance(value, Mapping):
                canonical["date_range"] = dict(value)
        elif lower_key in {"location", "lieu", "commune", "département", "department", "region", "région"}:
            canonical["location"] = value
        elif lower_key in {"theme", "subject", "thème"}:
            canonical["theme"] = value
        elif lower_key in {"visualisation", "visualization", "viz", "chart", "graph", "map"}:
            # Could be a string or list specifying requested visual outputs
            if isinstance(value, str):
                canonical.setdefault("visualisation", []).append(value)
            elif isinstance(value, (list, tuple, set)):
                canonical.setdefault("visualisation", []).extend(value)
        else:
            # Preserve any unknown keys verbatim
            canonical[lower_key] = value
    return canonical


def _build_default_plan(llm_output: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Construct a plan from an LLM output without an explicit actions list.

    When the LLM does not supply its own sequence of actions, this function
    infers a reasonable plan based on the intent and entities.  The goal is
    to cover the most common operations: searching for datasets, downloading
    resources, parsing them and optionally producing visualisations.

    Parameters
    ----------
    llm_output: Dict[str, Any]
        The raw JSON-like structure returned by the LLM.

    Returns
    -------
    List[Dict[str, Any]]
        A sequence of plan steps encoded as dictionaries.
    """
    plan: List[Dict[str, Any]] = []
    intent: str = str(llm_output.get("intent", "")).lower()
    entities_raw: Mapping[str, Any] = llm_output.get("entities", {})
    entities: Dict[str, Any] = _normalise_entities(entities_raw)

    # Step 1: search datasets if we have search parameters or no dataset_id
    if ("keywords" in entities or "dataset_name" in entities) and "dataset_id" not in entities:
        search_params: Dict[str, Any] = {}
        if "keywords" in entities:
            search_params["keywords"] = entities["keywords"]
        if "dataset_name" in entities:
            search_params["dataset_name"] = entities["dataset_name"]
        if "theme" in entities:
            search_params["theme"] = entities["theme"]
        if "location" in entities:
            search_params["location"] = entities["location"]
        if "date_range" in entities:
            search_params["date_range"] = entities["date_range"]
        plan.append({
            "type": "search_dataset",
            "target": "datagouv_api.search",
            "params": search_params,
        })

        # After searching we intend to download the first matching resource
        plan.append({
            "type": "download_dataset",
            "target": "downloader.download",
            # Use a placeholder for the resource reference.  The orchestrator
            # will resolve ``$search_results[0]`` to the first element of the
            # search output when executing the plan.
            "params": {"resource": "$search_results[0]"},
        })
    elif "dataset_id" in entities:
        # We know exactly which dataset to download; no search required
        plan.append({
            "type": "download_dataset",
            "target": "downloader.download",
            "params": {"dataset_id": entities["dataset_id"]},
        })

    # Step 2: parse the downloaded file.  Choose parser based on known format
    # or fall back to automatic detection using file_utils
    file_format: str | None = entities.get("file_format")
    if file_format in {"csv", "tsv", "txt"}:
        parser_target = "csv_parser.parse"
    elif file_format in {"json"}:
        parser_target = "json_parser.parse"
    elif file_format in {"geojson", "geo"}:
        parser_target = "geojson_parser.parse"
    else:
        parser_target = "file_utils.auto_parse"
    plan.append({
        "type": "parse_dataset",
        "target": parser_target,
        # Placeholder: the downloader returns an object with file_path attribute
        "params": {"file_path": "$download_result.file_path"},
    })

    # Step 3: temporal and geographical transformations if requested
    if any(term in intent for term in ["temps", "temporel", "chronologie", "time"]):
        plan.append({
            "type": "enrich_temporal",
            "target": "temporal_utils.enrich_time_columns",
            "params": {"data": "$parse_dataset_result"},
        })
    if any(term in intent for term in ["carte", "geo", "géographie", "map", "location"]):
        plan.append({
            "type": "enrich_geo",
            "target": "geo_utils.enrich_geometries",
            "params": {"data": "$parse_dataset_result"},
        })

    # Step 4: visualisation (chart or map) if explicitly requested
    visualisations = entities.get("visualisation", [])
    # Normalise to lower-case strings
    visualisations = [v.lower() for v in visualisations] if isinstance(visualisations, list) else []
    if "map" in visualisations or "carte" in visualisations:
        plan.append({
            "type": "generate_map",
            "target": "visualizer.map_animator",
            "params": {"data": "$parse_dataset_result"},
        })
    if "chart" in visualisations or "graph" in visualisations or "histogramme" in visualisations:
        plan.append({
            "type": "generate_chart",
            "target": "visualizer.summary_chart",
            "params": {"data": "$parse_dataset_result"},
        })

    return plan


def generate_plan(llm_output: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Create an actionable execution plan from an LLM output.

    The returned plan is a sequential list of steps dictating which
    subsystems should be invoked to satisfy the user request.  If the
    ``actions`` key exists in ``llm_output`` and contains a list of
    dictionaries, this function will normalise those entries directly into
    the plan.  Otherwise, it derives a sensible default plan using
    heuristics based on the detected intent and entities.

    Parameters
    ----------
    llm_output: Dict[str, Any]
        Raw JSON output from the LLM.  Expected keys may include
        ``intent``, ``entities``, ``actions`` and others.

    Returns
    -------
    List[Dict[str, Any]]
        A list of plan steps.  Each step is a dictionary with
        ``type``, ``target`` and ``params`` keys.
    """
    # If the LLM provided explicit actions, honour them by normalising keys
    actions = llm_output.get("actions")
    if isinstance(actions, list) and actions:
        plan: List[Dict[str, Any]] = []
        for action in actions:
            if not isinstance(action, Mapping):
                continue  # skip malformed entries
            action_name = str(action.get("action", action.get("type", ""))).strip()
            target = action.get("target")
            params = action.get("params", {})
            if not isinstance(params, Mapping):
                # ensure params is a dict
                params = {"value": params}
            plan.append({
                "type": action_name,
                "target": target,
                "params": dict(params),
            })
        return plan

    # No explicit actions: build a default plan
    return _build_default_plan(llm_output)
