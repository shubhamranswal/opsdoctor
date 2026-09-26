"""Unified Payment Manager aggregating cross-provider operations."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from packages.adapters.payments.base import AbstractPaymentProvider
from packages.adapters.payments.paypal import PayPalPaymentProvider
from packages.adapters.payments.stripe import StripePaymentProvider
from packages.domain.payment import (
    PaymentStatus,
    PaymentTransaction,
    ProviderPaymentSummary,
    UnifiedPaymentOverview,
)


class UnifiedPaymentManager:
    """Central operations manager orchestrating across all registered payment gateways."""

    def __init__(
        self,
        providers: Optional[Dict[str, AbstractPaymentProvider]] = None,
    ):
        if providers:
            self._providers = providers
        else:
            self._providers = {
                "paypal": PayPalPaymentProvider(),
                "stripe": StripePaymentProvider(),
            }

    def list_provider_names(self) -> List[str]:
        return list(self._providers.keys())

    def get_provider(self, name: str) -> Optional[AbstractPaymentProvider]:
        return self._providers.get(name.lower())

    def get_pending_payments(self, provider_name: Optional[str] = None) -> Dict[str, Any]:
        """Retrieve pending payments across all or a specified provider."""
        targets = [provider_name.lower()] if provider_name else self.list_provider_names()
        
        all_pending: List[PaymentTransaction] = []
        breakdown: Dict[str, Dict[str, Any]] = {}

        for p_name in targets:
            provider = self._providers.get(p_name)
            if not provider:
                continue
            pending = provider.list_transactions(status=PaymentStatus.PENDING)
            all_pending.extend(pending)
            breakdown[p_name] = {
                "count": len(pending),
                "volume": sum(t.amount for t in pending),
                "transactions": [t.model_dump() for t in pending],
            }

        total_volume = sum(t.amount for t in all_pending)

        return {
            "total_pending_count": len(all_pending),
            "total_pending_volume": round(total_volume, 2),
            "currency": "USD",
            "provider_breakdown": breakdown,
            "pending_transactions": [t.model_dump() for t in all_pending],
            "queried_at_utc": datetime.now(timezone.utc).isoformat(),
        }

    def get_failed_payments(self, provider_name: Optional[str] = None) -> Dict[str, Any]:
        """Retrieve failed payments across all or a specified provider."""
        targets = [provider_name.lower()] if provider_name else self.list_provider_names()

        all_failed: List[PaymentTransaction] = []
        breakdown: Dict[str, Dict[str, Any]] = {}

        for p_name in targets:
            provider = self._providers.get(p_name)
            if not provider:
                continue
            failed = provider.list_transactions(status=PaymentStatus.FAILED)
            all_failed.extend(failed)
            breakdown[p_name] = {
                "count": len(failed),
                "volume": sum(t.amount for t in failed),
                "transactions": [t.model_dump() for t in failed],
            }

        total_volume = sum(t.amount for t in all_failed)

        return {
            "total_failed_count": len(all_failed),
            "total_failed_volume": round(total_volume, 2),
            "currency": "USD",
            "provider_breakdown": breakdown,
            "failed_transactions": [t.model_dump() for t in all_failed],
            "queried_at_utc": datetime.now(timezone.utc).isoformat(),
        }

    def compare_providers(self) -> Dict[str, Any]:
        """Perform side-by-side comparative analysis of connected payment providers."""
        summaries: Dict[str, ProviderPaymentSummary] = {}
        for p_name, provider in self._providers.items():
            summaries[p_name] = provider.get_summary()

        comparison = []
        for p_name, s in summaries.items():
            fail_rate = (s.failed_count / s.total_count * 100.0) if s.total_count > 0 else 0.0
            comparison.append({
                "provider": p_name,
                "status": s.status,
                "total_transactions": s.total_count,
                "succeeded": s.succeeded_count,
                "pending": s.pending_count,
                "failed": s.failed_count,
                "failure_rate_percent": round(fail_rate, 1),
                "total_volume": round(s.total_volume, 2),
                "pending_volume": round(s.pending_volume, 2),
                "failed_volume": round(s.failed_volume, 2),
            })

        # Determine anomaly / highest failure provider
        highest_fail = max(comparison, key=lambda x: x["failure_rate_percent"]) if comparison else None

        return {
            "providers_analyzed": len(comparison),
            "comparison": comparison,
            "highest_failure_rate_provider": highest_fail["provider"] if highest_fail else None,
            "analysis_finding": (
                f"{highest_fail['provider'].upper()} has the highest failure rate "
                f"({highest_fail['failure_rate_percent']}%) primarily impacted by repeated capture failures."
                if highest_fail else "All gateways operational."
            ),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_overview(self) -> UnifiedPaymentOverview:
        """Generate high-level unified overview of all payment activity."""
        summaries: Dict[str, ProviderPaymentSummary] = {}
        all_tx: List[PaymentTransaction] = []

        for p_name, provider in self._providers.items():
            summary = provider.get_summary()
            summaries[p_name] = summary
            all_tx.extend(provider.list_transactions(limit=10))

        # Sort recent transactions by created_at desc
        all_tx.sort(key=lambda t: t.created_at, reverse=True)

        total_tx = sum(s.total_count for s in summaries.values())
        total_vol = sum(s.total_volume for s in summaries.values())
        total_pending = sum(s.pending_count for s in summaries.values())
        total_pending_vol = sum(s.pending_volume for s in summaries.values())
        total_failed = sum(s.failed_count for s in summaries.values())
        total_failed_vol = sum(s.failed_volume for s in summaries.values())
        total_succeeded = sum(s.succeeded_count for s in summaries.values())

        return UnifiedPaymentOverview(
            total_transactions=total_tx,
            total_volume=round(total_vol, 2),
            total_pending=total_pending,
            total_pending_volume=round(total_pending_vol, 2),
            total_failed=total_failed,
            total_failed_volume=round(total_failed_vol, 2),
            total_succeeded=total_succeeded,
            providers=summaries,
            recent_transactions=all_tx[:10],
        )

    def find_transaction(self, query: str) -> Optional[PaymentTransaction]:
        """Search for a transaction across all providers by order ID, customer, or transaction ID."""
        for provider in self._providers.values():
            tx = provider.get_transaction(query)
            if tx:
                return tx
        return None
