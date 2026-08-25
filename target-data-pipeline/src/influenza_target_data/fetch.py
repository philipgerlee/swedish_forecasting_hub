"""HTTP access to the Folkhälsodata PxWeb API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import API_URL, FIXED_SELECTIONS, TIME_DIMENSION


class SourceError(RuntimeError):
    """Raised when source metadata or transport is invalid."""


@dataclass(frozen=True)
class SourceResponse:
    metadata: dict[str, Any]
    dataset: dict[str, Any] | None
    requested_weeks: tuple[str, ...]
    available_weeks: tuple[str, ...]
    unavailable_weeks: tuple[str, ...]
    fetched_at: datetime


def _session() -> requests.Session:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/json",
            "User-Agent": "SwedishForecastingHub/0.1 (research pilot)",
        }
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def _variables(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    variables = metadata.get("variables")
    if not isinstance(variables, list):
        raise SourceError("Source metadata has no variables list")
    result = {variable.get("code"): variable for variable in variables}
    if None in result:
        raise SourceError("A source variable is missing its code")
    return result


def validate_metadata(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate required dimensions/codes and return non-blocking warnings."""
    variables = _variables(metadata)
    expected = set(FIXED_SELECTIONS) | {TIME_DIMENSION}
    missing_dimensions = sorted(expected - set(variables))
    if missing_dimensions:
        raise SourceError(f"Missing source dimensions: {missing_dimensions}")

    for dimension, required_values in FIXED_SELECTIONS.items():
        available = set(variables[dimension].get("values", []))
        missing_values = sorted(set(required_values) - available)
        if missing_values:
            raise SourceError(
                f"Dimension {dimension!r} is missing required values {missing_values}"
            )

    warnings: list[dict[str, Any]] = []
    unexpected = sorted(set(variables) - expected)
    if unexpected:
        warnings.append(
            {
                "severity": "warning",
                "check": "unexpected_metadata_dimensions",
                "message": f"Unexpected source dimensions: {unexpected}",
            }
        )
    return warnings


def build_query(weeks: Iterable[str]) -> dict[str, Any]:
    query = []
    for code, values in FIXED_SELECTIONS.items():
        query.append(
            {
                "code": code,
                "selection": {"filter": "item", "values": list(values)},
            }
        )
    query.append(
        {
            "code": TIME_DIMENSION,
            "selection": {"filter": "item", "values": list(weeks)},
        }
    )
    return {"query": query, "response": {"format": "json-stat2"}}


class FolkhalsodataClient:
    def __init__(
        self,
        url: str = API_URL,
        *,
        timeout: tuple[int, int] = (10, 60),
        session: requests.Session | None = None,
    ) -> None:
        self.url = url
        self.timeout = timeout
        self.session = session or _session()

    def _json(self, response: requests.Response, context: str) -> dict[str, Any]:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            snippet = response.text[:500]
            raise SourceError(
                f"{context} failed with HTTP {response.status_code}: {snippet}"
            ) from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise SourceError(f"{context} did not return valid JSON") from exc
        if not isinstance(payload, dict):
            raise SourceError(f"{context} returned an unexpected JSON structure")
        return payload

    def metadata(self) -> dict[str, Any]:
        """Fetch and validate the current PxWeb metadata document."""
        try:
            metadata_response = self.session.get(self.url, timeout=self.timeout)
        except requests.RequestException as exc:
            raise SourceError(f"Metadata request failed: {exc}") from exc
        metadata = self._json(metadata_response, "Metadata request")
        validate_metadata(metadata)
        return metadata

    def fetch(self, requested_weeks: Iterable[str]) -> SourceResponse:
        weeks = tuple(dict.fromkeys(requested_weeks))
        metadata = self.metadata()

        variables = _variables(metadata)
        source_weeks = set(variables[TIME_DIMENSION].get("values", []))
        available = tuple(week for week in weeks if week in source_weeks)
        unavailable = tuple(week for week in weeks if week not in source_weeks)
        dataset: dict[str, Any] | None = None
        if available:
            try:
                data_response = self.session.post(
                    self.url,
                    json=build_query(available),
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                raise SourceError(f"Data request failed: {exc}") from exc
            dataset = self._json(data_response, "Data request")

        return SourceResponse(
            metadata=metadata,
            dataset=dataset,
            requested_weeks=weeks,
            available_weeks=available,
            unavailable_weeks=unavailable,
            fetched_at=datetime.now(timezone.utc),
        )
