"""Answer-engine abstraction and implementations.

An *engine* answers a query and reports which sources it cited, in order. The
tracker never asks an engine about the target domain directly; it inspects the
returned citation list and decides whether (and at what rank) the target appears.
This keeps engines simple and makes the target-detection logic testable in one
place (:func:`detect_domain`).

Two engines ship with the tool:

* :class:`MockEngine` — deterministic, fully offline. Given a fixed pool of
  candidate domains it derives a stable citation list per query from a seeded
  hash. Same inputs always yield the same output, which is what the test suite
  relies on and why the default runs need no API key.
* :class:`ClaudeEngine` — a documented, real provider using the ``anthropic``
  SDK (model ``claude-sonnet-5``) with the web-search server tool. It is a thin
  stub with graceful failure: if the SDK or credentials are missing it raises
  :class:`EngineUnavailable` with an actionable message instead of crashing.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

# A small, stable pool of well-known domains the MockEngine can "cite". The
# target domain is injected into the pool by the CLI so it surfaces for some
# queries — that is what makes the illustrative citation rate non-trivial.
DEFAULT_MOCK_DOMAINS: tuple[str, ...] = (
    "wikipedia.org",
    "reddit.com",
    "g2.com",
    "capterra.com",
    "producthunt.com",
    "techcrunch.com",
    "forbes.com",
    "medium.com",
)


class EngineUnavailable(RuntimeError):
    """Raised when an engine cannot run (missing dependency, key, or network).

    The CLI catches this and prints the message verbatim, so keep messages
    actionable (tell the user exactly what to install or set).
    """


@dataclass
class EngineAnswer:
    """The result of asking an engine a single query.

    Attributes:
        engine: Name of the engine that produced the answer (e.g. ``"mock"``).
        query: The query that was asked.
        citations: Ordered list of cited sources (bare domains or URLs). Rank is
            derived from position in this list, so order is significant.
        text: Optional human-readable answer text (illustrative for the mock).
    """

    engine: str
    query: str
    citations: list[str] = field(default_factory=list)
    text: str = ""


@runtime_checkable
class Engine(Protocol):
    """Structural interface every answer engine implements.

    An engine exposes a stable ``name`` and answers a query. Implementations
    must be side-effect-free with respect to the tracker's store; persistence is
    handled entirely by :mod:`citationtracker.store`.
    """

    name: str

    def answer(self, query: str) -> EngineAnswer:
        """Answer ``query`` and return the cited sources in rank order."""
        ...


def domain_of(value: str) -> str:
    """Normalize a URL or bare domain to a comparable host string.

    Strips scheme, path, credentials, port, and a leading ``www.`` so that
    ``https://www.Example.com/page`` and ``example.com`` compare equal.
    """

    v = value.strip().lower()
    if "://" in v:
        v = v.split("://", 1)[1]
    v = v.split("/", 1)[0]
    v = v.split("@")[-1]  # drop any user:pass@ credentials
    v = v.split(":", 1)[0]  # drop any :port
    if v.startswith("www."):
        v = v[4:]
    return v


def detect_domain(citations: list[str], target: str) -> tuple[bool, int | None]:
    """Return whether ``target`` appears in ``citations`` and its 1-based rank.

    A citation matches the target if their normalized hosts are equal or the
    citation is a subdomain of the target (``blog.example.com`` matches
    ``example.com``). The first match wins.

    Returns:
        ``(cited, rank)`` where ``rank`` is ``None`` when not cited.
    """

    t = domain_of(target)
    for index, citation in enumerate(citations, start=1):
        d = domain_of(citation)
        if d == t or d.endswith("." + t):
            return True, index
    return False, None


class MockEngine:
    """Deterministic, offline answer engine.

    For each query the engine ranks its domain pool by a seeded hash and returns
    the top *k* (also derived from the query hash, 3–5). Because the ordering is
    a pure function of ``(seed, query, domain)``, results are reproducible: two
    ``MockEngine`` instances with the same pool and seed always agree. This is
    what lets the default workflow and the test suite run with zero network I/O.
    """

    name = "mock"

    def __init__(self, domains: list[str] | None = None, seed: str = "citationtracker") -> None:
        self._domains = list(domains) if domains else list(DEFAULT_MOCK_DOMAINS)
        self._seed = seed

    def _hash(self, *parts: str) -> str:
        return hashlib.sha256(":".join([self._seed, *parts]).encode("utf-8")).hexdigest()

    def answer(self, query: str) -> EngineAnswer:
        """Return a deterministic citation list for ``query``."""

        # Rank the pool deterministically for this query.
        ranked = sorted(self._domains, key=lambda d: self._hash(query, d))
        # Pick how many sources to "cite" (3..5), also deterministically.
        k = 3 + int(self._hash(query), 16) % 3
        citations = ranked[:k]
        text = (
            f"[mock] Based on available sources, the top references for "
            f"'{query}' are: {', '.join(citations)}."
        )
        return EngineAnswer(engine=self.name, query=query, citations=citations, text=text)


class ClaudeEngine:
    """Real answer engine backed by Claude (``claude-sonnet-5``) with web search.

    This is a documented provider stub, not part of the offline default path.
    It requires the optional ``anthropic`` dependency and valid credentials
    (``ANTHROPIC_API_KEY`` or an ``ant auth login`` profile). When either is
    missing, construction raises :class:`EngineUnavailable` so callers can fail
    gracefully with a clear message rather than an opaque traceback.

    The engine issues a web-style prompt and reads the ordered result URLs out
    of the ``web_search_tool_result`` blocks; those URLs become the citation
    list the tracker inspects for the target domain.
    """

    name = "claude"
    #: Model id requested by this project. Sonnet 5 supports the dynamic-filtering
    #: web-search tool variant used below.
    MODEL = "claude-sonnet-5"
    #: Web-search server-tool type for Sonnet 5 / current Opus models.
    WEB_SEARCH_TOOL = "web_search_20260209"

    def __init__(self, api_key: str | None = None, max_uses: int = 5, max_tokens: int = 1024) -> None:
        try:
            import anthropic  # noqa: F401  (import guarded for a friendly error)
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise EngineUnavailable(
                "The Claude engine needs the 'anthropic' package. "
                "Install it with: pip install anthropic"
            ) from exc

        self._anthropic = anthropic
        try:
            # A bare client resolves ANTHROPIC_API_KEY or an `ant auth login`
            # profile; only pass api_key when explicitly provided.
            self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        except Exception as exc:  # pragma: no cover - depends on local env
            raise EngineUnavailable(
                "Could not initialize the Anthropic client. Set ANTHROPIC_API_KEY "
                "or run `ant auth login`."
            ) from exc

        self._max_uses = max_uses
        self._max_tokens = max_tokens

    def answer(self, query: str) -> EngineAnswer:
        """Ask Claude ``query`` with web search enabled and collect cited URLs."""

        prompt = (
            "Answer the following question as an AI answer engine would for an "
            "end user. Use web search and base your answer on the sources you "
            f"find. Question: {query}"
        )
        try:
            response = self._client.messages.create(
                model=self.MODEL,
                max_tokens=self._max_tokens,
                tools=[
                    {
                        "type": self.WEB_SEARCH_TOOL,
                        "name": "web_search",
                        "max_uses": self._max_uses,
                    }
                ],
                messages=[{"role": "user", "content": prompt}],
            )
        except self._anthropic.APIError as exc:  # pragma: no cover - network dependent
            raise EngineUnavailable(f"Claude request failed: {exc}") from exc

        citations = self._extract_citations(response)
        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        return EngineAnswer(engine=self.name, query=query, citations=citations, text=text)

    @staticmethod
    def _extract_citations(response) -> list[str]:
        """Pull ordered, de-duplicated result URLs from web-search result blocks.

        A web-search error arrives as a single object on ``.content`` (not a
        list), so guard the type before iterating — this mirrors the SDK's
        documented error shape and keeps a failed search from raising.
        """

        urls: list[str] = []
        for block in response.content:
            if getattr(block, "type", None) != "web_search_tool_result":
                continue
            content = block.content
            if not isinstance(content, list):
                # Error object (e.g. max_uses_exceeded) — no results to record.
                continue
            for result in content:
                url = getattr(result, "url", None)
                if url and url not in urls:
                    urls.append(url)
        return urls


def build_engine(
    name: str,
    target_domain: str,
    mock_domains: list[str] | None = None,
    **claude_kwargs,
) -> Engine:
    """Construct an engine by name.

    For the mock engine the target domain is folded into the citation pool so it
    can plausibly surface. For the Claude engine, keyword arguments are forwarded
    to :class:`ClaudeEngine`.
    """

    if name == "mock":
        pool = list(mock_domains) if mock_domains else list(DEFAULT_MOCK_DOMAINS)
        # Ensure the target is present exactly once, at the front.
        pool = list(dict.fromkeys([target_domain, *pool]))
        return MockEngine(domains=pool)
    if name == "claude":
        return ClaudeEngine(**claude_kwargs)
    raise ValueError(f"Unknown engine: {name!r}. Choose 'mock' or 'claude'.")
