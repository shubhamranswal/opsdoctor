"""PayPal Swytchcode adapter package."""

from .auth import PayPalSandboxTokenManager
from .client import PayPalSwytchcodeClient
from .exceptions import (
    MalformedResponseError,
    MissingCredentialsError,
    PayPalAPIError,
    PayPalError,
    SwytchcodeExecutionError,
    TokenExchangeError,
)
from .tools import (
    get_client,
    paypal_get_balances,
    paypal_get_dispute,
    paypal_get_order,
    paypal_get_transaction,
    paypal_list_disputes,
    paypal_search_transactions,
)

__all__ = [
    "PayPalSandboxTokenManager",
    "PayPalSwytchcodeClient",
    "PayPalError",
    "MissingCredentialsError",
    "TokenExchangeError",
    "SwytchcodeExecutionError",
    "PayPalAPIError",
    "MalformedResponseError",
    "get_client",
    "paypal_search_transactions",
    "paypal_get_transaction",
    "paypal_list_disputes",
    "paypal_get_dispute",
    "paypal_get_order",
    "paypal_get_balances",
]
