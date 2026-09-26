"""Base interface for all payment providers in OpsDoctor."""

from abc import ABC, abstractmethod
from typing import List, Optional

from packages.domain.payment import (
    PaymentStatus,
    PaymentTransaction,
    ProviderPaymentSummary,
)


class AbstractPaymentProvider(ABC):
    """Abstract base class defining unified payment operations across all gateways."""

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the unique provider name (e.g. 'paypal', 'stripe')."""
        pass

    @abstractmethod
    def get_connection_status(self) -> str:
        """Return provider status ('connected', 'auth_required', 'error')."""
        pass

    @abstractmethod
    def list_transactions(
        self,
        status: Optional[PaymentStatus] = None,
        limit: int = 50,
    ) -> List[PaymentTransaction]:
        """List transactions optionally filtered by payment status."""
        pass

    @abstractmethod
    def get_transaction(self, transaction_id: str) -> Optional[PaymentTransaction]:
        """Fetch details of a single transaction by its ID."""
        pass

    @abstractmethod
    def get_summary(self) -> ProviderPaymentSummary:
        """Compute aggregated payment metrics for this provider."""
        pass
