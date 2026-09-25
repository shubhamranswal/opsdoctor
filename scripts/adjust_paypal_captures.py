"""Script to execute genuine capture attempts on existing PayPal Sandbox incident orders.

Brings the total failed capture attempts to 7 (> 5 within 15 minutes),
strictly satisfying the Notion policy threshold using genuine live PayPal Sandbox calls.
Preserves existing baseline orders and incident order IDs without modification.
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

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
    PayPalSwytchcodeClient,
)

MANIFEST_PATH = REPO_ROOT / "data" / "fixtures" / "paypal_orders_manifest.json"

def execute_capture(client: PayPalSwytchcodeClient, paypal_id: str, attempt_num: int):
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        res = client.execute("orders.checkout.capture.create", {"id": paypal_id, "body": {}})
        print(f"  [Attempt {attempt_num}] Unexpected success: {res}")
        return {
            "attempt": attempt_num,
            "timestamp": timestamp,
            "status_code": 200,
            "capture_status": res.get("status"),
            "details": res,
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

        debug_id = details.get("debug_id")
        print(f"  [Attempt {attempt_num}] EXPECTED 422: {issue} | debug_id={debug_id} | ts={timestamp}")
        return {
            "attempt": attempt_num,
            "timestamp": timestamp,
            "status_code": err.status_code,
            "error_issue": issue,
            "error_message": err.message,
            "debug_id": debug_id,
        }

def main():
    print("--- 1. Loading existing manifest ---")
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    client = PayPalSwytchcodeClient()

    # Incident orders configuration:
    # ORD-88219 (1LL009468F308113M): 2 attempts (initial + retry)
    # ORD-88225 (3KF38607U24457627): 2 attempts (initial + retry)
    # ORD-88231 (9PN44652X52492116): 2 attempts (initial + retry)
    # ORD-88240 (25B39056JJ708184A): 1 attempt
    # Total = 7 genuine failed capture attempts across the 4 incident orders
    order_attempts_plan = {
        "ORD-88219": 2,
        "ORD-88225": 2,
        "ORD-88231": 2,
        "ORD-88240": 1,
    }

    all_captured_attempts = []
    total_failures = 0

    print("\n--- 2. Executing live capture attempts via Swytchcode ---")
    for order in manifest["orders"]:
        order_ref = order["order_id"]
        if order["phase"] != "incident":
            print(f"Skipping baseline order {order_ref} (untouched)")
            continue

        paypal_id = order["paypal_order_id"]
        needed_attempts = order_attempts_plan.get(order_ref, 1)
        print(f"\nExecuting {needed_attempts} capture attempt(s) on {order_ref} (PayPal ID: {paypal_id})...")

        order["capture_attempts"] = []
        for att in range(1, needed_attempts + 1):
            att_result = execute_capture(client, paypal_id, attempt_num=att)
            order["capture_attempts"].append(att_result)
            all_captured_attempts.append(att_result)
            if att_result.get("status_code") == 422:
                total_failures += 1
            time.sleep(1.0) # 1 second between attempts

    print(f"\nTotal failed capture attempts executed: {total_failures}")

    # Verify time window
    timestamps = [datetime.fromisoformat(a["timestamp"]) for a in all_captured_attempts]
    min_ts = min(timestamps)
    max_ts = max(timestamps)
    duration_seconds = (max_ts - min_ts).total_seconds()
    print(f"Capture window: {min_ts.isoformat()} to {max_ts.isoformat()} ({duration_seconds:.2f} seconds)")

    if duration_seconds > 900:
        print("ERROR: Duration exceeds 15 minutes (900s)!", file=sys.stderr)
        sys.exit(1)
    if total_failures <= 5:
        print("ERROR: Failed attempts <= 5, threshold not met!", file=sys.stderr)
        sys.exit(1)

    print(f"SUCCESS: {total_failures} failures in {duration_seconds:.2f}s (<= 900s). Threshold (>5) satisfied!")

    # Update summary
    manifest["summary"]["failed_capture_attempts"] = total_failures
    manifest["generated_at_utc"] = datetime.now(timezone.utc).isoformat()

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nSuccessfully updated {MANIFEST_PATH}")

    # Read back all 4 incident orders from PayPal Sandbox via Swytchcode to verify state
    print("\n--- 3. Read-back verification from PayPal Sandbox ---")
    for order in manifest["orders"]:
        if order["phase"] == "incident":
            pid = order["paypal_order_id"]
            ref = order["order_id"]
            res = client.execute("orders.checkout.orders.get", {"id": pid})
            print(f"Order {ref} ({pid}) status in PayPal Sandbox: {res.get('status')} | Verified.")

if __name__ == "__main__":
    main()
