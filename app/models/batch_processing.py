"""Result models for batch URL processing."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse


@dataclass
class FailedURLDetail:
    """Detailed information about a failed URL in batch processing.

    This provides rich error context for user feedback and debugging.

    Attributes:
        url: The URL that failed
        error_type: Type of error (e.g., "timeout", "network", "validation", "circuit_breaker")
        error_message: Human-readable error message
        retry_recommended: Whether user should retry this URL
        attempts: Number of attempts made before failure
    """

    url: str
    error_type: str
    error_message: str
    retry_recommended: bool = False
    attempts: int = 1


@dataclass
class URLProcessingResult:
    """Result of processing a single URL with detailed error context.

    This replaces the simple bool return value to provide rich error information
    that can be used for retry logic, user feedback, and debugging.

    Attributes:
        url: The URL that was processed
        success: Whether processing succeeded
        error_type: Type of error if failed (e.g., "timeout", "network", "validation")
        error_message: Human-readable error message
        retry_possible: Whether this error is transient and retry makes sense
        processing_time_ms: Time taken to process in milliseconds
    """

    url: str
    success: bool
    error_type: str | None = None
    error_message: str | None = None
    retry_possible: bool = False
    processing_time_ms: float = 0.0

    @classmethod
    def success_result(cls, url: str, processing_time_ms: float = 0.0) -> URLProcessingResult:
        """Create a successful result."""
        return cls(url=url, success=True, processing_time_ms=processing_time_ms)

    @classmethod
    def error_result(
        cls,
        url: str,
        error_type: str,
        error_message: str,
        retry_possible: bool = False,
        processing_time_ms: float = 0.0,
    ) -> URLProcessingResult:
        """Create an error result."""
        return cls(
            url=url,
            success=False,
            error_type=error_type,
            error_message=error_message,
            retry_possible=retry_possible,
            processing_time_ms=processing_time_ms,
        )

    @classmethod
    def timeout_result(cls, url: str, timeout_sec: float) -> URLProcessingResult:
        """Create a timeout error result."""
        return cls.error_result(
            url=url,
            error_type="timeout",
            error_message=f"Processing timed out after {timeout_sec} seconds",
            retry_possible=True,
        )

    @classmethod
    def network_error_result(cls, url: str, error: Exception) -> URLProcessingResult:
        """Create a network error result."""
        return cls.error_result(
            url=url,
            error_type="network",
            error_message=str(error),
            retry_possible=True,
        )

    @classmethod
    def validation_error_result(cls, url: str, error: Exception) -> URLProcessingResult:
        """Create a validation error result (not retryable)."""
        return cls.error_result(
            url=url,
            error_type="validation",
            error_message=str(error),
            retry_possible=False,
        )

    @classmethod
    def generic_error_result(cls, url: str, error: Exception) -> URLProcessingResult:
        """Create a generic error result."""
        error_type = type(error).__name__
        return cls.error_result(
            url=url,
            error_type=error_type.lower(),
            error_message=str(error),
            retry_possible=False,  # Conservative: don't retry unknown errors
        )


class URLStatus(Enum):
    """Status of a URL in batch processing."""

    PENDING = "pending"
    PROCESSING = "processing"
    EXTRACTING = "extracting"  # Firecrawl content extraction phase
    ANALYZING = "analyzing"  # LLM summarization phase
    RETRYING = "retrying"  # Retrying due to error (e.g. timeout)
    COMPLETE = "complete"
    CACHED = "cached"  # Reused existing summary
    FAILED = "failed"


@dataclass
class URLStatusEntry:
    """Status entry for a single URL in batch processing.

    Tracks the current status, metadata, and timing for display in progress messages.

    Attributes:
        url: The URL being processed
        status: Current processing status
        domain: Extracted domain for compact display (e.g., "techcrunch.com")
        title: Article title (populated on completion)
        error_type: Type of error if failed
        error_message: Human-readable error message if failed
        processing_time_ms: Time taken to process in milliseconds
        start_time: Unix timestamp when processing started
    """

    url: str
    status: URLStatus = URLStatus.PENDING
    domain: str | None = None
    display_label: str | None = None
    title: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    processing_time_ms: float = 0.0
    start_time: float | None = None

    def __post_init__(self) -> None:
        """Extract domain and display label from URL on creation."""
        if self.domain is None:
            self.domain = self._extract_domain(self.url)
        if self.display_label is None:
            self.display_label = self._extract_display_label(self.url)

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Extract display-friendly domain from URL."""
        try:
            parsed = urlparse(url if "://" in url else f"https://{url}")
            host = parsed.hostname or parsed.netloc or url
            # Remove www. prefix for cleaner display
            if host.startswith("www."):
                host = host[4:]
            return host
        except Exception:
            return url[:30]

    @staticmethod
    def _extract_display_label(url: str, max_length: int = 40) -> str:
        """Extract a display-friendly label that distinguishes same-domain URLs.

        Includes the last path segment (slug) to differentiate URLs from the same
        domain, e.g. ``habr.com/.../123456`` instead of just ``habr.com``.

        Args:
            url: The URL to extract the label from
            max_length: Maximum length of the returned label

        Returns:
            A compact, human-readable label like ``habr.com/.../123456``
        """
        try:
            parsed = urlparse(url if "://" in url else f"https://{url}")
            host = parsed.hostname or parsed.netloc or url
            if host.startswith("www."):
                host = host[4:]

            # Get non-empty path segments
            path = parsed.path.rstrip("/")
            segments = [s for s in path.split("/") if s]

            if not segments:
                return host

            slug = segments[-1]

            label = f"{host}/{slug}" if len(segments) == 1 else f"{host}/.../{slug}"

            # Truncate long slugs while keeping the label readable
            if len(label) > max_length:
                # Keep host + "/.../" prefix, truncate the slug
                prefix = f"{host}/.../"
                available = max_length - len(prefix) - 3  # 3 for "..."
                label = f"{prefix}{slug[:available]}..." if available > 0 else label[:max_length]

            return label
        except Exception:
            return url[:max_length]


