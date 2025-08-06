"""Parser modules for the MCP project.

Parsing modules convert raw files (CSV, JSON, GeoJSON, Excel, etc.) into
structured in-memory objects such as pandas DataFrames.  The
``geojson_parser`` module, for example, produces GeoDataFrames that
may be consumed by the visualiser.

Submodules are typically named ``<format>_parser.py`` and expose
functions like ``parse_<format>``.  See the project specification for
details.
"""

__all__ = []
