"""Stripe Payment Provider Adapter for OpsDoctor."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from packages.adapters.base import BaseSwytchcodeClient
from packages.adapters.payments.base import AbstractPaymentProvider
from packages.domain.payment import (
    PaymentStatus,
    PaymentTransaction,
    ProviderPaymentSummary,
)

logger = logging.getLogger("opsdoctor.payments.stripe")

MANIFEST_PATH = Path(__file__).resolve().parents[3] / "data" / "fixtures" / "stripe_payments_manifest.json"


class StripePaymentProvider(AbstractPaymentProvider):
    """Adapter executing Stripe operations via Swytchcode with fixture resilience."""

    def __init__(self, client: Optional[BaseSwytchcodeClient] = None):
        self.client = client or BaseSwytchcodeClient()
        self._auth_blocker: Optional[str] = None
        self._check_swytchcode_status()

    def _check_swytchcode_status(self):
        """Check if Stripe credentials are configured in Swytchcode."""
        try:
            res = self.client.execute("stripe.payment_intent.list", args={"limit": 1})
            if isinstance(res, dict) and res.get("category") == "auth":
                self._auth_blocker = "missing credentials for Stripe - run `swytchcode auth connect Stripe`"
            else:
                self._auth_blocker = None
        except Exception as e:
            err_str = str(e)
            if "missing credentials" in err_str or "auth connect" in err_str:
                self._auth_blocker = "missing credentials for Stripe - run `swytchcode auth connect Stripe`"
            else:
                logger.warning("Stripe check warning: %s", e)
                self._auth_blocker = None

    def get_provider_name(self) -> str:
        return "stripe"

    def get_connection_status(self) -> str:
        if self._auth_blocker:
            return "ready_for_auth"
        return "connected"

    def get_auth_blocker(self) -> Optional[str]:
        return self._auth_blocker

    def _normalize_payment(self, p: Dict[str, Any]) -> PaymentTransaction:
        raw_status = str(p.get("status", "succeeded")).lower()
        has_error = bool(p.get("last_payment_error"))

        if raw_status == "succeeded":
            status = PaymentStatus.SUCCEEDED
        elif raw_status in ("requires_action", "processing", "requires_capture"):
            status = PaymentStatus.PENDING
        elif raw_status == "requires_payment_method":
            status = PaymentStatus.FAILED if has_error else PaymentStatus.PENDING
        elif raw_status == "canceled":
            status = PaymentStatus.CANCELLED
        elif raw_status in ("failed", "failure"):
            status = PaymentStatus.FAILED
        else:
            status = PaymentStatus.PENDING

        # Stripe amounts are in integer cents for standard currencies
        raw_amt = p.get("amount", 0.0)
        try:
            amount_val = float(raw_amt) / 100.0 if isinstance(raw_amt, (int, float)) and raw_amt > 10 else float(raw_amt)
        except (ValueError, TypeError):
            amount_val = 0.0

        metadata = p.get("metadata") or {}
        created_val = p.get("created")
        created_at_str = ""
        if isinstance(created_val, (int, float)):
            from datetime import datetime, timezone
            created_at_str = datetime.fromtimestamp(created_val, tz=timezone.utc).isoformat()
        else:
            created_at_str = str(p.get("created_at_utc", ""))

        failure_reason = None
        if p.get("last_payment_error"):
            err_obj = p["last_payment_error"]
            failure_reason = err_obj.get("message") or err_obj.get("code") or "card_declined"

        customer_name = metadata.get("customer_name") or metadata.get("org") or p.get("customer") or "Stripe Customer"
        flow_name = metadata.get("flow") or "checkout-v2"

        return PaymentTransaction(
            id=p.get("id", "unknown"),
            provider="stripe",
            provider_transaction_id=p.get("id", "N/A"),
            customer=customer_name,
            customer_email=p.get("customer_email"),
            amount=round(amount_val, 2),
            currency=p.get("currency", "USD").upper(),
            status=status,
            created_at=created_at_str,
            flow=flow_name,
            failure_reason=failure_reason,
            payment_method=p.get("payment_method") or "card",
            metadata={
                "description": p.get("description"),
                "raw_status": raw_status,
                "object": p.get("object", "payment_intent"),
                "auth_blocker": self._auth_blocker,
                "metadata": metadata,
            },
        )

    def list_transactions(
        self,
        status: Optional[PaymentStatus] = None,
        limit: int = 50,
    ) -> List[PaymentTransaction]:
        raw_payments = []
        if not self._auth_blocker:
            try:
                res = self.client.execute("stripe.payment_intent.list", args={"limit": limit})
                if isinstance(res, dict) and "data" in res:
                    raw_payments = res["data"]
            except Exception as e:
                logger.error("Failed to list live Stripe payment intents: %s", e)
                raw_payments = []
        else:
            raw_payments = []

        transactions = [self._normalize_payment(p) for p in raw_payments]

        if status:
            transactions = [t for t in transactions if t.status == status]

        return transactions[:limit]

    def get_transaction(self, transaction_id: str) -> Optional[PaymentTransaction]:
        if not self._auth_blocker:
            try:
                res = self.client.execute("stripe.payment_intent.get", args={"intent": transaction_id})
                if isinstance(res, dict) and not res.get("error"):
                    return self._normalize_payment(res)
            except Exception as e:
                logger.warning("Live Stripe get_transaction failed for %s: %s", transaction_id, e)

        # Fallback to search in list
        for t in self.list_transactions(limit=100):
            if t.id == transaction_id:
                return t
        return None


    def get_summary(self) -> ProviderPaymentSummary:
        transactions = self.list_transactions(limit=100)
        succeeded = [t for t in transactions if t.status == PaymentStatus.SUCCEEDED]
        pending = [t for t in transactions if t.status == PaymentStatus.PENDING]
        failed = [t for t in transactions if t.status == PaymentStatus.FAILED]

        return ProviderPaymentSummary(
            provider="stripe",
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
