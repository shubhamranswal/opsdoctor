"""Custom exceptions for PayPal Swytchcode adapter."""


class PayPalError(Exception):
    """Base exception for all PayPal adapter errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(message={self.message!r})"

    def __str__(self) -> str:
        return self.message


class MissingCredentialsError(PayPalError):
    """Raised when required PayPal sandbox credentials are missing from the environment."""
    pass


class TokenExchangeError(PayPalError):
    """Raised when obtaining an access token from PayPal Sandbox fails."""
    pass


class SwytchcodeExecutionError(PayPalError):
    """Raised when Swytchcode CLI execution fails or exits non-zero."""
    pass


class PayPalAPIError(PayPalError):
    """Raised when PayPal Sandbox API returns an error HTTP status code."""

    def __init__(self, status_code: int, message: str, details: dict | None = None):
        super().__init__(f"PayPal API error HTTP {status_code}: {message}", details)
        self.status_code = status_code


class MalformedResponseError(PayPalError):
    """Raised when the response from Swytchcode cannot be parsed as valid JSON."""
    pass
