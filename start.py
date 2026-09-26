#!/usr/bin/env python3
"""OpsDoctor Production Startup & Preflight Launcher.

Initializes environment credentials, verifies Swytchcode connections for
all 6 operational systems (Jira, Slack, Gmail, Notion, PayPal, Stripe),
and launches the FastAPI / Uvicorn application server.
"""

import os
import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Ensure repo root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Load .env file
load_dotenv(dotenv_path=REPO_ROOT / ".env")


def preflight_check():
    """Verify operational integrations and environment credentials."""
    print("=" * 64)
    print(" [+] OpsDoctor - AI Business Operations Platform")
    print("=" * 64)

    # 1. Swytchcode binary
    from packages.adapters.base import find_swytchcode_bin
    swy_bin = find_swytchcode_bin()
    print(f"[*] Swytchcode Binary: {swy_bin}")

    # 2. Check Stripe
    stripe_key = os.getenv("STRIPE_API_KEY")
    if stripe_key:
        print("[+] Stripe: Configured via STRIPE_API_KEY (.env) -> Test mode enabled")
    else:
        print("[!] Stripe: STRIPE_API_KEY not found in .env (run `swytchcode auth connect Stripe` or set STRIPE_API_KEY)")

    # 3. Check PayPal
    pp_client = os.getenv("PAYPAL_SANDBOX_CLIENT_ID")
    pp_secret = os.getenv("PAYPAL_SANDBOX_CLIENT_SECRET")
    if pp_client and pp_secret:
        print("[+] PayPal: Configured via PAYPAL_SANDBOX_CLIENT_ID & SECRET (.env) -> Sandbox enabled")
    else:
        print("[!] PayPal: PAYPAL_SANDBOX credentials not found in .env")

    # 4. Swytchcode auth status check for OAuth2 systems (Jira, Slack, Gmail, Notion)
    try:
        p = subprocess.run([swy_bin, "auth", "status"], capture_output=True, text=True, timeout=10)
        auth_raw = p.stdout.lower()
        for sys_name in ["jira", "slack", "gmail", "notion"]:
            if sys_name in auth_raw:
                print(f"[+] {sys_name.capitalize()}: Connected via Swytchcode OAuth2")
            else:
                print(f"[?] {sys_name.capitalize()}: Check auth status (`swytchcode auth connect {sys_name}`)")
    except Exception as e:
        print(f"[!] Warning checking Swytchcode auth status: {e}")

    # 5. Verify payment providers via UnifiedPaymentManager
    try:
        from packages.adapters.payments.manager import UnifiedPaymentManager
        mgr = UnifiedPaymentManager()
        overview = mgr.get_overview()
        print(f"[+] Payment Gateways Active: {', '.join(overview.providers.keys()).upper()}")
        print(f"    - Total Tracked Volume: ${overview.total_volume:,.2f}")
        print(f"    - Pending Payments Volume: ${overview.total_pending_volume:,.2f}")
    except Exception as e:
        print(f"[!] Warning initializing Payment Manager: {e}")

    print("-" * 64)
    print("[*] Starting Web Server on http://127.0.0.1:8000")
    print("    Open http://127.0.0.1:8000 in your browser to access OpsDoctor.")
    print("=" * 64 + "\n")


def main():
    preflight_check()
    import uvicorn
    uvicorn.run(
        "apps.web.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=False,
    )


if __name__ == "__main__":
    main()
