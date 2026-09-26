"""Payments API routes providing unified multi-provider financial operations."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query

from packages.adapters.payments.manager import UnifiedPaymentManager
from packages.domain.payment import PaymentStatus

router = APIRouter(prefix="/api/payments", tags=["payments"])

# Shared payment manager
_payment_manager: Optional[UnifiedPaymentManager] = None


def get_payment_manager() -> UnifiedPaymentManager:
    global _payment_manager
    if _payment_manager is None:
        _payment_manager = UnifiedPaymentManager()
    return _payment_manager


@router.get("/overview")
def get_overview() -> Dict[str, Any]:
    """Retrieve high-level cross-provider payment metrics."""
    mgr = get_payment_manager()
    return mgr.get_overview().model_dump()


@router.get("/pending")
def get_pending(provider: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve pending settlements across PayPal and Stripe."""
    mgr = get_payment_manager()
    return mgr.get_pending_payments(provider_name=provider)


@router.get("/failed")
def get_failed(provider: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve failed payments across gateways."""
    mgr = get_payment_manager()
    return mgr.get_failed_payments(provider_name=provider)


@router.get("/compare")
def compare_gateways() -> Dict[str, Any]:
    """Compare performance metrics between PayPal and Stripe."""
    mgr = get_payment_manager()
    return mgr.compare_providers()


@router.get("/transactions")
def list_transactions(
    status: Optional[str] = None,
    provider: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> List[Dict[str, Any]]:
    """List normalized payment transactions with filtering."""
    mgr = get_payment_manager()
    p_status = PaymentStatus(status.lower()) if status else None

    results = []
    targets = [provider.lower()] if provider else mgr.list_provider_names()
    for p_name in targets:
        p = mgr.get_provider(p_name)
        if p:
            txs = p.list_transactions(status=p_status, limit=limit)
            results.extend([t.model_dump() for t in txs])

    results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return results[:limit]
