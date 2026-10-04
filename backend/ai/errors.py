"""Normalized AI provider errors.

Providers raise these so the gateway can make consistent fallback decisions
instead of guessing from raw HTTP/SDK exceptions.
"""
from __future__ import annotations


class AIError(Exception):
    """Base class for all gateway/provider errors.

    ``fallbackable`` tells the gateway whether it should try the next model in
    the configured chain. We never fall back *blindly* on every error.
    """

    code = "ai_error"
    fallbackable = False

    def __init__(self, message: str = "", *, detail: str = ""):
        super().__init__(message or self.code)
        self.message = message or self.code
        self.detail = detail


class ConfigurationError(AIError):
    """Missing API key / misconfigured provider. Not fallbackable."""
    code = "configuration_error"
    fallbackable = False


class AuthError(AIError):
    """401/403 auth failure — retrying another model on the same bad key is pointless."""
    code = "auth_error"
    fallbackable = False


class ModelUnavailable(AIError):
    """Model not found / not enabled on the endpoint (404). Try the next model."""
    code = "model_unavailable"
    fallbackable = True


class RateLimited(AIError):
    """429 — try the next model."""
    code = "rate_limited"
    fallbackable = True


class ProviderServerError(AIError):
    """5xx from the provider. Try the next model."""
    code = "provider_server_error"
    fallbackable = True


class TimeoutError_(AIError):
    code = "timeout"
    fallbackable = True


class ConnectionError_(AIError):
    code = "connection_error"
    fallbackable = True


class MalformedOutput(AIError):
    """Provider replied but output could not be parsed/validated. Try the next model."""
    code = "malformed_output"
    fallbackable = True


class BadRequest(AIError):
    """400 — our request was invalid; another model would likely fail the same way."""
    code = "bad_request"
    fallbackable = False


class NoModelAvailable(AIError):
    """Entire configured chain was exhausted or empty."""
    code = "no_model_available"
    fallbackable = False
