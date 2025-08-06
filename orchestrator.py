"""
orchestrator.py
================

This module forms the heart of the MCP (Model Context Protocol) data
processing pipeline. Its primary responsibility is to take a natural
language question from an end user, solicit a large language model
(LLM) for a structured intent, transform that intent into a concrete
execution plan via the planner, and then carry out each of the
actions in that plan using the appropriate sub‑modules. The
orchestrator abstracts away the details of how data is fetched,
downloaded, parsed, or visualised, and exposes a single function
``process_question`` for external callers such as the API layer.

The expected flow is as follows:

1. **LLM Invocation** — The user's question is forwarded to the
   ``llm_agent`` which returns a raw description of the user's
   intent in JSON form. This may include the high level goal,
   entities to search for, time ranges, and a list of suggested
   actions.
2. **Planning** — The raw intent JSON is passed to the ``planner``
   module which refines it into an ordered list of executable steps.
   Each step is a dictionary describing the ``action`` to perform
   and any parameters needed to execute it (e.g. keywords for
   searching, dataset IDs, file formats, etc.).
3. **Execution** — The orchestrator iterates over the ordered steps
   and dispatches each one to the appropriate handler. It keeps
   track of intermediate artifacts (like downloaded file paths,
   parsed dataframes, or visualisation objects) in a ``context``
   dictionary so that later steps can build upon the results of
   earlier ones.
4. **Aggregation** — Once all actions have been executed, the
   orchestrator compiles a final structured response. This may
   include raw data (e.g. pandas DataFrames), metadata about the
   datasets found, and paths to any generated visualisations. If an
   error occurs at any point, a descriptive error message is
   captured rather than allowing an uncaught exception to unwind the
   call stack.

The orchestrator is intentionally conservative in its assumptions
about downstream modules. It does not attempt to access any global
state from those modules and instead depends only on documented
interfaces. Where no such interface is available, it raises a
``NotImplementedError`` to signal that the consuming module must
provide the requisite functionality. This makes the orchestrator
robust against incomplete implementations and easy to extend as
additional action types are introduced.

Example usage::

    from orchestrator import process_question
    response = process_question("Quels sont les logements sociaux construits en 2023 à Paris ?")
    # ``response`` is a dictionary containing datasets, tables,
    # visualisations and any summaries generated during the pipeline.

"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Setup a basic logger. In a real application, the FastAPI layer would
# configure logging and propagate those settings down; here we default
# to INFO for demonstrability.
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)s in %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class OrchestratorError(Exception):
    """Custom exception type for orchestrator errors."""


@dataclass
class ActionResult:
    """Container for results of executing an action.

    Attributes
    ----------
    name: str
        The name of the action that produced this result.
    result: Any
        The result returned by the action handler (dataset metadata,
        downloaded file path, parsed dataframe, visualisation etc.).
    description: Optional[str]
        A human‑readable description of what this result represents.
    """

    name: str
    result: Any
    description: Optional[str] = None


def _safe_import(module_name: str) -> Optional[Any]:
    """Attempt to import a module, returning ``None`` if unavailable.

    This helper function centralises import error handling. If the
    underlying module does not exist yet, this function logs the
    absence and returns ``None`` so that the orchestrator can raise a
    meaningful exception when its services are invoked.

    Parameters
    ----------
    module_name: str
        The fully qualified name of the module to import.

    Returns
    -------
    Optional[Any]
        The imported module, or ``None`` if the import failed.
    """
    try:
        return __import__(module_name, fromlist=["*"])
    except ImportError:
        logger.debug("Module %s could not be imported.", module_name)
        return None


def process_question(question: str) -> Dict[str, Any]:
    """Top level entry point for answering a user question.

    This function orchestrates the entire lifecycle of a request: it
    queries the language model, builds a plan, executes each action,
    and collects the results. It is designed to be synchronous and
    deterministic; concurrency is left to the discretion of the
    underlying modules.

    Parameters
    ----------
    question : str
        The user's question in natural language. It should be
        sufficiently specific that the LLM and planner can infer
        appropriate actions.

    Returns
    -------
    Dict[str, Any]
        A structured response containing the results of executing the
        plan. The keys of this dictionary may include ``plan`` (the
        interpreted plan returned by the planner), ``datasets`` (meta
        information about datasets discovered), ``data`` (parsed
        dataframes or lists/dicts), ``visualisations`` (paths to
        generated images or maps), ``summary`` (an optional
        natural language summary), and ``errors`` (a list of error
        messages encountered during processing). Missing keys simply
        indicate that no such artefact was produced.

    Raises
    ------
    OrchestratorError
        If a critical dependency (such as the LLM agent or planner)
        cannot be imported or if the plan returned by the planner is
        malformed.
    """
    logger.info("Processing question: %s", question)

    # Try to import required modules. If they are not yet implemented,
    # we'll note that and later raise an informative exception.
    llm = _safe_import("mcp_datagouv.llm_agent") or _safe_import("llm_agent")
    planner_module = _safe_import("mcp_datagouv.planner") or _safe_import("planner")
    datagouv_api = _safe_import("mcp_datagouv.datagouv_api") or _safe_import("datagouv_api")
    downloader_module = _safe_import("mcp_datagouv.downloader") or _safe_import("downloader")
    parsers_pkg = _safe_import("mcp_datagouv.parsers") or _safe_import("parsers")
    visualizer_pkg = _safe_import("mcp_datagouv.visualizer") or _safe_import("visualizer")

    if llm is None:
        raise OrchestratorError(
            "llm_agent module is required but not found. Please implement mcp_datagouv.llm_agent."
        )
    if planner_module is None:
        raise OrchestratorError(
            "planner module is required but not found. Please implement mcp_datagouv.planner."
        )

    # 1. Query the LLM to obtain a raw intent. The llm_agent is
    # expected to expose a function or class method that accepts a
    # question string and returns a JSON-like dictionary. We support
    # both functional and object‑oriented interfaces for flexibility.
    if hasattr(llm, "process_question"):
        raw_intent = llm.process_question(question)
    elif hasattr(llm, "LLMAgent"):
        llm_agent_instance = getattr(llm, "LLMAgent")()
        if hasattr(llm_agent_instance, "process_question"):
            raw_intent = llm_agent_instance.process_question(question)
        elif hasattr(llm_agent_instance, "__call__"):
            raw_intent = llm_agent_instance(question)  # type: ignore
        else:
            raise OrchestratorError(
                "llm_agent does not provide a callable interface."
            )
    else:
        raise OrchestratorError(
            "llm_agent must define either a process_question function or LLMAgent class."
        )

    logger.debug("Raw intent from LLM: %s", raw_intent)

    # 2. Pass the intent through the planner to get a concrete plan. A
    # well‑formed plan is expected to be a list of action dicts with
    # names and parameters. Raise a clear error if the structure is
    # unexpected.
    if hasattr(planner_module, "create_plan"):
        plan = planner_module.create_plan(raw_intent)
    elif hasattr(planner_module, "Planner"):
        planner_instance = getattr(planner_module, "Planner")()
        if hasattr(planner_instance, "create_plan"):
            plan = planner_instance.create_plan(raw_intent)
        elif hasattr(planner_instance, "__call__"):
            plan = planner_instance(raw_intent)  # type: ignore
        else:
            raise OrchestratorError(
                "planner module does not expose a create_plan method."
            )
    else:
        raise OrchestratorError(
            "planner must define either a create_plan function or Planner class."
        )

    if not isinstance(plan, list):
        raise OrchestratorError(
            f"Planner returned unexpected type {type(plan).__name__}, expected list of actions."
        )

    logger.info("Received execution plan with %d actions", len(plan))

    # Container to accumulate artifacts. Keys may include 'datasets',
    # 'files', 'data', 'visualisations', 'summary', 'errors'.
    results: Dict[str, Any] = {
        "plan": plan,
        "datasets": [],
        "files": [],
        "data": [],
        "visualisations": [],
        "summary": None,
        "errors": [],
    }
    # Context is used to share intermediate values (e.g. last downloaded
    # file or last parsed dataframe) between actions.
    context: Dict[str, Any] = {}

    # Local helper to dispatch actions. We capture datagouv_api,
    # downloader_module, parsers_pkg, and visualizer_pkg from outer
    # scope. The dispatcher updates context and results as necessary.
    def execute_action(action: Dict[str, Any]) -> Optional[ActionResult]:
        action_name = action.get("action")
        params = action.get("params", {})
        logger.info("Executing action: %s with params %s", action_name, params)

        if action_name in ("search", "search_datasets", "search_dataset"):
            if datagouv_api is None:
                raise OrchestratorError("datagouv_api module is required for search actions.")
            keywords = params.get("keywords") or params.get("query") or params
            # Normalise to list of strings
            if isinstance(keywords, str):
                keywords = [keywords]
            try:
                # The datagouv_api is expected to expose a search function
                # returning metadata for datasets matching the query.
                if hasattr(datagouv_api, "search"):
                    datasets = datagouv_api.search(keywords)
                elif hasattr(datagouv_api, "search_datasets"):
                    datasets = datagouv_api.search_datasets(keywords)
                else:
                    raise OrchestratorError("datagouv_api does not implement a search function.")
                results["datasets"].extend(datasets)
                context["datasets"] = datasets
                return ActionResult(
                    name=action_name,
                    result=datasets,
                    description=f"Found {len(datasets)} datasets for {keywords}",
                )
            except Exception as exc:
                logger.exception("Error while searching datasets: %s", exc)
                results["errors"].append(str(exc))
                return None

        elif action_name in ("download", "download_resource", "download_file"):
            if downloader_module is None:
                raise OrchestratorError("downloader module is required for download actions.")
            url: Optional[str] = params.get("url")
            if url is None and "resource" in params:
                url = params["resource"]
            if url is None:
                # If URL is still not provided, attempt to infer from context
                # (e.g. choose the first resource URL from the last dataset).
                datasets = context.get("datasets")
                if datasets:
                    # naive heuristic: take the first dataset's first resource URL
                    try:
                        url = datasets[0]["resources"][0]["url"]  # type: ignore
                        logger.debug("Inferred URL %s from context datasets", url)
                    except Exception:
                        pass
            if not url:
                results["errors"].append("No URL provided for download action.")
                return None
            try:
                if hasattr(downloader_module, "download"):
                    file_path = downloader_module.download(url)
                elif hasattr(downloader_module, "Downloader"):
                    dl = downloader_module.Downloader()
                    file_path = dl.download(url)  # type: ignore[attr-defined]
                else:
                    raise OrchestratorError("downloader does not implement a download function.")
                results["files"].append(file_path)
                context["last_file"] = file_path
                return ActionResult(
                    name=action_name,
                    result=file_path,
                    description=f"Downloaded file to {file_path}",
                )
            except Exception as exc:
                logger.exception("Error while downloading resource: %s", exc)
                results["errors"].append(str(exc))
                return None

        elif action_name in ("parse", "parse_file"):
            file_path = params.get("path") or context.get("last_file")
            # Determine the format; either provided explicitly or inferred from
            # the file extension using a simple heuristic.
            fmt: Optional[str] = params.get("format")
            if not fmt and file_path:
                if "." in file_path:
                    fmt = file_path.rsplit(".", 1)[-1].lower()
            if not file_path:
                results["errors"].append("No file path available for parse action.")
                return None
            if parsers_pkg is None:
                raise OrchestratorError("parsers package is required for parse actions.")
            try:
                parsed: Any
                if fmt in ("csv", "tsv"):
                    parser = getattr(parsers_pkg, "csv_parser", None)
                    if parser is None:
                        raise OrchestratorError("CSV parser not implemented.")
                    if hasattr(parser, "parse"):
                        parsed = parser.parse(file_path)
                    else:
                        # fallback to a generic function name
                        parsed = parser(file_path)  # type: ignore
                elif fmt in ("json", "ndjson"):
                    parser = getattr(parsers_pkg, "json_parser", None)
                    if parser is None:
                        raise OrchestratorError("JSON parser not implemented.")
                    if hasattr(parser, "parse"):
                        parsed = parser.parse(file_path)
                    else:
                        parsed = parser(file_path)  # type: ignore
                elif fmt in ("geojson", "geojsonl"):
                    parser = getattr(parsers_pkg, "geojson_parser", None)
                    if parser is None:
                        raise OrchestratorError("GeoJSON parser not implemented.")
                    if hasattr(parser, "parse"):
                        parsed = parser.parse(file_path)
                    else:
                        parsed = parser(file_path)  # type: ignore
                elif fmt in ("xml", "gml"):
                    parser = getattr(parsers_pkg, "xml_parser", None)
                    if parser is None:
                        raise OrchestratorError("XML parser not implemented.")
                    if hasattr(parser, "parse"):
                        parsed = parser.parse(file_path)
                    else:
                        parsed = parser(file_path)  # type: ignore
                elif fmt in ("xls", "xlsx"):
                    parser = getattr(parsers_pkg, "xls_parser", None)
                    if parser is None:
                        raise OrchestratorError("XLS parser not implemented.")
                    if hasattr(parser, "parse"):
                        parsed = parser.parse(file_path)
                    else:
                        parsed = parser(file_path)  # type: ignore
                else:
                    raise OrchestratorError(f"Unsupported file format '{fmt}'.")
                results["data"].append(parsed)
                context["last_data"] = parsed
                return ActionResult(
                    name=action_name,
                    result=parsed,
                    description=f"Parsed file {file_path} as {fmt}",
                )
            except Exception as exc:
                logger.exception("Error while parsing file: %s", exc)
                results["errors"].append(str(exc))
                return None

        elif action_name in ("visualise", "visualize", "generate_visualisation", "generate_visualization"):
            # Determine the type of visualisation requested: chart or map.
            vis_type = params.get("type")
            data = params.get("data") or context.get("last_data")
            if vis_type is None:
                # Default to summary chart if we have tabular data, otherwise map
                vis_type = "chart" if data is not None else "map"
            if visualizer_pkg is None:
                raise OrchestratorError("visualizer package is required for visualisation actions.")
            try:
                output: Any
                if vis_type in ("chart", "summary_chart", "graph"):
                    summary_chart_mod = getattr(visualizer_pkg, "summary_chart", None)
                    if summary_chart_mod is None:
                        raise OrchestratorError("summary_chart module not implemented.")
                    if hasattr(summary_chart_mod, "create_chart"):
                        output = summary_chart_mod.create_chart(data)
                    else:
                        output = summary_chart_mod(data)  # type: ignore
                elif vis_type in ("map", "heatmap", "animation"):
                    map_animator_mod = getattr(visualizer_pkg, "map_animator", None)
                    if map_animator_mod is None:
                        raise OrchestratorError("map_animator module not implemented.")
                    if hasattr(map_animator_mod, "create_animation"):
                        output = map_animator_mod.create_animation(data)
                    else:
                        output = map_animator_mod(data)  # type: ignore
                else:
                    raise OrchestratorError(f"Unsupported visualisation type '{vis_type}'.")
                results["visualisations"].append(output)
                context["last_visualisation"] = output
                return ActionResult(
                    name=action_name,
                    result=output,
                    description=f"Generated {vis_type} visualisation",
                )
            except Exception as exc:
                logger.exception("Error while generating visualisation: %s", exc)
                results["errors"].append(str(exc))
                return None

        elif action_name in ("summarise", "summarize", "summarization"):
            # Summarisation can leverage the LLM again or a dedicated summariser
            target = params.get("data") or context.get("last_data") or results.get("datasets")
            try:
                if hasattr(llm, "summarize"):
                    summary = llm.summarize(target, question=question)
                elif hasattr(llm, "LLMAgent"):
                    llm_instance = getattr(llm, "LLMAgent")()
                    if hasattr(llm_instance, "summarize"):
                        summary = llm_instance.summarize(target, question=question)  # type: ignore
                    else:
                        # Fallback: if no summariser available, just str() the data
                        summary = str(target)
                else:
                    summary = str(target)
                results["summary"] = summary
                context["last_summary"] = summary
                return ActionResult(
                    name=action_name,
                    result=summary,
                    description="Generated natural language summary",
                )
            except Exception as exc:
                logger.exception("Error during summarisation: %s", exc)
                results["errors"].append(str(exc))
                return None

        else:
            # Unknown action; record an error but continue
            msg = f"Unknown action '{action_name}' encountered in plan."
            logger.warning(msg)
            results["errors"].append(msg)
            return None

    # 3. Execute actions sequentially
    for idx, action in enumerate(plan):
        if not isinstance(action, dict):
            err = f"Plan action at index {idx} is not a dict: {action}"
            logger.error(err)
            results["errors"].append(err)
            continue
        try:
            execute_action(action)
        except OrchestratorError as orch_exc:
            # For orchestrator specific errors, abort execution and rethrow
            logger.error("Critical orchestrator error: %s", orch_exc)
            raise
        except Exception as exc:
            # Non‑critical exceptions are logged and collected
            logger.exception("Unhandled exception in action execution: %s", exc)
            results["errors"].append(str(exc))

    # Final clean up: remove empty lists or None values for cleanliness
    final_results: Dict[str, Any] = {}
    for key, value in results.items():
        if value:
            final_results[key] = value

    logger.info("Finished processing question. Produced keys: %s", list(final_results.keys()))
    return final_results


__all__ = ["process_question", "OrchestratorError", "ActionResult"]
