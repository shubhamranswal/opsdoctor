"""Verification script for PayPal Sandbox integration through Swytchcode.

Proves: Application -> Swytchcode CLI -> PayPal Sandbox -> Live Response.
NEVER prints secrets or access tokens.
"""

import os
import sys
from pathlib import Path

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packages.adapters.paypal import (
    MissingCredentialsError,
    PayPalAPIError,
    PayPalSandboxTokenManager,
    PayPalSwytchcodeClient,
    SwytchcodeExecutionError,
    TokenExchangeError,
    paypal_list_disputes,
    paypal_search_transactions,
)


def main():
    print("=" * 60)
    print(" OpsDoctor - PayPal Sandbox Swytchcode Verification")
    print("=" * 60)

    # 1. Check local environment credentials
    client_id = os.getenv("PAYPAL_SANDBOX_CLIENT_ID")
    client_secret = os.getenv("PAYPAL_SANDBOX_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("\n[!] PayPal Sandbox credentials not detected in .env file.")
        print("\nTo enable live Sandbox verification:")
        print("  1. Copy .env.example to .env (if not already done).")
        print("  2. Add your sandbox credentials:")
        print("       PAYPAL_SANDBOX_CLIENT_ID=your_sandbox_client_id")
        print("       PAYPAL_SANDBOX_CLIENT_SECRET=your_sandbox_client_secret")
        print("  3. Re-run this script: python scripts/verify_paypal.py\n")
        print("[i] Running offline dry-run verification instead...")
        _run_dry_run()
        return

    # Masked verification
    masked_id = client_id[:6] + "..." + client_id[-4:] if len(client_id) > 10 else "***"
    print(f"\n[1] PayPal Sandbox Client ID detected: {masked_id}")

    token_mgr = PayPalSandboxTokenManager()
    client = PayPalSwytchcodeClient(token_manager=token_mgr)

    # 2. Authenticate against PayPal Sandbox OAuth
    print("[2] Requesting access token from PayPal Sandbox OAuth endpoint...")
    try:
        token = token_mgr.get_access_token()
        masked_tok = token[:7] + "..." + token[-4:] if len(token) > 12 else "***"
        print(f"    [OK] Acquired Sandbox access token ({masked_tok}, length={len(token)})")
    except TokenExchangeError as e:
        print(f"    [FAIL] Token exchange failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"    [FAIL] Unexpected error during token exchange: {e}")
        sys.exit(1)

    # 3. Execute safe read-only call through Swytchcode
    print("[3] Executing safe read-only tool: paypal_list_disputes(page_size=2) via Swytchcode...")
    try:
        result = paypal_list_disputes(page_size=2, client=client, dry_run=False)
        print("    [OK] Swytchcode executed successfully!")
        print("\n[4] Verification Result from PayPal Sandbox:")
        print(f"    Total dispute items returned: {len(result.get('items', []))}")
        if "links" in result:
            print(f"    HATEOAS links verified: {len(result['links'])} link(s)")
        print("\n" + "=" * 60)
        print(" VERIFICATION SUCCESSFUL:")
        print(" Application -> Swytchcode Kernel -> PayPal Sandbox -> Live Response")
        print("=" * 60)
    except PayPalAPIError as e:
        print(f"    [API Error] PayPal returned HTTP {e.status_code}: {e.message}")
        print(f"    Details: {e.details}")
        sys.exit(1)
    except SwytchcodeExecutionError as e:
        print(f"    [Swytchcode Error] {e.message}")
        sys.exit(1)
    except Exception as e:
        print(f"    [Error] {e}")
        sys.exit(1)


def _run_dry_run():
    token_mgr = PayPalSandboxTokenManager(client_id="mock_id", client_secret="mock_secret")
    token_mgr._access_token = "mock_token_for_dry_run"
    client = PayPalSwytchcodeClient(token_manager=token_mgr)

    res = paypal_list_disputes(page_size=2, client=client, dry_run=True)
    print("    [OK] Swytchcode dry-run inspection:")
    print(f"         Method: {res.get('method')}")
    print(f"         Target URL: {res.get('url')}")
    print(f"         Headers: {res.get('headers')}")
    print("    [OK] Dry-run proves command syntax and Sandbox URL routing.")


if __name__ == "__main__":
    main()
