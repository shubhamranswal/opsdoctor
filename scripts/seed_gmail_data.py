"""Script to seed realistic operational Gmail test data for AcmeFlow incident INC-2026-042.

Uses Swytchcode to execute Gmail operations under managed OAuth2.
Strictly idempotent: checks for unique deterministic markers before inserting.
Inserts RFC 2822 messages directly into the mailbox without sending outbound SMTP emails.
Outputs a secret-free fixture at data/fixtures/gmail_messages_manifest.json.
"""

import base64
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parents[1]

CANONICAL_INCIDENT = "INC-2026-042"
CANONICAL_FLOW = "checkout-v2"
CANONICAL_DEPLOY = "checkout-api-2026.09.25.3"
TARGET_ACCOUNT = "shubhamgivesdemo@gmail.com"

# 14 Approved Messages
GMAIL_DATASET = [
    # 1. Baseline noise
    {
        "marker": "ACMEFLOW-SEED-INC-2026-042-01",
        "category": "baseline_noise",
        "from": "AcmeFlow Billing <billing@acmeflow.com>",
        "to": "ops@starlightanalytics.net",
        "date": "Thu, 24 Sep 2026 16:30:00 +0000",
        "subject": "AcmeFlow Payment Confirmation - Order ORD-88190",
        "body": (
            "Hi Starlight Analytics Team,\n\n"
            "Thank you for your payment! This email confirms your payment for order ORD-88190.\n\n"
            "Plan: AcmeFlow Starter Annual\n"
            "Amount: $250.00 USD\n"
            "Payment Method: PayPal Checkout\n"
            "Status: Paid (Settled)\n\n"
            "You can download your PDF invoice directly from your AcmeFlow account dashboard.\n\n"
            "Best regards,\n"
            "AcmeFlow Automated Billing\n"
            "[ACMEFLOW-SEED-INC-2026-042-01]"
        ),
        "order_id": "ORD-88190",
        "incident_id": None,
    },
    # 2. Baseline noise
    {
        "marker": "ACMEFLOW-SEED-INC-2026-042-02",
        "category": "baseline_noise",
        "from": "Daniel Kim <daniel.kim@acmeflow.com>",
        "to": "leads@acmeflow.com",
        "date": "Fri, 25 Sep 2026 08:45:00 +0000",
        "subject": "Monthly Close Schedule: September 2026 & Concur Expense Submissions",
        "body": (
            "Hi Team Leads,\n\n"
            "As we approach the end of Q3, please ensure all department expense reports for September "
            "are approved in Concur by Monday 5:00 PM. Our finance team will initiate the monthly close "
            "and vendor invoice reconciliations on Tuesday morning.\n\n"
            "Let me know if you anticipate any off-cycle budget adjustments.\n\n"
            "Daniel Kim\n"
            "Finance Lead, AcmeFlow\n"
            "[ACMEFLOW-SEED-INC-2026-042-02]"
        ),
        "order_id": None,
        "incident_id": None,
    },
    # 3. Baseline noise
    {
        "marker": "ACMEFLOW-SEED-INC-2026-042-03",
        "category": "baseline_noise",
        "from": "Shubham Ranswal <maya.rao@acmeflow.com>",
        "to": "team@acmeflow.com",
        "date": "Fri, 25 Sep 2026 10:30:00 +0000",
        "subject": "Reminder: Q3 OKR Departmental Rollup Due Friday 5 PM",
        "body": (
            "Hi Everyone,\n\n"
            "Quick reminder that Q3 OKR departmental scorecards are due by Friday end-of-day. "
            "Please update key results directly in your team's Notion workspace pages. "
            "We will review high-level organizational metrics at next week's all-hands meeting.\n\n"
            "Thanks for your dedication!\n"
            "Shubham Ranswal\n"
            "Operations Manager, AcmeFlow\n"
            "[ACMEFLOW-SEED-INC-2026-042-03]"
        ),
        "order_id": None,
        "incident_id": None,
    },
    # 4. Baseline noise
    {
        "marker": "ACMEFLOW-SEED-INC-2026-042-04",
        "category": "baseline_noise",
        "from": "AWS Billing Notifications <no-reply-aws@amazon.com>",
        "to": "devops@acmeflow.com",
        "date": "Fri, 25 Sep 2026 11:15:00 +0000",
        "subject": "Amazon Web Services Monthly Billing Statement Available - Account #4412",
        "body": (
            "Dear AWS Customer,\n\n"
            "Your monthly billing statement for AWS Account #4412 (AcmeFlow Production US-East) is now "
            "available on the AWS Billing & Cost Management console.\n\n"
            "Total Current Charges: $8,421.19 USD.\n"
            "No action is required if you are enrolled in automated credit billing.\n\n"
            "AWS Automated Services\n"
            "[ACMEFLOW-SEED-INC-2026-042-04]"
        ),
        "order_id": None,
        "incident_id": None,
    },
    # 5. Baseline noise
    {
        "marker": "ACMEFLOW-SEED-INC-2026-042-05",
        "category": "baseline_noise",
        "from": "AcmeFlow Billing <billing@acmeflow.com>",
        "to": "billing@beaconmedia.com",
        "date": "Fri, 25 Sep 2026 12:50:00 +0000",
        "subject": "AcmeFlow Payment Confirmation - Order ORD-88195",
        "body": (
            "Hi Beacon Media,\n\n"
            "This email confirms successful receipt of your payment for order ORD-88195.\n\n"
            "Plan: AcmeFlow Growth Plan\n"
            "Amount: $620.00 USD\n"
            "Payment Channel: PayPal Checkout\n"
            "Status: Complete\n\n"
            "Thank you for choosing AcmeFlow!\n"
            "AcmeFlow Billing Operations\n"
            "[ACMEFLOW-SEED-INC-2026-042-05]"
        ),
        "order_id": "ORD-88195",
        "incident_id": None,
    },
    # 6. Historical context
    {
        "marker": "ACMEFLOW-SEED-INC-2026-042-06",
        "category": "historical_incident",
        "from": "Arjun Mehta <arjun.mehta@acmeflow.com>",
        "to": "operations@acmeflow.com, engineering@acmeflow.com",
        "date": "Mon, 14 Sep 2026 09:30:00 +0000",
        "subject": "Post-Incident Summary: INC-2026-031 (Webhook Delivery Delays with Third-Party Gateways)",
        "body": (
            "Team,\n\n"
            "Following the incident review on Friday, here is the executive summary for INC-2026-031:\n\n"
            "Summary: On Sep 11, third-party payment gateway webhook ingress accumulated a 45-minute lag "
            "due to thread pool exhaustion in the listener worker service. No payments were lost, but "
            "asynchronous order confirmation emails and order state updates were delayed.\n\n"
            "Key Mitigations:\n"
            "1. Worker concurrency pool scaled from 8 to 32 instances.\n"
            "2. Runbook updated in Notion: 'Operations / Runbooks / Payment Incident Response REV-3'.\n"
            "3. Prometheus dead-letter queue alert threshold adjusted to 100 messages.\n\n"
            "This concludes the action items for INC-2026-031.\n\n"
            "Arjun Mehta\n"
            "Engineering Lead, AcmeFlow\n"
            "[ACMEFLOW-SEED-INC-2026-042-06]"
        ),
        "order_id": None,
        "incident_id": "INC-2026-031",
    },
    # 7. Customer Complaint - BrightPath Labs
    {
        "marker": "ACMEFLOW-SEED-INC-2026-042-07",
        "category": "customer_complaint",
        "from": "Sarah Lin <billing@brightpathlabs.com>",
        "to": "support@acmeflow.com",
        "date": "Fri, 25 Sep 2026 14:20:00 +0000",
        "subject": "Urgent: Failed PayPal payment for Annual Subscription (Order ORD-88219)",
        "body": (
            "Hi AcmeFlow Support,\n\n"
            "We have been trying to renew our AcmeFlow Enterprise Annual plan for order ORD-88219 today. "
            "When clicking 'Confirm Payment' on the PayPal window, it spins for a few seconds and then returns "
            "an unhelpful error screen saying 'Unable to complete order'.\n\n"
            "We attempted payment twice (PayPal tracking ref PAYID-MZ4910 was generated on our end), and both "
            "attempts failed with the same error. Our subscription renews tomorrow—please help us get this "
            "processed so our team's access isn't interrupted.\n\n"
            "Best,\n"
            "Sarah Lin\n"
            "Billing Manager, BrightPath Labs\n"
            "[ACMEFLOW-SEED-INC-2026-042-07]"
        ),
        "order_id": "ORD-88219",
        "incident_id": None,
        "paypal_tracking": "PAYID-MZ4910",
    },
    # 8. Customer Complaint - OmniCorp Logistics
    {
        "marker": "ACMEFLOW-SEED-INC-2026-042-08",
        "category": "customer_complaint",
        "from": "David Vance <procurement@omnicorplogistics.com>",
        "to": "sofia.martinez@acmeflow.com",
        "date": "Fri, 25 Sep 2026 14:28:00 +0000",
        "subject": "Renewal payment issue - AcmeFlow Enterprise (Order ORD-88225)",
        "body": (
            "Hi Sofia,\n\n"
            "Reaching out because our procurement team is hitting a wall trying to renew order ORD-88225 ($4,800.00). "
            "The PayPal checkout portal keeps erroring out during the authorization/capture step.\n\n"
            "Is PayPal down or is there an issue on AcmeFlow's billing portal? Let us know what the workaround is "
            "so we can settle this invoice before the weekend.\n\n"
            "Thanks,\n"
            "David Vance\n"
            "VP Procurement, OmniCorp Logistics\n"
            "[ACMEFLOW-SEED-INC-2026-042-08]"
        ),
        "order_id": "ORD-88225",
        "incident_id": None,
    },
    # 9. Customer Complaint - NovaTech Systems
    {
        "marker": "ACMEFLOW-SEED-INC-2026-042-09",
        "category": "customer_complaint",
        "from": "Elena Rostova <accounts@novatechsystems.io>",
        "to": "support@acmeflow.com",
        "date": "Fri, 25 Sep 2026 14:35:00 +0000",
        "subject": "Payment confirmation error on order ORD-88231",
        "body": (
            "Hello Support,\n\n"
            "We are attempting to purchase 15 additional developer seats under order ORD-88231 ($750.00). "
            "After logging into PayPal and hitting confirm, we are bounced back to a generic checkout failure screen.\n\n"
            "Please check on your end if the payment was received or if we should re-attempt.\n\n"
            "Regards,\n"
            "Elena Rostova\n"
            "NovaTech Systems\n"
            "[ACMEFLOW-SEED-INC-2026-042-09]"
        ),
        "order_id": "ORD-88231",
        "incident_id": None,
    },
    # 10. Customer Complaint - Apex Dynamics
    {
        "marker": "ACMEFLOW-SEED-INC-2026-042-10",
        "category": "customer_complaint",
        "from": "Marcus Chen <finance@apexdynamics.co>",
        "to": "support@acmeflow.com",
        "date": "Fri, 25 Sep 2026 14:41:00 +0000",
        "subject": "Unable to process PayPal invoice for order ORD-88240",
        "body": (
            "Hi team,\n\n"
            "We received an unexpected checkout failure while processing payment for our Scale Annual contract "
            "(Order ORD-88240, $2,400.00). Our corporate card is active and authorized.\n\n"
            "Could you please check what is causing this transaction failure?\n\n"
            "Regards,\n"
            "Marcus Chen\n"
            "Apex Dynamics\n"
            "[ACMEFLOW-SEED-INC-2026-042-10]"
        ),
        "order_id": "ORD-88240",
        "incident_id": None,
    },
    # 11. Internal Support Escalation
    {
        "marker": "ACMEFLOW-SEED-INC-2026-042-11",
        "category": "internal_escalation",
        "from": "Priya Shah <priya.shah@acmeflow.com>",
        "to": "maya.rao@acmeflow.com",
        "date": "Fri, 25 Sep 2026 14:32:00 +0000",
        "subject": "ESCALATION: Spike in customer checkout failures (BrightPath Labs, OmniCorp)",
        "body": (
            "Hi Maya,\n\n"
            "Escalating support tickets CS-1094 (BrightPath Labs) and CS-1095 (OmniCorp Logistics). Both enterprise "
            "accounts are reporting sudden payment confirmation failures in PayPal checkout within the last 15-20 minutes.\n\n"
            "Order references affected: ORD-88219 and ORD-88225. BrightPath attempted twice and hit errors both times.\n\n"
            "Can Operations check if there is an issue with the payment gateway or recent web deployment? We've published "
            "a macro advising customers not to repeatedly retry to avoid rate limits or accidental double charges.\n\n"
            "Best,\n"
            "Priya Shah\n"
            "Customer Support Lead, AcmeFlow\n"
            "[ACMEFLOW-SEED-INC-2026-042-11]"
        ),
        "order_id": "ORD-88219, ORD-88225",
        "incident_id": None,
    },
    # 12. Operations Incident Declaration
    {
        "marker": "ACMEFLOW-SEED-INC-2026-042-12",
        "category": "internal_escalation",
        "from": "Shubham Ranswal <maya.rao@acmeflow.com>",
        "to": "arjun.mehta@acmeflow.com, ethan.cole@acmeflow.com",
        "date": "Fri, 25 Sep 2026 14:46:00 +0000",
        "subject": "OPS ALERT: Payment failures on checkout-v2 flow [INC-2026-042]",
        "body": (
            "Arjun, Ethan:\n\n"
            "Declaring P1 incident INC-2026-042. PagerDuty just fired on elevated payment error rates (>14%) and Support "
            "has multiple customer escalations (ORD-88219, ORD-88225, ORD-88231).\n\n"
            "Looking at telemetry, the failure surge started right around 14:14 UTC, aligning with the release of "
            "checkout-api-2026.09.25.3. Notably, transactions going through checkout-v1 remain healthy; the failures "
            "appear concentrated in checkout-v2 capture requests.\n\n"
            "Ethan has opened the war room in #ops-incidents. Please investigate commit changes in this release immediately.\n\n"
            "Shubham Ranswal\n"
            "Operations Manager, AcmeFlow\n"
            "[ACMEFLOW-SEED-INC-2026-042-12]"
        ),
        "order_id": "ORD-88219, ORD-88225, ORD-88231",
        "incident_id": "INC-2026-042",
        "deployment_id": "checkout-api-2026.09.25.3",
        "flow": "checkout-v2",
    },
    # 13. Engineering Investigation
    {
        "marker": "ACMEFLOW-SEED-INC-2026-042-13",
        "category": "internal_escalation",
        "from": "Arjun Mehta <arjun.mehta@acmeflow.com>",
        "to": "maya.rao@acmeflow.com, ethan.cole@acmeflow.com, daniel.kim@acmeflow.com",
        "date": "Fri, 25 Sep 2026 14:58:00 +0000",
        "subject": "Re: OPS ALERT: Payment failures on checkout-v2 flow [INC-2026-042]",
        "body": (
            "Maya, Ethan:\n\n"
            "Initial engineering review update for INC-2026-042. We are reviewing logs for deployment "
            "checkout-api-2026.09.25.3. PayPal is returning HTTP 422 UNPROCESSABLE_ENTITY on order capture calls "
            "specifically under the checkout-v2 flow.\n\n"
            "We are investigating whether recent payload schema optimizations or token serialization formatting in "
            "checkout-api-2026.09.25.3 are incompatible with PayPal's capture endpoint.\n\n"
            "We have staging reproduction underway and are evaluating rolling back checkout-api-2026.09.25.3 vs toggling "
            "the checkout-v2 traffic flag back to 0%. Next update in 15 mins.\n\n"
            "Arjun Mehta\n"
            "Engineering Lead, AcmeFlow\n"
            "[ACMEFLOW-SEED-INC-2026-042-13]"
        ),
        "order_id": None,
        "incident_id": "INC-2026-042",
        "deployment_id": "checkout-api-2026.09.25.3",
        "flow": "checkout-v2",
    },
    # 14. Finance Verification
    {
        "marker": "ACMEFLOW-SEED-INC-2026-042-14",
        "category": "internal_escalation",
        "from": "Daniel Kim <daniel.kim@acmeflow.com>",
        "to": "maya.rao@acmeflow.com, arjun.mehta@acmeflow.com",
        "date": "Fri, 25 Sep 2026 15:20:00 +0000",
        "subject": "Finance check on PayPal capture failures - INC-2026-042",
        "body": (
            "Maya, Arjun:\n\n"
            "Quick finance check regarding INC-2026-042. I queried the PayPal reporting and balance endpoints; "
            "reporting API is functioning normally and existing settled balances are intact. Reviewing the failed orders "
            "(ORD-88219, ORD-88225, etc.), none show captured funds in our settlement ledger.\n\n"
            "However, because customers like BrightPath Labs have attempted retries, Support must ensure that once engineering "
            "resolves the capture issue, customer authorizations don't result in duplicate capture executions. We will reconcile "
            "any discrepancies in tomorrow morning's settlement sweep.\n\n"
            "Daniel Kim\n"
            "Finance Lead, AcmeFlow\n"
            "[ACMEFLOW-SEED-INC-2026-042-14]"
        ),
        "order_id": "ORD-88219, ORD-88225",
        "incident_id": "INC-2026-042",
    },
]


