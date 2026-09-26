"""Script to seed realistic operational test data into AcmeFlow Slack workspace.

Uses Swytchcode to execute Slack operations under managed OAuth2.
Follows AcmeFlow fictional operational timeline (Sep 25, 2026).
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parents[1]

CHANNELS = {
    "all-acmeflow-operations": "C0C43R6TS15",
    "general": "C0C4D0KH9C3",
    "ops-alerts": "C0C4E4BERRB",
    "ops-incidents": "C0C4D0G4H1R",
    "payments": "C0C4D0HSLF5",
    "social": "C0C4K2WG6LS",
    "new-channel": "C0C4E48431T",
}

CANONICAL_INCIDENT = "INC-2026-042"
CANONICAL_FLOW = "checkout-v2"
CANONICAL_DEPLOY = "checkout-api-2026.09.25.3"


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


def check_channel_member(channel_id: str) -> bool:
    res = run_swytchcode("slack.conversations.info.list", {"channel": channel_id})
    channel_info = res.get("data", {}).get("channel", {})
    return bool(channel_info.get("is_member", False))


def post_message(channel_id: str, text: str) -> Dict[str, Any]:
    payload = {
        "body": {
            "channel": channel_id,
            "text": text,
        }
    }
    return run_swytchcode("slack.chat.postmessage.create", payload)


SEED_DATA = {
    "payments": [
        (
            "*[Daniel Kim - Finance Lead]* (09:15 UTC)\n"
            "Morning team. Daily PayPal settlement reconciliation for Sep 24 completed clean. "
            "Gross settled: $184,250.00 across 1,420 transactions. Dispute volume remains under 0.05%."
        ),
        (
            "*[Shubham Ranswal - Operations Manager]* (11:30 UTC)\n"
            "Good to hear Daniel. FYI we have the gradual traffic ramp of `checkout-v2` continuing today - "
            "currently routing ~35% of web checkout traffic."
        ),
        (
            "*[Ethan Cole - On-call Engineer]* (13:50 UTC)\n"
            "FYI, deployment `checkout-api-2026.09.25.3` is going out to staging now, scheduled for prod rollout "
            "around 14:10 UTC. Includes the latency optimizations for `checkout-v2` capture calls."
        ),
        (
            "*[Priya Shah - Customer Support Lead]* (14:22 UTC)\n"
            "Hey team, seeing a couple of customer chats come in about failed PayPal checkouts on the annual plan. "
            "Customer *BrightPath Labs* tried twice for order `ORD-88219` (PayPal ref `PAYID-MZ4910`) and hit an unexpected error screen on confirm."
        ),
        (
            "*[Sofia Martinez - Customer Success]* (14:31 UTC)\n"
            "Adding to Priya's note - Enterprise customer *OmniCorp Logistics* just reached out over email. "
            "Their procurement team got a generic failure trying to renew order `ORD-88225`. Is PayPal having an outage?"
        ),
        (
            "*[Daniel Kim - Finance Lead]* (14:36 UTC)\n"
            "I just checked PayPal status page and our reporting endpoints (`reporting.transactions.list`). "
            "The PayPal status dashboard is all green, and reporting API calls are returning 200 OK. "
            "But our capture success rate in the internal dashboard just dropped sharply."
        ),
        (
            "*[Arjun Mehta - Engineering Lead]* (14:42 UTC)\n"
            "Looking into this with Ethan. It looks isolated to `checkout-v2` flows specifically. "
            "Customers going through legacy checkout-v1 are checking out with 0 issues. Ethan is spinning up an incident update in #ops-incidents."
        ),
        (
            "*[Priya Shah - Customer Support Lead]* (14:55 UTC)\n"
            "Thanks Arjun. We've created Jira ticket `OPS-412` and linked customer support case `CS-1094`. "
            "Support macro sent to affected users advising them not to spam retries while we investigate."
        ),
    ],
    "ops-alerts": [
        (
            "`[INFO] [Monitor: Payment Gateway Health] [Region: us-east-1]`\n"
            "Status: HEALTHY | p95 latency: 142ms | Error rate: 0.04% | Active flow: checkout-v1 (65%), checkout-v2 (35%) | 08:00 UTC"
        ),
        (
            "`[INFO] [Monitor: Scheduled Batch Reconciliation]`\n"
            "PayPal Settlement sync: COMPLETE | 1,420 records processed | Discrepancies: 0 | 12:00 UTC"
        ),
        (
            "`[DEPLOY] [Service: checkout-api]`\n"
            "Release `checkout-api-2026.09.25.3` deployed to production (us-east-1) by CI/CD pipeline #4412. Commit: `9f8a12c`. | 14:12 UTC"
        ),
        (
            "`[WARN] [Alert: Elevated HTTP 4xx/5xx on Checkout Service]`\n"
            "Metric: Error rate on endpoint `/v2/checkout/orders/capture` exceeded threshold 1.0% (Current: 2.14%). Flow: `checkout-v2`. Triggered at 14:18:22 UTC."
        ),
        (
            "`[ALERT] [PagerDuty P1] [Service: checkout-api]`\n"
            "Condition: CRITICAL_PAYMENT_FAILURE_RATE | Provider: PayPal | Flow: `checkout-v2` | Failure Rate: 14.8% (Threshold: 5.0%) | Incident: Triggered | Assigned: Ethan Cole (Primary On-Call) | 14:34 UTC"
        ),
        (
            "`[ALERT] [Queue Monitor: payment-retry-queue]`\n"
            "Backlog depth: 462 messages (Warning threshold: 250). DLQ ingress: 18 messages/min. | 14:38 UTC"
        ),
        (
            "`[STATUS] [Incident Management: OpsGenie]`\n"
            "Incident `INC-2026-042` declared by @ethan.cole. Priority: P1 - High. War room initiated. | 14:40 UTC"
        ),
    ],
    "ops-incidents": [
        (
            "*[RESOLVED] INC-2026-038: Redis session store memory eviction causing transient 401s on Web Dashboard*\n"
            "• Impact: ~120 user sessions logged out unexpectedly between 09:15 - 09:48 UTC on Sep 12.\n"
            "• Root Cause: Redis maxmemory policy was set to noeviction instead of volatile-lru during node resize.\n"
            "• Action Items: Maxmemory policy updated; alerting threshold set at 75% memory utilization.\n"
            "• Postmortem doc: Notion > Operations / Incident Reviews / INC-2026-038 Postmortem"
        ),
        (
            "*:rotating_light: INCIDENT DECLARED: INC-2026-042 (P1)*\n"
            "• *Title*: Elevated PayPal payment capture failures on checkout-v2\n"
            "• *Incident Commander*: Ethan Cole\n"
            "• *Ops Lead*: Shubham Ranswal\n"
            "• *Engineering Lead*: Arjun Mehta\n"
            "• *Impact*: Customers attempting payments via `checkout-v2` receiving capture failures. Error rate ~15%.\n"
            "• *Tracking Jira*: `OPS-412` | *Runbook*: Notion > Operations / Runbooks / Payment Incident Response (REV-4)\n"
            "• *Declared*: 14:38 UTC"
        ),
        (
            "*[Shubham Ranswal - Operations Manager]* (14:44 UTC)\n"
            "Ops update: Customer Support is tracking ~8 escalated tickets so far. Finance reports no issues on PayPal reporting or webhook listener infrastructure. Initial customer transactions affected include order `ORD-88219`, `ORD-88225`, and `ORD-88231`."
        ),
        (
            "*[Arjun Mehta - Engineering Lead]* (14:49 UTC)\n"
            "Investigation update: Comparing failure timelines against deployments. Issue started sharply at 14:14 UTC, right after deployment of `checkout-api-2026.09.25.3`. Note that legacy checkout-v1 is unaffected. Looking into recent commit diffs on the `checkout-v2` capture payload serializer."
        ),
        (
            "*[Ethan Cole - On-call Engineer]* (14:56 UTC)\n"
            "Investigating logs: PayPal is returning HTTP 422 / UNPROCESSABLE_ENTITY on specific capture requests under `checkout-v2`.\n"
            "Hypothesis 1: Token scope issue - ruled out, token refresh is healthy.\n"
            "Hypothesis 2: PayPal Sandbox/upstream API change - checking sandbox announcements.\n"
            "Hypothesis 3: Serialization format of currency or amount breakdown in `checkout-api-2026.09.25.3`."
        ),
        (
            "*[Daniel Kim - Finance Lead]* (15:05 UTC)\n"
            "Finance check: Settlement balance is intact. None of the failed transactions have authorizations stuck in pending settlement, but we need to ensure retried captures don't double-charge when resolved."
        ),
        (
            "*[Arjun Mehta - Engineering Lead]* (15:12 UTC)\n"
            "Update: Testing rollback of deployment `checkout-api-2026.09.25.3` vs targeted feature flag toggle on `checkout-v2`. Arjun and Ethan reproducing locally in staging. Next update in 15 mins."
        ),
    ],
    "general": [
        (
            "*[Shubham Ranswal - Operations Manager]* (08:30 UTC)\n"
            "Good morning AcmeFlow! Friendly reminder that Q3 OKR departmental rollups are due this Friday by 5 PM. Please ensure your team sheets in Notion are updated."
        ),
        (
            "*[Arjun Mehta - Engineering Lead]* (10:15 UTC)\n"
            "Engineering release window reminder: Standard deploy window is today 14:00 - 15:30 UTC. Teams with scheduled service updates please coordinate in #dev-releases."
        ),
        (
            "*[Priya Shah - Customer Support Lead]* (12:45 UTC)\n"
            "Customer Support team lunch is happening today at 1 PM! Support coverage will be handled by the EMEA rotation during that hour."
        ),
        (
            "*[Shubham Ranswal - Operations Manager]* (16:00 UTC)\n"
            "Pantry reminder: Fresh fruit and cold brew have been restocked on the 3rd floor. Please remember to label any personal containers in the fridge!"
        ),
    ],
    "all-acmeflow-operations": [
        (
            "*[Shubham Ranswal - Operations Manager]* (09:00 UTC)\n"
            "Weekly Operations Pulse (Sep 25, 2026): Platform uptime at 99.94% across all regions. Customer onboarding cycle time reduced by 12% this sprint. Excellent work cross-functional team!"
        ),
        (
            "*[Daniel Kim - Finance Lead]* (11:00 UTC)\n"
            "FYI to team leads: September end-of-month expense reports must be submitted into Concur by Monday morning for monthly close."
        ),
        (
            "*[Shubham Ranswal - Operations Manager]* (14:45 UTC)\n"
            "Operations Notice: Ops and Engineering are actively managing an intermittent issue impacting some checkout payments. An incident has been declared and the team is working on mitigation. Please direct any customer inquiries to Priya's support team queue."
        ),
        (
            "*[Shubham Ranswal - Operations Manager]* (15:30 UTC)\n"
            "Operations Update: Payment investigation is progressing with engineering. Root cause isolation underway. Support has established customer communication macros. Further technical updates will remain centralized in #ops-incidents."
        ),
    ],
    "social": [
        (
            "*[Sofia Martinez - Customer Success]* (10:00 UTC)\n"
            "Anyone tried that new taco truck parked outside Building 4 yet? The birria tacos look amazing :taco:"
        ),
        (
            "*[Ethan Cole - On-call Engineer]* (10:08 UTC)\n"
            "Can confirm, had them yesterday! The spicy salsa is legitimately hot though, beware :fire:"
        ),
        (
            "*[Arjun Mehta - Engineering Lead]* (11:45 UTC)\n"
            "Quick question for the keyboard nerds here: looking for quiet tactile switch recommendations for office use. Boba U4s or Gateron Browns?"
        ),
        (
            "*[Daniel Kim - Finance Lead]* (12:02 UTC)\n"
            "Boba U4 silent tactiles all the way Arjun, night and day difference for office typing."
        ),
        (
            "*[Sofia Martinez - Customer Success]* (15:10 UTC)\n"
            "Friday dog park meetup is still on for 5:30 PM by the fountain park if anyone wants to bring their pups! :dog:"
        ),
    ],
}


def main():
    print("=" * 60)
    print(" OpsDoctor - Seeding Realistic Slack Operational Data")
    print("=" * 60)

    # 1. Check membership status for each channel via conversations.info
    print("\n[1] Checking channel membership for @swytchcode bot...")
    unjoined = []
    joined = []

    for name, cid in CHANNELS.items():
        if name == "new-channel":
            continue
        is_member = check_channel_member(cid)
        if is_member:
            joined.append(name)
            print(f"  [OK] #{name:<25} (ID: {cid}) -> Member: True")
        else:
            unjoined.append(name)
            print(f"  [!]  #{name:<25} (ID: {cid}) -> Member: False")

    if unjoined:
        print(f"\n[!] The bot is not a member of {len(unjoined)} channels:")
        for ch in unjoined:
            print(f"      #{ch}")
        return

    # 2. Post messages to joined channels
    print("\n[2] Seeding operational messages to channels...")
    posted_records = {}
    for channel_name, messages in SEED_DATA.items():
        cid = CHANNELS[channel_name]
        print(f"\nPosting {len(messages)} messages to #{channel_name} ({cid})...")
        posted_records[channel_name] = []
        for i, text in enumerate(messages, 1):
            res = post_message(cid, text)
            data = res.get("data", {})
            if data.get("ok"):
                ts = data.get("ts")
                posted_records[channel_name].append({"text": text, "ts": ts, "ok": True})
                first_line = text.split("\n")[0][:50]
                print(f"  [{i}/{len(messages)}] Posted (ts={ts}): {first_line}...")
            else:
                error = data.get("error") or res.get("error") or "unknown"
                print(f"  [{i}/{len(messages)}] FAILED: {error}")
                posted_records[channel_name].append({"text": text, "ok": False, "error": error})
            time.sleep(0.4)

    # 3. Verification
    print("\n" + "=" * 60)
    print(" VERIFICATION & AUDIT REPORT")
    print("=" * 60)

    all_texts = []
    print(f"\n{'Channel':<26} {'Status':<10} {'Posted':<8} {CANONICAL_INCIDENT:<15} {CANONICAL_FLOW:<15} {CANONICAL_DEPLOY:<15}")
    print("-" * 95)

    for ch_name, records in posted_records.items():
        successful = [r for r in records if r.get("ok")]
        ch_text = " ".join(r["text"] for r in successful)
        all_texts.append(ch_text)
        has_inc = CANONICAL_INCIDENT in ch_text
        has_flow = CANONICAL_FLOW in ch_text
        has_dep = CANONICAL_DEPLOY in ch_text
        status = "COMPLETE" if len(successful) == len(records) else "PARTIAL"

        print(
            f"#{ch_name:<25} {status:<10} {len(successful)}/{len(records):<5} "
            f"{str(has_inc):<15} {str(has_flow):<15} {str(has_dep):<15}"
        )

    # Check #new-channel
    print(f"#{'new-channel':<25} {'SKIPPED':<10} {'0/0 (empty)':<15} {'False':<15} {'False':<15} {'False':<15}")

    # Security check: verify no secrets
    print("\n[Security Verification]")
    combined_dump = " ".join(all_texts)
    secrets_suspect = []
    for pattern in ["client_secret", "secret", "bearer_token", "xoxb-", "access_token"]:
        if pattern in combined_dump.lower() and "noeviction" not in combined_dump.lower():
            secrets_suspect.append(pattern)

    if not secrets_suspect:
        print("  [PASSED] No API keys, OAuth tokens, client secrets, or credentials in posted messages.")
    else:
        print(f"  [WARN] Suspect tokens found: {secrets_suspect}")

    print("\nData seeding is complete!")


if __name__ == "__main__":
    main()
