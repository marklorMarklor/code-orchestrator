"""Top level package for the mcp_datagouv project.

This package contains the various modules that collectively make up
the Model Context Protocol (MCP) client for interacting with data
published on data.gouv.fr.  The modules under this package are
designed to be thin wrappers around the public API, download
utilities and parsers, leaving orchestration and business logic to
higher level components.

The functions exposed by the submodules should be considered stable
entry points for the orchestrator.  Each module provides sensible
defaults and attempts to handle recoverable network errors where
possible.  See the documentation strings in individual modules for
usage details.
"""

__all__ = [
    "datagouv_api",
    "downloader",
]
