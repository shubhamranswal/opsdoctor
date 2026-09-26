"""Domain models for payments and cross-provider financial operations."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PaymentStatus(str, Enum):
    SUCCEEDED = "succeeded"
    PENDING = "pending"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class PaymentTransaction(BaseModel):
    """Normalized cross-provider payment transaction."""
    id: str  # Provider transaction or internal order ID
    provider: str  # "paypal" or "stripe"
    provider_transaction_id: str  # Real provider ID (e.g. pi_..., 8AT...)
    customer: str
    customer_email: Optional[str] = None
    amount: float
    currency: str = "USD"
    status: PaymentStatus
    created_at: str
    flow: Optional[str] = None  # e.g., "checkout-v2", "enterprise-billing", "checkout-v1"
    failure_reason: Optional[str] = None
    payment_method: Optional[str] = None  # "card", "paypal_wallet", "ach_debit"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProviderPaymentSummary(BaseModel):
    """Aggregated payment metrics for a specific payment provider."""
    provider: str
    status: str  # "connected", "ready_for_auth", "error"
    total_count: int = 0
    succeeded_count: int = 0
    pending_count: int = 0
    failed_count: int = 0
    total_volume: float = 0.0
    pending_volume: float = 0.0
    failed_volume: float = 0.0
    currency: str = "USD"
    recent_transactions: List[PaymentTransaction] = Field(default_factory=list)


class UnifiedPaymentOverview(BaseModel):
    """Normalized multi-provider payment landscape."""
    total_transactions: int
    total_volume: float
    total_pending: int
    total_pending_volume: float
    total_failed: int
    total_failed_volume: float
    total_succeeded: int
    currency: str = "USD"
    providers: Dict[str, ProviderPaymentSummary]
    recent_transactions: List[PaymentTransaction]
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