@dataclass
class URLBatchStatus:
    """Status tracker for batch URL processing.

    Provides methods to update status, track timing, and calculate estimates.

    Attributes:
        entries: List of URLStatusEntry objects, one per URL
        batch_start_time: Unix timestamp when batch processing started
        _processing_times: List of completed processing times for ETA calculation
    """

    entries: list[URLStatusEntry] = field(default_factory=list)
    batch_start_time: float = field(default_factory=time.time)
    _processing_times: list[float] = field(default_factory=list, repr=False)

    @classmethod
    def from_urls(cls, urls: list[str]) -> URLBatchStatus:
        """Create a batch status tracker from a list of URLs."""
        entries = [URLStatusEntry(url=url) for url in urls]
        return cls(entries=entries)

    def _find_entry(self, url: str) -> URLStatusEntry | None:
        """Find entry by URL."""
        for entry in self.entries:
            if entry.url == url:
                return entry
        return None

    def mark_processing(self, url: str) -> None:
        """Mark a URL as currently processing."""
        entry = self._find_entry(url)
        if entry:
            entry.status = URLStatus.PROCESSING
            entry.start_time = time.time()

    def mark_extracting(self, url: str) -> None:
        """Mark a URL as in the content extraction phase (Firecrawl)."""
        entry = self._find_entry(url)
        if entry:
            entry.status = URLStatus.EXTRACTING
            if entry.start_time is None:
                entry.start_time = time.time()

    def mark_analyzing(self, url: str) -> None:
        """Mark a URL as in the LLM analysis phase."""
        entry = self._find_entry(url)
        if entry:
            entry.status = URLStatus.ANALYZING

    def mark_retrying(self, url: str) -> None:
        """Mark a URL as being retried."""
        entry = self._find_entry(url)
        if entry:
            entry.status = URLStatus.RETRYING

    def mark_complete(
        self,
        url: str,
        *,
        title: str | None = None,
        processing_time_ms: float | None = None,
    ) -> None:
        """Mark a URL as successfully completed.

        Args:
            url: The URL that completed
            title: Optional article title for display
            processing_time_ms: Optional explicit processing time
        """
        entry = self._find_entry(url)
        if entry:
            entry.status = URLStatus.COMPLETE
            entry.title = title

            # Calculate processing time
            if processing_time_ms is not None:
                entry.processing_time_ms = processing_time_ms
            elif entry.start_time:
                entry.processing_time_ms = (time.time() - entry.start_time) * 1000

            # Track for ETA calculation
            if entry.processing_time_ms > 0:
                self._processing_times.append(entry.processing_time_ms)

    def mark_cached(
        self,
        url: str,
        *,
        title: str | None = None,
    ) -> None:
        """Mark a URL as successfully reused from cache.

        Args:
            url: The URL that was found in cache
            title: Optional article title for display
        """
        entry = self._find_entry(url)
        if entry:
            entry.status = URLStatus.CACHED
            entry.title = title
            entry.processing_time_ms = 0.0

    def mark_failed(
        self,
        url: str,
        error_type: str,
        error_message: str,
        *,
        processing_time_ms: float | None = None,
    ) -> None:
        """Mark a URL as failed.

        Args:
            url: The URL that failed
            error_type: Type of error (e.g., "timeout", "network")
            error_message: Human-readable error message
            processing_time_ms: Optional explicit processing time
        """
        entry = self._find_entry(url)
        if entry:
            entry.status = URLStatus.FAILED
            entry.error_type = error_type
            entry.error_message = error_message

            # Calculate processing time
            if processing_time_ms is not None:
                entry.processing_time_ms = processing_time_ms
            elif entry.start_time:
                entry.processing_time_ms = (time.time() - entry.start_time) * 1000

            # Track for ETA calculation (even failures contribute to timing)
            if entry.processing_time_ms > 0:
                self._processing_times.append(entry.processing_time_ms)

    @property
    def total(self) -> int:
        """Total number of URLs in batch."""
        return len(self.entries)

    @property
    def completed(self) -> list[URLStatusEntry]:
        """List of successfully completed entries (including cached)."""
        return [e for e in self.entries if e.status in {URLStatus.COMPLETE, URLStatus.CACHED}]

    @property
    def failed(self) -> list[URLStatusEntry]:
        """List of failed entries."""
        return [e for e in self.entries if e.status == URLStatus.FAILED]

    @property
    def pending(self) -> list[URLStatusEntry]:
        """List of pending entries."""
        return [e for e in self.entries if e.status == URLStatus.PENDING]

    @property
    def processing(self) -> list[URLStatusEntry]:
        """List of currently processing entries (any active phase)."""
        active = {URLStatus.PROCESSING, URLStatus.EXTRACTING, URLStatus.ANALYZING}
        return [e for e in self.entries if e.status in active]

    @property
    def done_count(self) -> int:
        """Number of URLs that are done (completed + cached + failed)."""
        return len(self.completed) + len(self.failed)

    @property
    def success_count(self) -> int:
        """Number of successfully completed URLs (including cached)."""
        return len(self.completed)

    @property
    def fail_count(self) -> int:
        """Number of failed URLs."""
        return len(self.failed)

    @property
    def pending_count(self) -> int:
        """Number of pending URLs."""
        return len(self.pending)

    def average_processing_time_ms(self) -> float:
        """Calculate average processing time in milliseconds."""
        if not self._processing_times:
            return 0.0
        return sum(self._processing_times) / len(self._processing_times)

    def estimate_remaining_time_sec(self) -> float | None:
        """Estimate remaining time in seconds based on average processing time.

        Returns:
            Estimated seconds remaining, or None if insufficient data
        """
        remaining = self.pending_count + len(self.processing)
        if remaining == 0:
            return 0.0

        avg_ms = self.average_processing_time_ms()
        if avg_ms <= 0:
            return None

        # Estimate remaining time
        return (remaining * avg_ms) / 1000.0

    def total_elapsed_time_sec(self) -> float:
        """Calculate total elapsed time since batch started."""
        return time.time() - self.batch_start_time

    def is_complete(self) -> bool:
        """Check if all URLs have been processed."""
        return self.done_count >= self.total
