"""Unit tests for PayPal Swytchcode adapter."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packages.adapters.paypal.auth import PayPalSandboxTokenManager
from packages.adapters.paypal.client import PayPalSwytchcodeClient
from packages.adapters.paypal.exceptions import (
    MissingCredentialsError,
    PayPalAPIError,
    SwytchcodeExecutionError,
    TokenExchangeError,
)
from packages.adapters.paypal.tools import (
    paypal_get_dispute,
    paypal_get_order,
    paypal_get_transaction,
    paypal_list_disputes,
    paypal_search_transactions,
)


class TestPayPalTokenManager(unittest.TestCase):
    """Test credential validation and caching behavior."""

    def test_missing_credentials_raises(self):
        manager = PayPalSandboxTokenManager(client_id="", client_secret="")
        with self.assertRaises(MissingCredentialsError):
            manager.get_access_token()

    @patch("urllib.request.urlopen")
    def test_token_exchange_success_and_cache(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.getcode.return_value = 200
        mock_response.read.return_value = b'{"access_token": "mock_token_abc", "expires_in": 3600}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        manager = PayPalSandboxTokenManager(client_id="mock_id", client_secret="mock_secret")
        token1 = manager.get_access_token()
        self.assertEqual(token1, "mock_token_abc")
        self.assertEqual(mock_urlopen.call_count, 1)

        # Second call should use cache without hitting network
        token2 = manager.get_access_token()
        self.assertEqual(token2, "mock_token_abc")
        self.assertEqual(mock_urlopen.call_count, 1)

    def test_token_manager_repr_does_not_leak_token(self):
        manager = PayPalSandboxTokenManager(client_id="id", client_secret="sec")
        manager._access_token = "SUPER_SECRET_TOKEN_DO_NOT_PRINT"
        r = repr(manager)
        self.assertNotIn("SUPER_SECRET_TOKEN", r)
        self.assertIn("cached_token=True", r)


class TestPayPalSwytchcodeClientDryRun(unittest.TestCase):
    """Test that all PayPal tools invoke Swytchcode and target PayPal Sandbox."""

    def setUp(self):
        self.token_manager = MagicMock()
        self.token_manager.get_access_token.return_value = "mock_dry_run_token"
        self.client = PayPalSwytchcodeClient(token_manager=self.token_manager, workspace_dir=str(REPO_ROOT))

    def test_paypal_list_disputes_dry_run(self):
        res = paypal_list_disputes(page_size=5, client=self.client, dry_run=True)
        self.assertEqual(res.get("method"), "GET")
        self.assertTrue(res.get("url", "").startswith("https://api-m.sandbox.paypal.com/v1/customer/disputes"))

    def test_paypal_get_dispute_dry_run(self):
        res = paypal_get_dispute("DP-TEST-999", client=self.client, dry_run=True)
        self.assertEqual(res.get("method"), "GET")
        self.assertEqual(res.get("url"), "https://api-m.sandbox.paypal.com/v1/customer/disputes/DP-TEST-999")

    def test_paypal_get_order_dry_run(self):
        res = paypal_get_order("ORD-TEST-999", client=self.client, dry_run=True)
        self.assertEqual(res.get("method"), "GET")
        self.assertEqual(res.get("url"), "https://api-m.sandbox.paypal.com/v2/checkout/orders/ORD-TEST-999")

    def test_paypal_get_transaction_dry_run(self):
        res = paypal_get_transaction("CAP-TEST-999", client=self.client, dry_run=True)
        self.assertEqual(res.get("method"), "GET")
        self.assertEqual(res.get("url"), "https://api-m.sandbox.paypal.com/v2/payments/captures/CAP-TEST-999")

    def test_paypal_search_transactions_dry_run(self):
        res = paypal_search_transactions(
            start_date="2026-09-01T00:00:00Z",
            end_date="2026-09-25T23:59:59Z",
            client=self.client,
            dry_run=True,
        )
        self.assertEqual(res.get("method"), "GET")
        self.assertTrue(res.get("url", "").startswith("https://api-m.sandbox.paypal.com/v1/reporting/transactions"))


if __name__ == "__main__":
    unittest.main()
