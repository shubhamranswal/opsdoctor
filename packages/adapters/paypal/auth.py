"""Secure PayPal Sandbox token manager."""

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional
from dotenv import load_dotenv

from .exceptions import MissingCredentialsError, TokenExchangeError

# Ensure environment variables are loaded
load_dotenv()

SANDBOX_OAUTH_TOKEN_URL = "https://api-m.sandbox.paypal.com/v1/oauth2/token"


class PayPalSandboxTokenManager:
    """Manages acquisition and in-memory caching of PayPal Sandbox OAuth2 access tokens."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        token_url: str = SANDBOX_OAUTH_TOKEN_URL,
    ):
        self._client_id = client_id if client_id is not None else os.getenv("PAYPAL_SANDBOX_CLIENT_ID")
        self._client_secret = client_secret if client_secret is not None else os.getenv("PAYPAL_SANDBOX_CLIENT_SECRET")
        self._token_url = token_url
        self._access_token: Optional[str] = None
        self._expires_at: float = 0.0

    def get_access_token(self, force_refresh: bool = False) -> str:
        """Return a valid sandbox access token, refreshing if expired or requested."""
        now = time.time()
        # Return cached token if present and not expired/forced
        if not force_refresh and self._access_token:
            if self._expires_at == 0.0 or (now < self._expires_at - 60):
                return self._access_token

        if not self._client_id or not self._client_secret:
            raise MissingCredentialsError(
                "Missing PayPal Sandbox credentials. Set PAYPAL_SANDBOX_CLIENT_ID "
                "and PAYPAL_SANDBOX_CLIENT_SECRET in your .env file."
            )

        return self._fetch_token()

    def invalidate_token(self) -> None:
        """Invalidate currently cached token, forcing a refresh on next call."""
        self._access_token = None
        self._expires_at = 0.0

    def _fetch_token(self) -> str:
        """Exchange client credentials for an access token via PayPal Sandbox OAuth endpoint."""
        credentials = f"{self._client_id}:{self._client_secret}".encode("utf-8")
        basic_auth = base64.b64encode(credentials).decode("ascii")

        headers = {
            "Authorization": f"Basic {basic_auth}",
            "Accept": "application/json",
            "Accept-Language": "en_US",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode("utf-8")

        req = urllib.request.Request(self._token_url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                status_code = resp.getcode()
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8")
            except Exception:
                pass
            raise TokenExchangeError(
                f"Failed to obtain PayPal Sandbox access token: HTTP {e.code}. "
                f"Check that PAYPAL_SANDBOX_CLIENT_ID and PAYPAL_SANDBOX_CLIENT_SECRET are valid.",
                details={"status_code": e.code, "error_body": error_body},
            ) from None
        except Exception as e:
            raise TokenExchangeError(
                f"Network error communicating with PayPal Sandbox OAuth endpoint: {e}"
            ) from e

        try:
            payload = json.loads(body)
            access_token = payload.get("access_token")
            expires_in = int(payload.get("expires_in", 32400))
            if not access_token:
                raise TokenExchangeError(
                    "PayPal Sandbox OAuth response did not contain an access_token."
                )

            self._access_token = access_token
            self._expires_at = time.time() + expires_in
            return access_token
        except json.JSONDecodeError as e:
            raise TokenExchangeError("Malformed JSON received from PayPal token endpoint.") from e

    def __repr__(self) -> str:
        cached = bool(self._access_token)
        return f"<PayPalSandboxTokenManager (cached_token={cached})>"