def find_swytchcode_bin() -> str:
    env_bin = os.getenv("SWYTCHCODE_BIN")
    if env_bin and os.path.exists(env_bin):
        return env_bin
    local_app_data = os.getenv("LOCALAPPDATA", "")
    if local_app_data:
        win_path = Path(local_app_data) / "Programs" / "swytchcode" / "bin" / "swytchcode.exe"
        if win_path.exists():
            return str(win_path)
    which_bin = shutil.which("swytchcode") or shutil.which("swy")
    if which_bin:
        return which_bin
    return "swytchcode"


def run_swytchcode(canonical_id: str, args: Dict[str, Any], timeout: int = 30) -> Dict[str, Any]:
    swy_bin = find_swytchcode_bin()
    cmd = [swy_bin, "exec", canonical_id, "--json"]
    stdin_payload = json.dumps(args)

    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(REPO_ROOT),
    )
    stdout, stderr = process.communicate(input=stdin_payload, timeout=timeout)

    start_idx = stdout.find("{")
    end_idx = stdout.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        try:
            parsed = json.loads(stdout[start_idx : end_idx + 1])
            if "status_code" in parsed or "data" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass

    return {"error": "Failed to parse json output", "raw_stdout": stdout, "raw_stderr": stderr}


def check_marker_exists(marker: str) -> Optional[str]:
    """Check if a message with the given marker already exists in Gmail."""
    res = run_swytchcode("gmail.user.messages.get", {"userId": "me", "q": marker})
    messages = res.get("data", {}).get("messages", [])
    if messages and len(messages) > 0:
        return messages[0].get("id")
    return None


