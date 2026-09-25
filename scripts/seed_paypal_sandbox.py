"""Script to seed realistic PayPal Sandbox operational test data for AcmeFlow.

Executes all operations strictly via Swytchcode (PayPalSwytchcodeClient).
Targets only PayPal Sandbox (https://api-m.sandbox.paypal.com).
Generates a secret-free manifest at data/fixtures/paypal_orders_manifest.json.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packages.adapters.paypal import (
    PayPalAPIError,
    PayPalSandboxTokenManager,
    PayPalSwytchcodeClient,
    SwytchcodeExecutionError,
)

CANONICAL_INCIDENT = "INC-2026-042"
CANONICAL_FLOW_V2 = "checkout-v2"
CANONICAL_FLOW_V1 = "checkout-v1"
CANONICAL_DEPLOY = "checkout-api-2026.09.25.3"

# Dataset specification aligned with Slack incident timeline (Sep 25, 2026)
ORDER_DEFINITIONS = [
    # Healthy Baseline (pre-incident morning Sep 25, 2026)
    {
        "order_id": "ORD-88190",
        "customer": "Starlight Analytics",
        "amount": "250.00",
        "currency": "USD",
        "description": "AcmeFlow Starter Annual - Starlight Analytics",
        "flow": CANONICAL_FLOW_V1,
        "phase": "baseline",
        "deploy": "pre-incident",
        "attempt_capture": False,
    },
    {
        "order_id": "ORD-88195",
        "customer": "Beacon Media",
        "amount": "620.00",
        "currency": "USD",
        "description": "AcmeFlow Growth Plan - Beacon Media",
        "flow": CANONICAL_FLOW_V1,
        "phase": "baseline",
        "deploy": "pre-incident",
        "attempt_capture": False,
    },
    {
        "order_id": "ORD-88201",
        "customer": "Zenith Logistics",
        "amount": "1450.00",
        "currency": "USD",
        "description": "AcmeFlow Pro Annual - Zenith Logistics",
        "flow": CANONICAL_FLOW_V2,
        "phase": "baseline",
        "deploy": "pre-incident",
        "attempt_capture": False,
    },
    {
        "order_id": "ORD-88208",
        "customer": "Crestview Health",
        "amount": "310.00",
        "currency": "USD",
        "description": "AcmeFlow Team License - Crestview Health",
        "flow": CANONICAL_FLOW_V1,
        "phase": "baseline",
        "deploy": "pre-incident",
        "attempt_capture": False,
    },
    # Incident Period (post checkout-api-2026.09.25.3 deployment)
    {
        "order_id": "ORD-88219",
        "customer": "BrightPath Labs",
        "amount": "1200.00",
        "currency": "USD",
        "description": "AcmeFlow Annual Subscription - BrightPath Labs",
        "flow": CANONICAL_FLOW_V2,
        "phase": "incident",
        "deploy": CANONICAL_DEPLOY,
        "client_tracking_ref": "PAYID-MZ4910",
        "attempt_capture": True,
        "retry_capture": True,  # Customer tried twice per Priya's support note in Slack
    },
    {
        "order_id": "ORD-88225",
        "customer": "OmniCorp Logistics",
        "amount": "4800.00",
        "currency": "USD",
        "description": "AcmeFlow Enterprise Renewal - OmniCorp Logistics",
        "flow": CANONICAL_FLOW_V2,
        "phase": "incident",
        "deploy": CANONICAL_DEPLOY,
        "attempt_capture": True,
        "retry_capture": False,
    },
    {
        "order_id": "ORD-88231",
        "customer": "NovaTech Systems",
        "amount": "750.00",
        "currency": "USD",
        "description": "AcmeFlow Pro Tier Expansion - NovaTech Systems",
        "flow": CANONICAL_FLOW_V2,
        "phase": "incident",
        "deploy": CANONICAL_DEPLOY,
        "attempt_capture": True,
        "retry_capture": False,
    },
    {
        "order_id": "ORD-88240",
        "customer": "Apex Dynamics",
        "amount": "2400.00",
        "currency": "USD",
        "description": "AcmeFlow Scale Annual - Apex Dynamics",
        "flow": CANONICAL_FLOW_V2,
        "phase": "incident",
        "deploy": CANONICAL_DEPLOY,
        "attempt_capture": True,
        "retry_capture": False,
    },
]


def safety_preflight_check() -> None:
    """Verify that credentials exist and target ONLY PayPal Sandbox."""
    print("\n[Safety Check 1] Verifying environment and Sandbox configuration...")
    token_mgr = PayPalSandboxTokenManager()
    token = token_mgr.get_access_token()
    if not token:
        raise RuntimeError("Failed to obtain PayPal Sandbox access token.")

    masked = token[:6] + "..." + token[-4:] if len(token) > 10 else "***"
    print(f"  [OK] Valid PayPal Sandbox token retrieved: {masked}")

    # Verify manifest.json endpoint
    manifest_path = REPO_ROOT / ".swytchcode" / "integrations" / "manifest.json"
    if manifest_path.exists():
        with open(manifest_path, encoding="utf-8") as f:
            manifest_data = json.load(f)
        orders_bundle = manifest_data.get("PayPal.checkout_orders_v2@2.0", {})
        sb_endpoint = orders_bundle.get("sandbox_endpoint", "")
        if "sandbox.paypal.com" not in sb_endpoint:
            raise RuntimeError(f"Safety violation: sandbox_endpoint is {sb_endpoint}, expected sandbox.paypal.com")
        print(f"  [OK] PayPal checkout orders target verified: {sb_endpoint}")

    # Verify tooling.json mode
    tooling_path = REPO_ROOT / ".swytchcode" / "tooling.json"
    if tooling_path.exists():
        with open(tooling_path, encoding="utf-8") as f:
            tooling_data = json.load(f)
        if tooling_data.get("mode") != "sandbox":
            raise RuntimeError("Safety violation: tooling.json mode is not 'sandbox'")
        print("  [OK] Swytchcode execution mode verified: sandbox")


def seed_orders() -> List[Dict[str, Any]]:
    client = PayPalSwytchcodeClient()
    results = []

    print("\n[Execution] Creating orders in PayPal Sandbox via Swytchcode...")

    for spec in ORDER_DEFINITIONS:
        order_ref = spec["order_id"]
        phase = spec["phase"]
        amount = spec["amount"]
        customer = spec["customer"]

        print(f"\nCreating order {order_ref} ({customer}, ${amount}, phase={phase})...")

        create_payload = {
            "body": {
                "intent": "CAPTURE",
                "purchase_units": [
                    {
                        "reference_id": order_ref,
                        "custom_id": order_ref,
                        "description": spec["description"],
                        "amount": {
                            "currency_code": spec["currency"],
                            "value": amount,
                        },
                    }
                ],
            }
        }

        # 1. Execute order creation in PayPal Sandbox
        order_res = client.execute("orders.checkout.orders.create", create_payload)
        paypal_id = order_res.get("id")
        status = order_res.get("status")
        print(f"  -> Created in PayPal Sandbox: ID={paypal_id}, Status={status}")

        record = {
            "order_id": order_ref,
            "paypal_order_id": paypal_id,
            "customer": customer,
            "amount": amount,
            "currency": spec["currency"],
            "flow": spec["flow"],
            "phase": phase,
            "deployment": spec["deploy"],
            "client_tracking_ref": spec.get("client_tracking_ref"),
            "order_status": status,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "capture_attempts": [],
        }

        # 2. Execute capture attempts if specified (incident period)
        if spec.get("attempt_capture"):
            print(f"  -> Executing capture attempt 1 on PayPal order {paypal_id}...")
            attempt_1 = execute_capture_attempt(client, paypal_id, attempt_num=1)
            record["capture_attempts"].append(attempt_1)

            if spec.get("retry_capture"):
                print(f"  -> Executing capture attempt 2 (retry) on PayPal order {paypal_id}...")
                time.sleep(1)  # Brief pause between retries
                attempt_2 = execute_capture_attempt(client, paypal_id, attempt_num=2)
                record["capture_attempts"].append(attempt_2)

        results.append(record)
        time.sleep(0.5)

    return results


def execute_capture_attempt(client: PayPalSwytchcodeClient, paypal_id: str, attempt_num: int) -> Dict[str, Any]:
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        capture_res = client.execute("orders.checkout.capture.create", {"id": paypal_id, "body": {}})
        status = capture_res.get("status", "UNKNOWN")
        print(f"     [Attempt {attempt_num}] SUCCESS: Capture Status={status}")
        return {
            "attempt": attempt_num,
            "timestamp": timestamp,
            "status_code": 200,
            "capture_status": status,
            "details": capture_res,
        }
    except PayPalAPIError as err:
        details = err.details or {}
        issue = "UNKNOWN_ERROR"
        if "details" in details and isinstance(details["details"], list) and details["details"]:
            issue = details["details"][0].get("issue", err.message)
        elif "name" in details:
            issue = details["name"]
        else:
            issue = err.message

        print(f"     [Attempt {attempt_num}] EXPECTED 422 FAILURE: {issue} ({err.message})")
        return {
            "attempt": attempt_num,
            "timestamp": timestamp,
            "status_code": err.status_code,
            "error_issue": issue,
            "error_message": err.message,
            "debug_id": details.get("debug_id"),
        }


def read_back_verification(client: PayPalSwytchcodeClient, records: List[Dict[str, Any]]) -> None:
    print("\n[Verification] Querying created orders back from PayPal Sandbox...")
    verified_count = 0
    for r in records:
        pid = r["paypal_order_id"]
        order_data = client.execute("orders.checkout.orders.get", {"id": pid})
        fetched_id = order_data.get("id")
        fetched_status = order_data.get("status")
        if fetched_id == pid:
            verified_count += 1
            print(f"  [VERIFIED] Order {r['order_id']} -> PayPal ID: {pid} (Status: {fetched_status})")
        else:
            print(f"  [ERROR] ID mismatch for {r['order_id']}: expected {pid}, got {fetched_id}")

    print(f"\nSuccessfully verified {verified_count}/{len(records)} orders via PayPal Sandbox API.")


def write_fixture_manifest(records: List[Dict[str, Any]]) -> Path:
    fixtures_dir = REPO_ROOT / "data" / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = fixtures_dir / "paypal_orders_manifest.json"

    manifest_content = {
        "incident_id": CANONICAL_INCIDENT,
        "payment_flow": CANONICAL_FLOW_V2,
        "deployment_id": CANONICAL_DEPLOY,
        "environment": "sandbox",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_orders": len(records),
            "baseline_orders": len([r for r in records if r["phase"] == "baseline"]),
            "incident_orders": len([r for r in records if r["phase"] == "incident"]),
            "failed_capture_attempts": sum(
                len([a for a in r["capture_attempts"] if a["status_code"] >= 400])
                for r in records
            ),
        },
        "orders": records,
    }

    with open(fixture_path, "w", encoding="utf-8") as f:
        json.dump(manifest_content, f, indent=2)

    print(f"\n[Fixture Saved] Secret-free manifest written to: {fixture_path}")
    return fixture_path


def audit_fixture_security(fixture_path: Path) -> None:
    print("\n[Security Audit] Scanning fixture for sensitive tokens or credentials...")
    content = fixture_path.read_text(encoding="utf-8").lower()
    suspicious = []
    for pattern in ["client_secret", "secret", "bearer", "access_token", "password"]:
        # Allow benign keys if any
        if pattern in content:
            suspicious.append(pattern)

    if not suspicious:
        print("  [PASSED] Manifest is completely free of credentials, tokens, and secrets.")
    else:
        print(f"  [WARNING] Suspicious words found in fixture: {suspicious}")


def main():
    print("=" * 65)
    print(" OpsDoctor - PayPal Sandbox Test Data Generation")
    print("=" * 65)

    safety_preflight_check()
    records = seed_orders()

    client = PayPalSwytchcodeClient()
    read_back_verification(client, records)

    fixture_path = write_fixture_manifest(records)
    audit_fixture_security(fixture_path)

    print("\n" + "=" * 65)
    print(" PAYPAL TEST DATA GENERATION COMPLETE")
    print("=" * 65)


if __name__ == "__main__":
    main()
