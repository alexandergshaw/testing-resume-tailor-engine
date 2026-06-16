"""Downstream service clients + env-configured factories.

Factories return None when the service isn't configured, so the composer can
degrade gracefully (composed -> legacy fallback) instead of crashing.
"""
from .base import DownstreamError
from .generator import GeneratorClient
from .parser import ParserClient
from .researcher import ResearcherClient


def get_parser_client() -> ParserClient | None:
    return ParserClient.from_env()


def get_researcher_client() -> ResearcherClient | None:
    return ResearcherClient.from_env()


def get_generator_client() -> GeneratorClient | None:
    return GeneratorClient.from_env()


__all__ = [
    "DownstreamError", "ParserClient", "ResearcherClient", "GeneratorClient",
    "get_parser_client", "get_researcher_client", "get_generator_client",
]