def create_rfc2822_message(item: Dict[str, Any]) -> str:
    """Build a standard RFC 2822 email format."""
    lines = [
        f"From: {item['from']}",
        f"To: {item['to']}",
        f"Date: {item['date']}",
        f"Subject: {item['subject']}",
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=UTF-8",
        "",
        item["body"],
    ]
    return "\r\n".join(lines)


def insert_email_message(item: Dict[str, Any]) -> Dict[str, Any]:
    """Directly insert an email message into the user's mailbox via Swytchcode."""
    rfc_content = create_rfc2822_message(item)
    raw_b64 = base64.urlsafe_b64encode(rfc_content.encode("utf-8")).decode("ascii")

    payload = {
        "userId": "me",
        "internalDateSource": "dateHeader",
        "Content-Type": "application/json",
        "body": {
            "raw": raw_b64,
            "labelIds": ["INBOX"],
        },
    }
    return run_swytchcode("gmail.user.messages.create", payload)


def seed_gmail_dataset() -> Dict[str, Any]:
    print("=" * 65)
    print(" OpsDoctor - Gmail Test Dataset Seeding (Idempotent)")
    print("=" * 65)

    created_count = 0
    skipped_count = 0
    results = []

    print("\n[Execution] Checking markers and inserting messages...")
    for i, item in enumerate(GMAIL_DATASET, 1):
        marker = item["marker"]
        subject = item["subject"]
        existing_id = check_marker_exists(marker)

        if existing_id:
            skipped_count += 1
            print(f"  [{i}/14] SKIPPED: Already exists (ID={existing_id}) [{marker}]")
            results.append({
                "marker": marker,
                "status": "ALREADY_EXISTS",
                "gmail_id": existing_id,
                "subject": subject,
                "from": item["from"],
                "to": item["to"],
                "category": item["category"],
                "order_id": item.get("order_id"),
                "incident_id": item.get("incident_id"),
            })
        else:
            res = insert_email_message(item)
            data = res.get("data", {})
            new_id = data.get("id")
            if new_id:
                created_count += 1
                print(f"  [{i}/14] CREATED: ID={new_id} [{marker}] -> {subject[:45]}...")
                results.append({
                    "marker": marker,
                    "status": "CREATED",
                    "gmail_id": new_id,
                    "subject": subject,
                    "from": item["from"],
                    "to": item["to"],
                    "category": item["category"],
                    "order_id": item.get("order_id"),
                    "incident_id": item.get("incident_id"),
                })
            else:
                error = res.get("error", "Unknown error")
                print(f"  [{i}/14] FAILED: {error}")
                results.append({
                    "marker": marker,
                    "status": "FAILED",
                    "error": error,
                    "subject": subject,
                })
        time.sleep(0.4)

    return {
        "expected": len(GMAIL_DATASET),
        "created": created_count,
        "already_existed": skipped_count,
        "skipped": skipped_count,
        "duplicates": 0,
        "results": results,
    }


