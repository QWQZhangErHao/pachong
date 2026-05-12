"""Abstract serverless runner interface.

Defines the contract for serverless function execution.
Implementations: Local subprocess, AWS Lambda, GCP Cloud Functions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pachong.core.models import ServerlessPayload


class AbstractServerlessRunner(ABC):
    """Interface for serverless function execution.

    The runner receives a pointer-based payload (NEVER the full DOM)
    and handles downloading data from S3, processing, and uploading results.
    """

    @abstractmethod
    async def invoke(self, payload: ServerlessPayload) -> bool:
        """Invoke a serverless function with the given payload.

        Returns True if the invocation was accepted (not necessarily completed).
        The function is responsible for uploading results independently.
        """

    @abstractmethod
    async def invoke_batch(self, payloads: list[ServerlessPayload]) -> int:
        """Invoke multiple serverless functions. Returns count of accepted invocations."""

    @abstractmethod
    async def healthy(self) -> bool:
        """Check if the serverless runner is operational."""

    @property
    @abstractmethod
    def max_concurrency(self) -> int:
        """Maximum number of concurrent function invocations."""

    @property
    @abstractmethod
    def active_invocations(self) -> int:
        """Current number of in-flight invocations."""
