"""ai-citation-tracker: track whether a domain is cited by AI answer engines.

This package is offline-first. The default :class:`~citationtracker.engines.MockEngine`
produces deterministic, illustrative results with no network calls. A documented
:class:`~citationtracker.engines.ClaudeEngine` shows how to plug in a real answer
engine (Claude with web search) once an API key is available.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
