"""Visualization utilities for the MCP project.

The visualizer subpackage gathers tools that convert tabular and
geospatial data into user–friendly artefacts such as charts and
animated maps.  These modules are intended to be consumed by the
orchestrator when a user requests a visual representation of the
queried data.
"""

# Re-export common helpers for convenience
from .map_animator import create_periodic_animation  # noqa: F401
from .summary_chart import (
    generate_bar_chart,
    generate_line_chart,
    generate_heatmap_chart,
)

__all__ = [
    "create_periodic_animation",
    "generate_bar_chart",
    "generate_line_chart",
    "generate_heatmap_chart",
]
