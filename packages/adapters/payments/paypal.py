"""PayPal Payment Provider Adapter for OpsDoctor."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from packages.adapters.payments.base import AbstractPaymentProvider
from packages.adapters.paypal import PayPalSwytchcodeClient
from packages.domain.payment import (
    PaymentStatus,
    PaymentTransaction,
    ProviderPaymentSummary,
)

logger = logging.getLogger("opsdoctor.payments.paypal")

MANIFEST_PATH = Path(__file__).resolve().parents[3] / "data" / "fixtures" / "paypal_orders_manifest.json"


class PayPalPaymentProvider(AbstractPaymentProvider):
    """Adapter executing PayPal operations via Swytchcode and sandbox manifest."""

    def __init__(self, client: Optional[PayPalSwytchcodeClient] = None):
        self.client = client or PayPalSwytchcodeClient()

    def get_provider_name(self) -> str:
        return "paypal"

    def get_connection_status(self) -> str:
        return "connected"

    def _load_manifest_orders(self) -> List[Dict[str, Any]]:
        if MANIFEST_PATH.exists():
            try:
                with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("orders", [])
            except Exception as e:
                logger.error("Failed loading PayPal manifest: %s", e)
        return []

    def _normalize_order(self, o: Dict[str, Any]) -> PaymentTransaction:
        captures = o.get("capture_attempts", [])
        has_failed_captures = len(captures) > 0

        status = PaymentStatus.SUCCEEDED
        failure_reason = None

        if has_failed_captures:
            status = PaymentStatus.FAILED
            failure_reason = "ORDER_NOT_APPROVED: Payer has not approved the order for capture (HTTP 422)"
        elif o.get("order_status") == "CREATED" and o.get("phase") == "incident":
            status = PaymentStatus.FAILED
            failure_reason = "Checkout capture abandoned after repeated failures"
        elif o.get("order_status") == "CREATED" and o.get("phase") == "baseline":
            status = PaymentStatus.SUCCEEDED

        amount_val = 0.0
        try:
            amount_val = float(o.get("amount", 0.0))
        except (ValueError, TypeError):
            pass

        return PaymentTransaction(
            id=o.get("order_id", o.get("paypal_order_id", "unknown")),
            provider="paypal",
            provider_transaction_id=o.get("paypal_order_id", "N/A"),
            customer=o.get("customer", "AcmeFlow Customer"),
            amount=amount_val,
            currency=o.get("currency", "USD"),
            status=status,
            created_at=o.get("created_at_utc", ""),
            flow=o.get("flow", "checkout-v2"),
            failure_reason=failure_reason,
            payment_method="paypal_wallet",
            metadata={
                "phase": o.get("phase"),
                "deployment": o.get("deployment"),
                "failed_capture_attempts": len(captures),
                "client_tracking_ref": o.get("client_tracking_ref"),
            },
        )

    def list_transactions(
        self,
        status: Optional[PaymentStatus] = None,
        limit: int = 50,
    ) -> List[PaymentTransaction]:
        raw_orders = self._load_manifest_orders()
        transactions = [self._normalize_order(o) for o in raw_orders]

        if status:
            transactions = [t for t in transactions if t.status == status]

        return transactions[:limit]

    def get_transaction(self, transaction_id: str) -> Optional[PaymentTransaction]:
        raw_orders = self._load_manifest_orders()
        for o in raw_orders:
            if o.get("order_id") == transaction_id or o.get("paypal_order_id") == transaction_id:
                # Optionally attempt live query
                try:
                    pid = o.get("paypal_order_id")
                    live = self.client.execute("orders.checkout.orders.get", {"id": pid})
                    if isinstance(live, dict) and not live.get("error"):
                        merged = {**o, **live}
                        return self._normalize_order(merged)
                except Exception:
                    pass
                return self._normalize_order(o)
        return None

    def get_summary(self) -> ProviderPaymentSummary:
        transactions = self.list_transactions(limit=100)
        succeeded = [t for t in transactions if t.status == PaymentStatus.SUCCEEDED]
        pending = [t for t in transactions if t.status == PaymentStatus.PENDING]
        failed = [t for t in transactions if t.status == PaymentStatus.FAILED]

        return ProviderPaymentSummary(
            provider="paypal",
            status=self.get_connection_status(),
            total_count=len(transactions),
            succeeded_count=len(succeeded),
            pending_count=len(pending),
            failed_count=len(failed),
            total_volume=sum(t.amount for t in transactions),
            pending_volume=sum(t.amount for t in pending),
            failed_volume=sum(t.amount for t in failed),
            currency="USD",
            recent_transactions=transactions[:5],
        )
