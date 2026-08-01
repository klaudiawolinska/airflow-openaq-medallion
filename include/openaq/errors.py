"""Exception hierarchy for the OpenAQ v3 client.

Retryable failures derive from ``OpenAQRetryableError`` so callers can retry
without inspecting HTTP status codes.
"""


class OpenAQError(Exception):
    """Base for every error raised by the OpenAQ client."""


class OpenAQRetryableError(OpenAQError):
    """A failure that may succeed on a later attempt."""


class OpenAQTransportError(OpenAQRetryableError):
    """Transport failure such as a timeout, DNS error or connection reset."""


class OpenAQServerError(OpenAQRetryableError):
    """The API returned a 5xx response."""

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class OpenAQRateLimitError(OpenAQRetryableError):
    """The API returned 429.

    ``retry_after`` contains the server's suggested delay in seconds, if
    available.
    """

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class OpenAQAuthError(OpenAQError):
    """The API returned 401/403 — missing, invalid or revoked API key."""


class OpenAQRequestError(OpenAQError):
    """The API rejected the request (4xx other than 401/403/429)."""

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class OpenAQResponseError(OpenAQError):
    """The API returned an unexpected response."""


class OpenAQInvalidJSONResponseError(OpenAQRetryableError):
    """The API returned a response body that could not be decoded as JSON."""
