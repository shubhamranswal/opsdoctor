"""Read-only PayPal operational tools executed through Swytchcode.

The rest of OpsDoctor interacts strictly with these functions.
All actual executions are delegated to the Swytchcode CLI kernel.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from .client import PayPalSwytchcodeClient

_default_client: Optional[PayPalSwytchcodeClient] = None


def get_client() -> PayPalSwytchcodeClient:
    """Retrieve or create the singleton PayPal Swytchcode client."""
    global _default_client
    if _default_client is None:
        _default_client = PayPalSwytchcodeClient()
    return _default_client


def paypal_search_transactions(
    start_date: str,
    end_date: str,
    page_size: int = 10,
    page: int = 1,
    client: Optional[PayPalSwytchcodeClient] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Search transactions within a specified date range (UTC ISO-8601 strings).

    Canonical method: transaction_search.reporting.transactions.list
    """
    c = client or get_client()
    args: Dict[str, Any] = {
        "start_date": start_date,
        "end_date": end_date,
        "page_size": page_size,
        "page": page,
    }
    return c.execute("transaction_search.reporting.transactions.list", args=args, dry_run=dry_run)


def paypal_get_transaction(
    capture_id: str,
    client: Optional[PayPalSwytchcodeClient] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Retrieve details for a specific captured transaction by ID.

    Canonical method: payments.payment.captures.get
    """
    c = client or get_client()
    args: Dict[str, Any] = {"capture_id": capture_id}
    return c.execute("payments.payment.captures.get", args=args, dry_run=dry_run)


def paypal_list_disputes(
    page_size: int = 10,
    start_time: Optional[str] = None,
    dispute_state: Optional[str] = None,
    client: Optional[PayPalSwytchcodeClient] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """List customer disputes with optional filtering.

    Canonical method: disputes.customer.disputes.list
    """
    c = client or get_client()
    if not start_time:
        # Default start_time to 90 days ago in ISO-8601 UTC format to override
        # Wrekenfile placeholder default "Current date and time"
        start_time = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    args: Dict[str, Any] = {"page_size": page_size, "start_time": start_time}
    if dispute_state:
        args["dispute_state"] = dispute_state
    return c.execute("disputes.customer.disputes.list", args=args, dry_run=dry_run)


def paypal_get_dispute(
    dispute_id: str,
    client: Optional[PayPalSwytchcodeClient] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Retrieve details for a specific customer dispute by ID.

    Canonical method: disputes.customer.disputes.get
    """
    c = client or get_client()
    args: Dict[str, Any] = {"id": dispute_id}
    return c.execute("disputes.customer.disputes.get", args=args, dry_run=dry_run)


def paypal_get_order(
    order_id: str,
    client: Optional[PayPalSwytchcodeClient] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Retrieve details for a specific checkout order by ID.

    Canonical method: orders.checkout.orders.get
    """
    c = client or get_client()
    args: Dict[str, Any] = {"id": order_id}
    return c.execute("orders.checkout.orders.get", args=args, dry_run=dry_run)


def paypal_get_balances(
    client: Optional[PayPalSwytchcodeClient] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Retrieve account balances from PayPal Sandbox.

    Canonical method: transaction_search.reporting.balances.list
    """
    c = client or get_client()
    return c.execute("transaction_search.reporting.balances.list", args={}, dry_run=dry_run)