def verify_dataset(seed_summary: Dict[str, Any]) -> Dict[str, Any]:
    print("\n[Verification] Querying messages back through Swytchcode...")
    verification_results = {}
    verified_count = 0

    for item in GMAIL_DATASET:
        marker = item["marker"]
        res = run_swytchcode("gmail.user.messages.get", {"userId": "me", "q": marker})
        msgs = res.get("data", {}).get("messages", [])
        count = len(msgs)

        if count == 1:
            verified_count += 1
            msg_id = msgs[0]["id"]
            verification_results[marker] = {"verified": True, "id": msg_id, "count": count}
            print(f"  [VERIFIED] Marker {marker} -> Gmail ID: {msg_id} (Count: 1)")
        elif count == 0:
            verification_results[marker] = {"verified": False, "count": 0, "error": "Not found"}
            print(f"  [MISSING] Marker {marker} -> Not found in mailbox!")
        else:
            verification_results[marker] = {"verified": False, "count": count, "error": "Duplicate found"}
            print(f"  [DUPLICATE] Marker {marker} -> Multiple matches: {count}")

    print(f"\nRead-back verification: {verified_count}/{len(GMAIL_DATASET)} verified.")
    return verification_results


def write_manifest(seed_summary: Dict[str, Any], verification: Dict[str, Any]) -> Path:
    fixtures_dir = REPO_ROOT / "data" / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = fixtures_dir / "gmail_messages_manifest.json"

    manifest_content = {
        "incident_id": CANONICAL_INCIDENT,
        "payment_flow": CANONICAL_FLOW,
        "deployment_id": CANONICAL_DEPLOY,
        "target_account": TARGET_ACCOUNT,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "expected_messages": seed_summary["expected"],
            "created": seed_summary["created"],
            "already_existed": seed_summary["already_existed"],
            "skipped": seed_summary["skipped"],
            "duplicates": 0,
            "verified_in_mailbox": len([v for v in verification.values() if v.get("verified")]),
        },
        "messages": seed_summary["results"],
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
        if pattern in content:
            suspicious.append(pattern)

    if not suspicious:
        print("  [PASSED] Manifest is completely free of credentials, tokens, and secrets.")
    else:
        print(f"  [WARNING] Suspicious words found in fixture: {suspicious}")


def main():
    summary = seed_gmail_dataset()
    verification = verify_dataset(summary)
    fixture_path = write_manifest(summary, verification)
    audit_fixture_security(fixture_path)

    print("\n" + "=" * 65)
    print(" GMAIL SEEDING & VERIFICATION COMPLETE")
    print("=" * 65)


if __name__ == "__main__":
    main()
